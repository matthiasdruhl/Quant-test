"""Capture actual locked wheels, then replay and test a fresh offline toolchain.

Development-only consumer under ADR0019. No experiment/source authentication,
crash durability, durable retention or hostile-code network sandbox is claimed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tomllib
import zipfile
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import parse_tag, sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

from quant_test.data.raw_archive import LocalRawArchive

POLICY = "offline-locked-toolchain-replay-v1"
CONSUMER = "isolated-installed-pytest-v1"
UV_VERSION = "0.13.5"


def controlled_environment() -> dict[str, str]:
    """Pass only ordinary system paths/locale plus explicit nonsecret controls."""
    names = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "LANG", "LC_ALL")
    result = {name: os.environ[name] for name in names if name in os.environ}
    result.update(PIP_CONFIG_FILE=os.devnull, NETRC=os.devnull, GIT_OPTIONAL_LOCKS="0")
    return result


def run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=cwd, env=controlled_environment(), capture_output=True, text=True, check=False
    )


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"Consumer command failed ({result.returncode}):\n{result.stdout}{result.stderr}"
        )


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def checked_digest(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected a lowercase SHA-256 hex digest")
    return value


def checked_path(path: Path, *, directory: bool = False) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise ValueError("Inputs must be absolute paths without '..'")
    for component in (*reversed(path.parents), path):
        metadata = component.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Symlink input component: {component}")
    mode = path.lstat().st_mode
    if directory and not stat.S_ISDIR(mode):
        raise ValueError("Expected an existing directory")
    if not directory and not stat.S_ISREG(mode):
        raise ValueError("Expected a regular input file")
    return path


def read_regular(path: Path) -> bytes:
    checked_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Input is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class LockedRequirement:
    name: str
    version: str
    hashes: tuple[str, ...]


def parse_lock(payload: bytes, marker_environment: dict[str, str]) -> tuple[LockedRequirement, ...]:
    """Accept only the reviewed generated exact-name/version/hash/marker subset."""
    pending = ""
    records: dict[str, LockedRequirement] = {}
    for original in payload.decode("ascii").splitlines():
        line = original.strip()
        if not line or line.startswith("#"):
            if pending:
                raise ValueError("Interrupted lock continuation")
            continue
        continuation = line.endswith("\\")
        pending += " " + (line[:-1].rstrip() if continuation else line)
        if continuation:
            continue
        match = re.fullmatch(r"(.+?)\s+((?:--hash=sha256:[0-9a-f]{64}(?:\s+|$))+)", pending.strip())
        if match is None:
            raise ValueError("Unsupported lock record syntax")
        requirement = Requirement(match[1])
        specifiers = list(requirement.specifier)
        if (
            requirement.url is not None
            or requirement.extras
            or len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
        ):
            raise ValueError("Lock must contain named exact versions without extras or URLs")
        version = str(Version(specifiers[0].version))
        name = str(canonicalize_name(requirement.name))
        hashes = tuple(re.findall(r"--hash=sha256:([0-9a-f]{64})", match[2]))
        if len(set(hashes)) != len(hashes):
            raise ValueError("Duplicate lock hash")
        if requirement.marker is None or requirement.marker.evaluate(marker_environment):
            if name in records:
                raise ValueError("Duplicate active lock requirement")
            records[name] = LockedRequirement(name, version, tuple(sorted(hashes)))
        pending = ""
    if pending:
        raise ValueError("Unterminated lock continuation")
    if not records:
        raise ValueError("Empty active lock")
    return tuple(records[name] for name in sorted(records))


@dataclass(frozen=True)
class WheelInput:
    filename: str
    name: str
    version: str
    size: int
    sha256: str
    payload: bytes = field(repr=False, compare=False)

    def document(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "name": self.name,
            "version": self.version,
            "size": self.size,
            "sha256": self.sha256,
        }


def _one_header(message: object, name: str, *, optional: bool = False) -> str | None:
    # EmailMessage is used without executing package metadata or extracting a ZIP.
    values = message.get_all(name, [])  # type: ignore[attr-defined]
    if not values and optional:
        return None
    if len(values) != 1 or not str(values[0]).strip():
        raise ValueError(f"Wheel requires one {name} header")
    return str(values[0])


def inspect_wheel(path: Path) -> WheelInput:
    filename = path.name
    if not filename.isascii() or re.fullmatch(r"[A-Za-z0-9_.+!-]+\.whl", filename) is None:
        raise ValueError("Unsafe or unsupported wheel basename")
    name, version, _, tags = parse_wheel_filename(filename)
    if not tags.intersection(sys_tags()):
        raise ValueError("Wheel tags incompatible with current interpreter")
    payload = read_regular(path)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        members = archive.infolist()
        member_names = [item.filename for item in members]
        if len(set(member_names)) != len(member_names):
            raise ValueError("Duplicate wheel ZIP member")
        for item in members:
            parts = item.filename.split("/")
            if (
                item.filename.startswith("/")
                or "\\" in item.filename
                or ".." in parts
                or any(ord(char) < 32 for char in item.filename)
                or item.flag_bits & 1
                or stat.S_ISLNK(item.external_attr >> 16)
            ):
                raise ValueError("Unsafe wheel ZIP member")
        metadata_names = [
            value
            for value in member_names
            if value.count("/") == 1 and value.endswith(".dist-info/METADATA")
        ]
        wheel_names = [
            value
            for value in member_names
            if value.count("/") == 1 and value.endswith(".dist-info/WHEEL")
        ]
        if len(metadata_names) != 1 or len(wheel_names) != 1:
            raise ValueError("Wheel requires one METADATA and WHEEL")
        metadata_name, wheel_name = metadata_names[0], wheel_names[0]
        if (
            metadata_name.rsplit("/", 1)[0] != wheel_name.rsplit("/", 1)[0]
            or metadata_name.count("/") != 1
        ):
            raise ValueError("Wheel metadata directories disagree")
        directory = metadata_name.split("/")[0][: -len(".dist-info")]
        if "-" not in directory:
            raise ValueError("Malformed dist-info identity")
        directory_name, directory_version = directory.rsplit("-", 1)
        if canonicalize_name(directory_name) != name or Version(directory_version) != version:
            raise ValueError("Wheel dist-info identity disagrees with filename")
        metadata = BytesParser(policy=policy.default).parsebytes(archive.read(metadata_name))
        wheel = BytesParser(policy=policy.default).parsebytes(archive.read(wheel_name))
        if (
            canonicalize_name(text(_one_header(metadata, "Name")), validate=True) != name
            or Version(text(_one_header(metadata, "Version"))) != version
        ):
            raise ValueError("Wheel METADATA identity disagrees with filename")
        requires_python = _one_header(metadata, "Requires-Python", optional=True)
        if requires_python is not None and not SpecifierSet(requires_python).contains(
            platform.python_version()
        ):
            raise ValueError("Wheel Requires-Python incompatible")
        if _one_header(wheel, "Wheel-Version") != "1.0":
            raise ValueError("Unsupported WHEEL version")
        if _one_header(wheel, "Root-Is-Purelib") not in ("true", "false"):
            raise ValueError("Malformed WHEEL purelib declaration")
        declared_tags = wheel.get_all("Tag", [])
        if (
            not declared_tags
            or frozenset(tag for value in declared_tags for tag in parse_tag(str(value))) != tags
        ):
            raise ValueError("WHEEL Tag metadata disagrees with filename")
    return WheelInput(filename, str(name), str(version), len(payload), digest(payload), payload)


def source_revision(source_root: Path) -> str:
    checked_path(source_root, directory=True)
    top = run(["git", "-C", str(source_root), "rev-parse", "--show-toplevel"])
    require_success(top)
    if Path(top.stdout.strip()).resolve() != source_root:
        raise ValueError("source-root must be the checkout root")
    revision = run(["git", "-C", str(source_root), "rev-parse", "--verify", "HEAD"])
    require_success(revision)
    if re.fullmatch(r"[0-9a-f]{40}", revision.stdout.strip()) is None:
        raise ValueError("Expected an actual Git commit")
    status = run(
        [
            "git",
            "-C",
            str(source_root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        ]
    )
    require_success(status)
    if status.stdout:
        raise ValueError("Source checkout is dirty; clean committed input is required")
    return revision.stdout.strip()


def uv_executable() -> Path:
    executable = shutil.which("uv", path=controlled_environment().get("PATH"))
    if executable is None:
        raise ValueError("Pinned uv executable not found")
    return Path(executable).resolve(strict=True)


def host_observation(
    requirements: tuple[LockedRequirement, ...], source_root: Path
) -> dict[str, object]:
    expected_python = read_regular(source_root / ".python-version").decode("ascii").strip()
    if (
        platform.python_implementation() != "CPython"
        or platform.python_version() != expected_python
    ):
        raise ValueError("Host interpreter differs from repository baseline")
    expected = {item.name: item.version for item in requirements}
    tools: dict[str, str] = {}
    for name in ("pip", "packaging"):
        tools[name] = importlib.metadata.version(name)
        if name not in expected or Version(tools[name]) != Version(expected[name]):
            raise ValueError(f"Observed host {name} version differs from active lock")
    uv = uv_executable()
    result = run([str(uv), "--version"])
    require_success(result)
    if result.stdout.split()[:2] != ["uv", UV_VERSION]:
        raise ValueError("Unexpected uv version")
    try:
        uv_hash, limitation = digest(read_regular(uv)), None
    except (OSError, ValueError):
        uv_hash, limitation = (
            None,
            "uv executable bytes not readable; binary provenance unavailable",
        )
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_build": list(platform.python_build()),
        "python_compiler": platform.python_compiler(),
        "python_cache_tag": sys.implementation.cache_tag,
        "python_executable_sha256": digest(read_regular(Path(sys.executable).resolve(strict=True))),
        "system": platform.system(),
        "release": platform.release(),
        "platform_version": platform.version(),
        "machine": platform.machine(),
        "marker_environment": default_environment(),
        "host_tools": tools,
        "uv_version": result.stdout.strip(),
        "uv_executable_sha256": uv_hash,
        "uv_provenance_limitation": limitation,
    }


@dataclass(frozen=True)
class ReplayInputs:
    wheelhouse: Path
    local_wheel: Path
    lock: Path
    source_root: Path
    report_dir: Path


@dataclass(frozen=True)
class PreparedInputs:
    manifest: dict[str, object]
    wheels: tuple[WheelInput, ...]
    local_wheel: WheelInput


def prepare(inputs: ReplayInputs, expected_lock: str, expected_local: str) -> PreparedInputs:
    checked_digest(expected_lock)
    checked_digest(expected_local)
    checked_path(inputs.wheelhouse, directory=True)
    checked_path(inputs.report_dir, directory=True)
    checked_path(inputs.source_root, directory=True)
    checked_path(inputs.source_root / "tests", directory=True)
    lock_bytes = read_regular(inputs.lock)
    if digest(lock_bytes) != expected_lock:
        raise ValueError("Pinned lock digest mismatch")
    if read_regular(inputs.source_root / "requirements-dev.lock") != lock_bytes:
        raise ValueError("Supplied lock differs from checked source revision's lock")
    requirements = parse_lock(
        lock_bytes, {key: text(value) for key, value in default_environment().items()}
    )
    observed = host_observation(requirements, inputs.source_root)
    revision = source_revision(inputs.source_root)
    wheels = tuple(inspect_wheel(path) for path in sorted(inputs.wheelhouse.iterdir()))
    by_name = {wheel.name: wheel for wheel in wheels}
    if len(by_name) != len(wheels):
        raise ValueError("Duplicate wheel distribution name")
    if set(by_name) != {item.name for item in requirements}:
        raise ValueError("Wheelhouse does not exactly match complete active lock")
    for item in requirements:
        wheel = by_name[item.name]
        if wheel.version != item.version or wheel.sha256 not in item.hashes:
            raise ValueError("Wheel version/hash differs from active lock")
    local = inspect_wheel(inputs.local_wheel)
    if local.sha256 != expected_local:
        raise ValueError("Pinned local wheel digest mismatch")
    project = tomllib.loads(read_regular(inputs.source_root / "pyproject.toml").decode("utf-8"))[
        "project"
    ]
    if local.name != canonicalize_name(project["name"]) or Version(local.version) != Version(
        project["version"]
    ):
        raise ValueError("Local wheel does not match project identity")
    if local.name in by_name:
        raise ValueError("Local project must not appear in dependency wheelhouse")
    ordered = tuple(sorted(wheels, key=lambda item: item.name))
    manifest: dict[str, object] = {
        "schema_version": 1,
        "policy_id": POLICY,
        "consumer_policy_id": CONSUMER,
        "lock_sha256": expected_lock,
        "active_requirements": [
            {"name": item.name, "version": item.version} for item in requirements
        ],
        "dependency_wheels": [wheel.document() for wheel in ordered],
        "local_wheel": local.document(),
        "host": observed,
        "source_revision": revision,
    }
    return PreparedInputs(manifest, ordered, local)


def canonical(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def reject_number(value: str) -> object:
    raise ValueError(f"Unsupported JSON number: {value}")


def mapping(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Manifest object fields differ from schema")
    return value


def text(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("Manifest field must be text")
    return value


def _identities(value: object, *, wheels: bool) -> list[dict[str, object]]:
    if type(value) is not list:
        raise ValueError("Manifest collection must be an array")
    names: list[str] = []
    for item in value:
        fields = (
            {"name", "version", "filename", "size", "sha256"} if wheels else {"name", "version"}
        )
        item = mapping(item, fields)
        name = text(item["name"])
        if (
            canonicalize_name(name, validate=True) != name
            or str(Version(text(item["version"]))) != item["version"]
        ):
            raise ValueError("Noncanonical distribution identity")
        names.append(name)
        if wheels:
            filename = text(item["filename"])
            if not filename.isascii() or re.fullmatch(r"[A-Za-z0-9_.+!-]+\.whl", filename) is None:
                raise ValueError("Unsafe manifest wheel basename")
            wheel_name, wheel_version, _, _ = parse_wheel_filename(filename)
            if wheel_name != name or str(wheel_version) != item["version"]:
                raise ValueError("Manifest filename and distribution identity differ")
            if type(item["size"]) is not int or item["size"] <= 0:
                raise ValueError("Manifest wheel size must be a positive integer")
            checked_digest(item["sha256"])
    if names != sorted(set(names)):
        raise ValueError("Manifest collections must be sorted and unique")
    return value


def decode_manifest(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes:
        raise ValueError("Manifest bytes must be immutable")
    document = mapping(
        json.loads(
            payload.decode("ascii"),
            object_pairs_hook=unique_object,
            parse_float=reject_number,
            parse_constant=reject_number,
        ),
        {
            "schema_version",
            "policy_id",
            "consumer_policy_id",
            "lock_sha256",
            "active_requirements",
            "dependency_wheels",
            "local_wheel",
            "host",
            "source_revision",
        },
    )
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("Unsupported manifest schema")
    if document["policy_id"] != POLICY or document["consumer_policy_id"] != CONSUMER:
        raise ValueError("Unsupported manifest policy")
    checked_digest(document["lock_sha256"])
    requirements = _identities(document["active_requirements"], wheels=False)
    wheels = _identities(document["dependency_wheels"], wheels=True)
    if [(item["name"], item["version"]) for item in requirements] != [
        (item["name"], item["version"]) for item in wheels
    ]:
        raise ValueError("Manifest active plan and wheels differ")
    local = _identities([document["local_wheel"]], wheels=True)[0]
    if local["name"] in {item["name"] for item in requirements}:
        raise ValueError("Local wheel also appears in active dependencies")
    host = mapping(
        document["host"],
        {
            "python_implementation",
            "python_version",
            "python_build",
            "python_compiler",
            "python_cache_tag",
            "python_executable_sha256",
            "system",
            "release",
            "platform_version",
            "machine",
            "marker_environment",
            "host_tools",
            "uv_version",
            "uv_executable_sha256",
            "uv_provenance_limitation",
        },
    )
    for name in (
        "python_implementation",
        "python_version",
        "python_compiler",
        "python_cache_tag",
        "system",
        "release",
        "platform_version",
        "machine",
        "uv_version",
    ):
        text(host[name])
    if (
        type(host["python_build"]) is not list
        or len(host["python_build"]) != 2
        or any(type(item) is not str for item in host["python_build"])
    ):
        raise ValueError("Malformed Python build")
    checked_digest(host["python_executable_sha256"])
    if host["uv_executable_sha256"] is None:
        text(host["uv_provenance_limitation"])
    else:
        checked_digest(host["uv_executable_sha256"])
        if host["uv_provenance_limitation"] is not None:
            raise ValueError("Unexpected uv provenance limitation")
    markers = mapping(host["marker_environment"], set(default_environment()))
    for value in markers.values():
        text(value)
    tools = mapping(host["host_tools"], {"pip", "packaging"})
    for value in tools.values():
        Version(text(value))
    if (
        not isinstance(document["source_revision"], str)
        or re.fullmatch(r"[0-9a-f]{40}", document["source_revision"]) is None
    ):
        raise ValueError("Malformed source revision")
    if canonical(document) != payload:
        raise ValueError("Manifest encoding is not canonical")
    return document


def publish(archive: LocalRawArchive, document: dict[str, object]) -> str:
    payload = canonical(document)
    sha256 = digest(payload)
    archive.put(sha256, payload)
    if archive.get(sha256) != payload:
        raise ValueError("Publication read-back differs")
    return sha256


def capture(inputs: ReplayInputs, expected_lock: str, expected_local: str) -> str:
    prepared = prepare(inputs, expected_lock, expected_local)
    payload = canonical(prepared.manifest)
    decode_manifest(payload)
    archive = LocalRawArchive(inputs.report_dir)
    sha256 = publish(archive, prepared.manifest)
    decode_manifest(archive.get(sha256))
    return sha256


INVENTORY_CODE = """import importlib.metadata,json
records=[]
for distribution in importlib.metadata.distributions():
    direct=distribution.read_text("direct_url.json")
    editable=bool(direct and json.loads(direct).get("dir_info",{}).get("editable",False))
    records.append({"name":distribution.metadata["Name"],"version":distribution.version,"editable":editable})
print(json.dumps(records))
"""


def child_inventory(python: Path, cwd: Path) -> list[dict[str, str]]:
    result = run([str(python), "-I", "-c", INVENTORY_CODE], cwd=cwd)
    require_success(result)
    raw = json.loads(result.stdout)
    if type(raw) is not list:
        raise ValueError("Malformed installed inventory")
    records: dict[str, dict[str, str]] = {}
    for item in raw:
        item = mapping(item, {"name", "version", "editable"})
        name = str(canonicalize_name(text(item["name"])))
        if item["editable"] is not False or name in records:
            raise ValueError("Editable/duplicate installed distribution")
        records[name] = {"name": name, "version": str(Version(text(item["version"])))}
    return [records[name] for name in sorted(records)]


ORIGIN_CODE = """import hashlib,importlib,json,pathlib,platform,sys,sysconfig
roots={pathlib.Path(sysconfig.get_path(key)).resolve() for key in ("purelib","platlib")}
origins={}
for name in ("quant_test","quant_test.core.time","quant_test.data.raw_archive","quant_test.strategies.targets"):
    module=importlib.import_module(name)
    path=pathlib.Path(module.__file__).resolve()
    if not any(path.is_relative_to(root) for root in roots):
        raise SystemExit("Source or host import fallback")
    if not path.is_relative_to(pathlib.Path(sys.prefix).resolve()):
        raise SystemExit("Import outside fresh environment")
    origins[name]=str(path.relative_to(pathlib.Path(sys.prefix).resolve()))
observation={"python_implementation":platform.python_implementation(),"python_version":platform.python_version(),
"python_build":list(platform.python_build()),"python_compiler":platform.python_compiler(),
"python_cache_tag":sys.implementation.cache_tag,
"python_executable_sha256":hashlib.sha256(pathlib.Path(sys.executable).resolve().read_bytes()).hexdigest(),
"system":platform.system(),"release":platform.release(),"platform_version":platform.version(),"machine":platform.machine()}
print(json.dumps({"origins":origins,"environment":observation}))
"""


def junit_counts(path: Path) -> dict[str, int]:
    root = ElementTree.fromstring(read_regular(path))
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise ValueError("Missing JUnit suite")
    result = {
        name: sum(int(suite.attrib.get(name, "0")) for suite in suites)
        for name in ("tests", "failures", "errors", "skipped")
    }
    result["passed"] = result["tests"] - result["failures"] - result["errors"] - result["skipped"]
    if (
        result["tests"] <= 0
        or result["passed"] <= 0
        or result["failures"]
        or result["errors"]
        or any(value < 0 for value in result.values())
    ):
        raise ValueError("Test consumer failed or collected no passing tests")
    return result


def offline_consumer(inputs: ReplayInputs, prepared: PreparedInputs) -> dict[str, object]:
    with TemporaryDirectory(prefix="quant-toolchain-replay-") as temporary:
        scratch = Path(temporary).resolve()
        environment, staged = scratch / "venv", scratch / "wheels"
        staged.mkdir()
        for wheel in (*prepared.wheels, prepared.local_wheel):
            target = staged / wheel.filename
            target.write_bytes(wheel.payload)
            if digest(read_regular(target)) != wheel.sha256:
                raise ValueError("Staged wheel hash mismatch")
        plan = scratch / "requirements.txt"
        plan.write_text(
            "".join(
                f"{(staged / wheel.filename).as_uri()} --hash=sha256:{wheel.sha256}\n"
                for wheel in (*prepared.wheels, prepared.local_wheel)
            ),
            encoding="ascii",
        )
        uv = str(uv_executable())
        created = run(
            [
                uv,
                "venv",
                "--offline",
                "--no-cache",
                "--no-config",
                "--no-project",
                "--no-python-downloads",
                "--python",
                sys.executable,
                str(environment),
            ],
            cwd=scratch,
        )
        require_success(created)
        python = environment / "bin" / "python"
        if child_inventory(python, scratch):
            raise ValueError("Fresh environment is seeded")
        installed = run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                "--offline",
                "--no-index",
                "--no-cache",
                "--no-config",
                "--no-python-downloads",
                "--only-binary=:all:",
                "--require-hashes",
                "--reinstall",
                "--strict",
                "-r",
                str(plan),
            ],
            cwd=scratch,
        )
        require_success(installed)
        expected = sorted(
            [
                {"name": item.name, "version": item.version}
                for item in (*prepared.wheels, prepared.local_wheel)
            ],
            key=lambda item: item["name"],
        )
        inventory = child_inventory(python, scratch)
        if inventory != expected:
            raise ValueError("Installed inventory differs from complete pinned plan")
        checked = run(
            [str(python), "-I", "-m", "pip", "--isolated", "--disable-pip-version-check", "check"],
            cwd=scratch,
        )
        require_success(checked)
        imported = run([str(python), "-I", "-c", ORIGIN_CODE], cwd=scratch)
        require_success(imported)
        origins = mapping(json.loads(imported.stdout), {"origins", "environment"})
        host = prepared.manifest["host"]
        assert isinstance(host, dict)
        child_fields = {
            "python_implementation",
            "python_version",
            "python_build",
            "python_compiler",
            "python_cache_tag",
            "python_executable_sha256",
            "system",
            "release",
            "platform_version",
            "machine",
        }
        child = mapping(origins["environment"], child_fields)
        if child != {key: host[key] for key in child_fields}:
            raise ValueError("Observed child interpreter/platform differs from captured host")
        junit = scratch / "pytest.xml"
        tested = run(
            [
                str(python),
                "-I",
                "-m",
                "pytest",
                "--import-mode=importlib",
                "-c",
                str(inputs.source_root / "pyproject.toml"),
                str(inputs.source_root / "tests"),
                "--junitxml",
                str(junit),
                "-o",
                f"cache_dir={scratch / 'pytest-cache'}",
                "-q",
            ],
            cwd=scratch,
        )
        require_success(tested)
        counts = junit_counts(junit)
        if child_inventory(python, scratch) != expected:
            raise ValueError("Installed inventory changed during consumer")
        for wheel in (*prepared.wheels, prepared.local_wheel):
            if digest(read_regular(staged / wheel.filename)) != wheel.sha256:
                raise ValueError("Staged wheel changed during consumer")
        return {
            "installed": inventory,
            "child": origins,
            "test_counts": counts,
            "return_codes": {
                "create": created.returncode,
                "install": installed.returncode,
                "pip_check": checked.returncode,
                "imports": imported.returncode,
                "pytest": tested.returncode,
            },
            "consumer_policy_id": CONSUMER,
        }


def replay(inputs: ReplayInputs, manifest_sha256: str) -> str:
    checked_digest(manifest_sha256)
    checked_path(inputs.report_dir, directory=True)
    archive = LocalRawArchive(inputs.report_dir)
    payload = archive.get(manifest_sha256)
    manifest = decode_manifest(payload)
    local = mapping(manifest["local_wheel"], {"filename", "name", "version", "size", "sha256"})
    expected_lock = checked_digest(manifest["lock_sha256"])
    expected_local = checked_digest(local["sha256"])
    prepared = prepare(inputs, expected_lock, expected_local)
    if canonical(prepared.manifest) != payload:
        raise ValueError("Reopened input manifest differs from actual inputs/platform/source")
    report = offline_consumer(inputs, prepared)
    if canonical(prepare(inputs, expected_lock, expected_local).manifest) != payload:
        raise ValueError("Input identity changed during consumer")
    report.update(
        schema_version=1,
        policy_id="offline-locked-toolchain-replay-report-v1",
        input_manifest_sha256=manifest_sha256,
    )
    return publish(archive, report)


def download_locked_wheels(lock: Path, destination: Path) -> None:
    """Separate networked materialization from an explicit public index, not replay."""
    requirements = parse_lock(
        read_regular(lock), {key: text(value) for key, value in default_environment().items()}
    )
    locked = {item.name: item.version for item in requirements}
    for name in ("pip", "packaging"):
        if name not in locked or Version(importlib.metadata.version(name)) != Version(locked[name]):
            raise ValueError("Host materialization tool differs from active lock")
    if (
        not isinstance(destination, Path)
        or not destination.is_absolute()
        or ".." in destination.parts
    ):
        raise ValueError("Destination must be an absolute new directory")
    checked_path(destination.parent, directory=True)
    destination.mkdir()
    argv = [
        sys.executable,
        "-I",
        "-m",
        "pip",
        "--isolated",
        "--disable-pip-version-check",
        "--no-input",
        "download",
        "--require-hashes",
        "--only-binary=:all:",
        "--no-cache-dir",
        "--keyring-provider",
        "disabled",
        "--index-url",
        "https://pypi.org/simple",
        "--dest",
        str(destination),
        "-r",
        str(lock),
    ]
    require_success(run(argv, cwd=destination.parent))


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "replay"):
        command = commands.add_parser(name)
        for argument in ("wheelhouse", "local-wheel", "lock", "source-root", "report-dir"):
            command.add_argument(f"--{argument}", type=Path, required=True)
        if name == "capture":
            command.add_argument("--expected-lock-sha256", required=True)
            command.add_argument("--expected-local-wheel-sha256", required=True)
        else:
            command.add_argument("--manifest-sha256", required=True)
    arguments = parser.parse_args()
    inputs = ReplayInputs(
        arguments.wheelhouse,
        arguments.local_wheel,
        arguments.lock,
        arguments.source_root,
        arguments.report_dir,
    )
    result = (
        capture(inputs, arguments.expected_lock_sha256, arguments.expected_local_wheel_sha256)
        if arguments.command == "capture"
        else replay(inputs, arguments.manifest_sha256)
    )
    print(f"{arguments.command.upper()} SHA256 {result}")


if __name__ == "__main__":
    cli()
