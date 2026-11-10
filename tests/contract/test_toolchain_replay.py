"""Verifier parsing/preflight/failure references; no fake ZIP is installed.

The complete real positive consumer is a separate explicit CI command, never
recursively invoked by this suite. Process doubles establish sequencing only.
"""

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from quant_test.data.raw_archive import ArchiveIOError, PayloadCorruptError, PayloadMissingError

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "verify_toolchain_replay.py"
SPEC = importlib.util.spec_from_file_location("quant_toolchain_verifier_tests", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)

MARKERS = {
    "implementation_name": "cpython",
    "implementation_version": "3.11.17",
    "os_name": "posix",
    "platform_machine": "arm64",
    "platform_release": "reference",
    "platform_system": "Darwin",
    "platform_version": "reference",
    "python_full_version": "3.11.17",
    "platform_python_implementation": "CPython",
    "python_version": "3.11",
    "sys_platform": "darwin",
}
HOST = {
    "python_implementation": "CPython",
    "python_version": "3.11.17",
    "python_build": ["reference", "reference"],
    "python_compiler": "reference",
    "python_cache_tag": "cpython-311",
    "python_executable_sha256": "0" * 64,
    "system": "Darwin",
    "release": "reference",
    "platform_version": "reference",
    "machine": "arm64",
    "marker_environment": MARKERS,
    "host_tools": {"pip": "26.3", "packaging": "26.3"},
    "uv_version": "uv 0.13.5 (reference)",
    "uv_executable_sha256": "1" * 64,
    "uv_provenance_limitation": None,
}
CHILD_FIELDS = {
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
FIXTURE = ROOT / "tests" / "fixtures" / "toolchain-input-manifest-v1.json"
MANIFEST_SHA = "d7996e5b81a478ce6fd21679df59b4c24dcc2e288597661edea5078b26217c3f"


def canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def wheel_bytes(
    name: str,
    version: str,
    *,
    tags: str = "py3-none-any",
    metadata_name: str | None = None,
    metadata_version: str | None = None,
    declared_tag: str | None = None,
    requires_python: str = ">=3.11",
    extra_members: dict[str, bytes] | None = None,
) -> bytes:
    """Independent deterministic minimal ZIP unit fixture, never actual lock evidence."""
    metadata = (
        f"Metadata-Version: 2.4\nName: {metadata_name or name}\nVersion: {metadata_version or version}\n"
        f"Requires-Python: {requires_python}\n\n"
    ).encode("ascii")
    wheel = (
        "Wheel-Version: 1.0\nRoot-Is-Purelib: true\n" + f"Tag: {declared_tag or tags}\n\n"
    ).encode("ascii")
    prefix = f"{name.replace('-', '_')}-{version}.dist-info"
    contents = {f"{prefix}/METADATA": metadata, f"{prefix}/WHEEL": wheel, f"{prefix}/RECORD": b""}
    contents.update(extra_members or {})
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for filename, payload in contents.items():
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return output.getvalue()


@pytest.fixture
def unit_inputs(tmp_path: Path, monkeypatch: Any) -> Any:
    """Synthetic parsing/preflight only: clean Git and host observations are doubles."""
    base = tmp_path.resolve()
    wheelhouse, source, reports = base / "wheels", base / "source", base / "reports"
    for directory in (wheelhouse, source, reports):
        directory.mkdir()
    (source / "tests").mkdir()
    (source / ".python-version").write_text("3.11.17\n")
    (source / "pyproject.toml").write_text('[project]\nname="quant-test"\nversion="0.1.0"\n')
    records = []
    for name in ("packaging", "pip"):
        payload = wheel_bytes(name, "26.3")
        (wheelhouse / f"{name}-26.3-py3-none-any.whl").write_bytes(payload)
        records.append(f"{name}==26.3 --hash=sha256:{hashlib.sha256(payload).hexdigest()}\n")
    lock = base / "requirements.lock"
    lock.write_text("".join(records))
    (source / "requirements-dev.lock").write_bytes(lock.read_bytes())
    local = base / "quant_test-0.1.0-py3-none-any.whl"
    local.write_bytes(wheel_bytes("quant-test", "0.1.0"))
    monkeypatch.setattr(verifier, "default_environment", lambda: copy.deepcopy(MARKERS))
    monkeypatch.setattr(verifier, "host_observation", lambda *_: copy.deepcopy(HOST))
    monkeypatch.setattr(verifier, "source_revision", lambda *_: "a" * 40)
    return verifier.ReplayInputs(wheelhouse, local, lock, source, reports)


def prepare(inputs: Any) -> Any:
    return verifier.prepare(
        inputs,
        hashlib.sha256(inputs.lock.read_bytes()).hexdigest(),
        hashlib.sha256(inputs.local_wheel.read_bytes()).hexdigest(),
    )


def capture(inputs: Any) -> str:
    return verifier.capture(
        inputs,
        hashlib.sha256(inputs.lock.read_bytes()).hexdigest(),
        hashlib.sha256(inputs.local_wheel.read_bytes()).hexdigest(),
    )


def forbidden(*args: Any, **kwargs: Any) -> Any:
    pytest.fail("invalid input reached installation/consumer")


def test_independent_literal_manifest_bytes_hash_capture_and_readback(unit_inputs: Any) -> None:
    # Fixed synthetic host/ZIP identities test representation, not actual replay success.
    expected = FIXTURE.read_bytes()
    assert hashlib.sha256(expected).hexdigest() == MANIFEST_SHA
    prepared = prepare(unit_inputs)
    assert verifier.canonical(prepared.manifest) == expected
    assert verifier.decode_manifest(expected) == json.loads(expected)
    assert capture(unit_inputs) == MANIFEST_SHA
    assert capture(unit_inputs) == MANIFEST_SHA
    assert (unit_inputs.report_dir / MANIFEST_SHA).read_bytes() == expected
    assert set(unit_inputs.report_dir.iterdir()) == {unit_inputs.report_dir / MANIFEST_SHA}


def test_active_markers_continuations_and_allowed_hashes() -> None:
    payload = (
        "# literal marker reference\n"
        "demo==1.2 ; sys_platform == 'darwin' \\\n"
        "    --hash=sha256:" + "a" * 64 + " \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n"
        "colorama==0.4.6 ; sys_platform == 'win32' --hash=sha256:" + "c" * 64 + "\n"
        "librt==0.16.0 ; platform_python_implementation != 'PyPy' --hash=sha256:" + "d" * 64 + "\n"
    ).encode()
    parsed = verifier.parse_lock(payload, MARKERS)
    assert [(r.name, r.version, r.hashes) for r in parsed] == [
        ("demo", "1.2", ("a" * 64, "b" * 64)),
        ("librt", "0.16.0", ("d" * 64,)),
    ]


@pytest.mark.parametrize(
    "requirement",
    [
        "demo>=1",
        "demo==1.*",
        "demo[extra]==1",
        "demo @ https://example.invalid/a.whl",
        "-e .",
        "-r another.lock",
        "--index-url https://example.invalid",
        "./demo.whl",
        "demo==1 --config-settings=unsafe",
        "demo==1 --hash=sha512:" + "a" * 64,
    ],
)
def test_unsupported_lock_subset_fails(requirement: str) -> None:
    with pytest.raises(ValueError):
        verifier.parse_lock((requirement + " --hash=sha256:" + "a" * 64 + "\n").encode(), MARKERS)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"# comment\n",
        b"demo==1\n",
        b"demo==1 --hash=sha256:ABC\n",
        b"demo==1 \\\n",
        b"demo==1 \\\n# interrupted\n",
        b"\xff",
        (
            "demo==1 --hash=sha256:" + "a" * 64 + "\ndemo==1 --hash=sha256:" + "b" * 64 + "\n"
        ).encode(),
    ],
)
def test_malformed_empty_or_duplicate_active_lock_fails(payload: bytes) -> None:
    with pytest.raises(ValueError):
        verifier.parse_lock(payload, MARKERS)


@pytest.mark.parametrize(
    "kind", ["missing", "extra", "duplicate", "sdist", "directory", "symlink", "fifo"]
)
def test_whole_wheelhouse_fails_before_consumer(
    unit_inputs: Any, monkeypatch: Any, kind: str
) -> None:
    file = unit_inputs.wheelhouse / "pip-26.3-py3-none-any.whl"
    if kind == "missing":
        file.unlink()
    elif kind == "extra":
        (unit_inputs.wheelhouse / "extra-1-py3-none-any.whl").write_bytes(wheel_bytes("extra", "1"))
    elif kind == "duplicate":
        (unit_inputs.wheelhouse / "pip-26.3-1-py3-none-any.whl").write_bytes(file.read_bytes())
    elif kind == "sdist":
        (unit_inputs.wheelhouse / "pip-26.3.tar.gz").write_bytes(b"not a wheel")
    elif kind == "directory":
        (unit_inputs.wheelhouse / "nested").mkdir()
    elif kind == "symlink":
        file.unlink()
        file.symlink_to(unit_inputs.local_wheel)
    else:
        file.unlink()
        os.mkfifo(file)
    monkeypatch.setattr(verifier, "offline_consumer", forbidden)
    with pytest.raises(ValueError):
        prepare(unit_inputs)
    assert list(unit_inputs.report_dir.iterdir()) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"metadata_name": "other"},
        {"metadata_version": "99"},
        {"declared_tag": "py2-none-any"},
        {"requires_python": ">=99"},
        {"extra_members": {"../escape": b"x"}},
    ],
)
def test_metadata_contradiction_or_unsafe_zip_rejects(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    path = tmp_path.resolve() / "demo-1-py3-none-any.whl"
    path.write_bytes(wheel_bytes("demo", "1", **changes))
    with pytest.raises(ValueError):
        verifier.inspect_wheel(path)


def test_filename_compatibility_does_not_override_wheel_tag_metadata(tmp_path: Path) -> None:
    path = tmp_path.resolve() / "demo-1-py3-none-any.whl"
    path.write_bytes(wheel_bytes("demo", "1", declared_tag="py311-none-any"))
    with pytest.raises(ValueError, match="Tag metadata"):
        verifier.inspect_wheel(path)
    incompatible = tmp_path.resolve() / "demo-1-cp999-cp999-impossible.whl"
    incompatible.write_bytes(wheel_bytes("demo", "1", tags="cp999-cp999-impossible"))
    with pytest.raises(ValueError, match="incompatible"):
        verifier.inspect_wheel(incompatible)


def test_duplicate_zip_member_and_mismatched_metadata_directory_fail(tmp_path: Path) -> None:
    path = tmp_path.resolve() / "demo-1-py3-none-any.whl"
    payload = BytesIO(wheel_bytes("demo", "1"))
    with zipfile.ZipFile(payload, "a") as archive:
        with pytest.warns(UserWarning, match="Duplicate"):
            archive.writestr("demo-1.dist-info/METADATA", b"Name: demo\nVersion: 1\n")
    path.write_bytes(payload.getvalue())
    with pytest.raises(ValueError, match="Duplicate"):
        verifier.inspect_wheel(path)
    path.write_bytes(wheel_bytes("different", "1"))
    with pytest.raises(ValueError, match="dist-info"):
        verifier.inspect_wheel(path)


def test_missing_required_metadata_or_corrupt_zip_fails(tmp_path: Path) -> None:
    path = tmp_path.resolve() / "demo-1-py3-none-any.whl"
    path.write_bytes(b"not a ZIP")
    with pytest.raises(zipfile.BadZipFile):
        verifier.inspect_wheel(path)
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("demo/__init__.py", b"")
    path.write_bytes(output.getvalue())
    with pytest.raises(ValueError, match="METADATA"):
        verifier.inspect_wheel(path)


def test_lock_expected_hash_allowed_hash_and_local_expected_hash_are_independent(
    unit_inputs: Any,
) -> None:
    lock_hash = hashlib.sha256(unit_inputs.lock.read_bytes()).hexdigest()
    local_hash = hashlib.sha256(unit_inputs.local_wheel.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Pinned lock"):
        verifier.prepare(unit_inputs, "0" * 64, local_hash)
    with pytest.raises(ValueError, match="Pinned local"):
        verifier.prepare(unit_inputs, lock_hash, "0" * 64)
    # A new expected lock digest does not authorize a wheel absent from allowed hashes.
    text = unit_inputs.lock.read_text()
    actual = hashlib.sha256(
        (unit_inputs.wheelhouse / "pip-26.3-py3-none-any.whl").read_bytes()
    ).hexdigest()
    unit_inputs.lock.write_text(text.replace(actual, "0" * 64))
    (unit_inputs.source_root / "requirements-dev.lock").write_bytes(unit_inputs.lock.read_bytes())
    with pytest.raises(ValueError, match="version/hash"):
        prepare(unit_inputs)


@pytest.mark.parametrize("change", ["lock", "local", "dependency", "missing", "source", "platform"])
def test_replay_rechecks_every_captured_input_before_install(
    unit_inputs: Any, monkeypatch: Any, change: str
) -> None:
    sha = capture(unit_inputs)
    if change == "lock":
        unit_inputs.lock.write_bytes(unit_inputs.lock.read_bytes() + b"# changed\n")
    elif change == "local":
        unit_inputs.local_wheel.write_bytes(unit_inputs.local_wheel.read_bytes() + b"changed")
    elif change == "dependency":
        path = unit_inputs.wheelhouse / "pip-26.3-py3-none-any.whl"
        path.write_bytes(path.read_bytes() + b"changed")
    elif change == "missing":
        (unit_inputs.wheelhouse / "pip-26.3-py3-none-any.whl").unlink()
    elif change == "source":
        monkeypatch.setattr(verifier, "source_revision", lambda *_: "b" * 40)
    else:
        monkeypatch.setattr(
            verifier, "host_observation", lambda *_: dict(HOST, machine="different")
        )
    monkeypatch.setattr(verifier, "offline_consumer", forbidden)
    with pytest.raises((ValueError, OSError)):
        verifier.replay(unit_inputs, sha)
    assert len(list(unit_inputs.report_dir.iterdir())) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version=2),
        lambda d: d.update(policy_id="unknown"),
        lambda d: d.update(consumer_policy_id="unknown"),
        lambda d: d.update(extra=None),
        lambda d: d.pop("host"),
        lambda d: d.update(lock_sha256="A" * 64),
        lambda d: d.update(source_revision="not-a-commit"),
        lambda d: d.update(active_requirements={}),
        lambda d: d["active_requirements"].reverse(),
        lambda d: d["dependency_wheels"].append(d["dependency_wheels"][0].copy()),
        lambda d: d["dependency_wheels"][0].update(size=True),
        lambda d: d["dependency_wheels"][0].update(size=-1),
        lambda d: d["dependency_wheels"][0].update(filename="../escape.whl"),
        lambda d: d["dependency_wheels"][0].update(filename="other-26.3-py3-none-any.whl"),
        lambda d: d["dependency_wheels"][0].update(version="26.4"),
        lambda d: d["active_requirements"][0].update(name=" "),
        lambda d: d["local_wheel"].update(extra=None),
        lambda d: d.update(local_wheel=d["dependency_wheels"][0].copy()),
        lambda d: d["host"].update(extra=None),
        lambda d: d["host"].update(python_build=[True]),
        lambda d: d["host"]["marker_environment"].update(extra="injected"),
        lambda d: d["host"]["host_tools"].update(pip=None),
        lambda d: d["host"].update(uv_executable_sha256=None),
    ],
)
def test_rehashed_schema_type_identity_tampers_reject_before_preflight(
    unit_inputs: Any, monkeypatch: Any, mutation: Any
) -> None:
    document = json.loads(FIXTURE.read_bytes())
    mutation(document)
    payload = canonical(document)
    sha = hashlib.sha256(payload).hexdigest()
    (unit_inputs.report_dir / sha).write_bytes(payload)
    monkeypatch.setattr(verifier, "prepare", forbidden)
    with pytest.raises(ValueError):
        verifier.replay(unit_inputs, sha)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b + b"\n",
        lambda b: b" " + b,
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
        lambda b: b.replace(b'"size":', b'"size":0,"size":', 1),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":1.0'),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":NaN'),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":Infinity'),
        lambda b: b"[]",
        lambda b: b"\xff",
    ],
)
def test_noncanonical_duplicate_or_invalid_json_rejects(mutate: Any) -> None:
    with pytest.raises(ValueError):
        verifier.decode_manifest(mutate(FIXTURE.read_bytes()))


def test_manifest_missing_corrupt_and_post_consumer_input_change_never_publish_success(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    sha = capture(unit_inputs)
    path = unit_inputs.report_dir / sha
    payload = path.read_bytes()
    path.unlink()
    with pytest.raises(PayloadMissingError):
        verifier.replay(unit_inputs, sha)
    path.write_bytes(b"corrupt")
    with pytest.raises(PayloadCorruptError):
        verifier.replay(unit_inputs, sha)
    path.write_bytes(payload)

    def changed(*args: Any) -> dict[str, object]:
        unit_inputs.lock.write_bytes(unit_inputs.lock.read_bytes() + b"# changed after consumer\n")
        return {"test_counts": {"tests": 1, "passed": 1}}

    monkeypatch.setattr(verifier, "offline_consumer", changed)
    with pytest.raises(ValueError, match="lock digest"):
        verifier.replay(unit_inputs, sha)
    assert list(unit_inputs.report_dir.iterdir()) == [path]


def test_source_git_checks_are_readonly_and_dirty_or_nested_roots_reject(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = tmp_path.resolve()
    calls = []

    def git(argv: list[str], **kwargs: Any) -> Any:
        calls.append(argv)
        if "--show-toplevel" in argv:
            return subprocess.CompletedProcess(argv, 0, str(root) + "\n", "")
        if "rev-parse" in argv:
            return subprocess.CompletedProcess(argv, 0, "a" * 40 + "\n", "")
        return subprocess.CompletedProcess(argv, 0, "?? untracked\n", "")

    monkeypatch.setattr(verifier, "run", git)
    with pytest.raises(ValueError, match="dirty"):
        verifier.source_revision(root)
    assert all(argv[:3] == ["git", "-C", str(root)] for argv in calls)
    assert verifier.controlled_environment()["GIT_OPTIONAL_LOCKS"] == "0"
    monkeypatch.setattr(
        verifier,
        "run",
        lambda argv, **_: subprocess.CompletedProcess(argv, 0, str(root.parent) + "\n", ""),
    )
    with pytest.raises(ValueError, match="checkout root"):
        verifier.source_revision(root)


@pytest.mark.parametrize(
    "kind", ["relative", "dotdot", "symlink-component", "symlink-file", "directory", "fifo"]
)
def test_regular_path_boundary_rejects_unsafe_inputs(tmp_path: Path, kind: str) -> None:
    root = tmp_path.resolve()
    file = root / "input"
    file.write_bytes(b"abc")
    if kind == "relative":
        path = Path("input")
    elif kind == "dotdot":
        path = root / ".." / root.name / "input"
    elif kind == "symlink-component":
        linked = root / "linked"
        linked.symlink_to(root, target_is_directory=True)
        path = linked / "input"
    elif kind == "symlink-file":
        path = root / "link"
        path.symlink_to(file)
    elif kind == "directory":
        path = root
    else:
        path = root / "fifo"
        os.mkfifo(path)
    with pytest.raises(ValueError):
        verifier.read_regular(path)


def test_controlled_environment_strips_ambient_credentials_options_and_paths(
    monkeypatch: Any,
) -> None:
    names = [
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "UV_NO_VERIFY_HASHES",
        "UV_VENV_SEED",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "HTTP_PROXY",
        "https_proxy",
        "ALL_PROXY",
        "GIT_INDEX_FILE",
    ]
    for name in names:
        monkeypatch.setenv(name, "synthetic-test-marker")
    result = verifier.controlled_environment()
    assert not set(names).intersection(result)
    assert result["NETRC"] == result["PIP_CONFIG_FILE"] == os.devnull
    assert result.get("HOME") == os.environ.get("HOME")
    assert result.get("PATH") == os.environ.get("PATH")


def test_run_subprocess_uses_argument_array_controlled_environment_no_shell(
    monkeypatch: Any,
) -> None:
    observed = {}

    def process(argv: list[str], **kwargs: Any) -> Any:
        observed.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(verifier.subprocess, "run", process)
    verifier.run(["literal-tool", "literal-argument"])
    assert observed["argv"] == ["literal-tool", "literal-argument"]
    assert "shell" not in observed
    assert observed["env"]["NETRC"] == os.devnull


@pytest.mark.parametrize("name", ["pip", "packaging"])
def test_observed_host_tools_must_match_active_lock(
    unit_inputs: Any, monkeypatch: Any, name: str
) -> None:
    # Call the original host function despite the fixture's synthetic observation double.
    host_function = SPEC.loader  # keep the independent module loader explicit below
    assert host_function is not None
    isolated_spec = importlib.util.spec_from_file_location("quant_toolchain_host_probe", SCRIPT)
    assert isolated_spec is not None and isolated_spec.loader is not None
    module = importlib.util.module_from_spec(isolated_spec)
    sys.modules[isolated_spec.name] = module
    isolated_spec.loader.exec_module(module)
    actual_version = module.importlib.metadata.version
    monkeypatch.setattr(
        module.importlib.metadata,
        "version",
        lambda package: "999" if package == name else actual_version(package),
    )
    requirements = verifier.parse_lock(unit_inputs.lock.read_bytes(), MARKERS)
    with pytest.raises(ValueError, match="version differs"):
        module.host_observation(requirements, unit_inputs.source_root)


def test_unexpected_uv_version_rejects_before_consumer(unit_inputs: Any, monkeypatch: Any) -> None:
    isolated_spec = importlib.util.spec_from_file_location("quant_toolchain_uv_probe", SCRIPT)
    assert isolated_spec is not None and isolated_spec.loader is not None
    module = importlib.util.module_from_spec(isolated_spec)
    sys.modules[isolated_spec.name] = module
    isolated_spec.loader.exec_module(module)
    monkeypatch.setattr(
        module, "run", lambda argv, **_: subprocess.CompletedProcess(argv, 0, "uv 0.0.0\n", "")
    )
    requirements = verifier.parse_lock(unit_inputs.lock.read_bytes(), MARKERS)
    with pytest.raises(ValueError, match="uv version"):
        module.host_observation(requirements, unit_inputs.source_root)


@pytest.mark.parametrize(
    "records",
    [
        [{"name": "demo", "version": "1", "editable": True}],
        [
            {"name": "my-demo", "version": "1", "editable": False},
            {"name": "my_demo", "version": "1", "editable": False},
        ],
        [{"name": "demo", "version": "1", "editable": 0}],
        {},
    ],
)
def test_child_inventory_rejects_editables_duplicates_and_bad_types(
    tmp_path: Path, monkeypatch: Any, records: Any
) -> None:
    monkeypatch.setattr(
        verifier,
        "run",
        lambda argv, **_: subprocess.CompletedProcess(argv, 0, json.dumps(records), ""),
    )
    with pytest.raises(ValueError):
        verifier.child_inventory(Path(sys.executable), tmp_path)


def fake_consumer_processes(
    inputs: Any, prepared: Any, monkeypatch: Any, *, failure: str | None = None
) -> list[list[str]]:
    """Process sequencing double, never complete positive replay acceptance."""
    expected = [
        {"name": wheel.name, "version": wheel.version}
        for wheel in (*prepared.wheels, prepared.local_wheel)
    ]
    expected.sort(key=lambda row: row["name"])
    inventory_calls = 0
    calls = []

    def inventory(*args: Any) -> Any:
        nonlocal inventory_calls
        inventory_calls += 1
        if inventory_calls == 1:
            return expected if failure == "seeded" else []
        if failure == "inventory-extra":
            return expected + [{"name": "unexpected", "version": "1"}]
        if failure == "post-inventory" and inventory_calls > 2:
            return []
        return expected

    def process(argv: list[str], **kwargs: Any) -> Any:
        calls.append(argv)
        stage = (
            "create"
            if argv[1] == "venv"
            else "install"
            if "install" in argv
            else "pip-check"
            if "check" in argv
            else "imports"
            if len(argv) > 2 and argv[2] == "-c"
            else "pytest"
        )
        if failure == stage:
            return subprocess.CompletedProcess(argv, 1, "injected failure", "")
        output = ""
        if stage == "imports":
            observation = {key: HOST[key] for key in CHILD_FIELDS}
            if failure == "child-platform":
                observation["machine"] = "other"
            output = json.dumps(
                {
                    "origins": {
                        "quant_test": "lib/python3.11/site-packages/quant_test/__init__.py"
                    },
                    "environment": observation,
                }
            )
        if stage == "pytest":
            junit = Path(argv[argv.index("--junitxml") + 1])
            junit.write_text(
                '<testsuites><testsuite tests="0" failures="0" errors="0" skipped="0"/></testsuites>'
                if failure == "zero-tests"
                else '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>'
            )
            if failure == "staged-corrupt":
                staged = Path(kwargs["cwd"]) / "wheels" / prepared.wheels[0].filename
                staged.write_bytes(b"changed")
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr(verifier, "child_inventory", inventory)
    monkeypatch.setattr(verifier, "run", process)
    return calls


@pytest.mark.parametrize(
    "failure",
    [
        "create",
        "seeded",
        "install",
        "inventory-extra",
        "pip-check",
        "imports",
        "child-platform",
        "pytest",
        "zero-tests",
        "post-inventory",
        "staged-corrupt",
    ],
)
def test_process_or_inventory_failure_never_publishes_success(
    unit_inputs: Any, monkeypatch: Any, failure: str
) -> None:
    sha = capture(unit_inputs)
    prepared = prepare(unit_inputs)
    fake_consumer_processes(unit_inputs, prepared, monkeypatch, failure=failure)
    with pytest.raises((ValueError, RuntimeError)):
        verifier.replay(unit_inputs, sha)
    assert len(list(unit_inputs.report_dir.iterdir())) == 1


def test_process_double_verifies_offline_exact_plan_order_and_report_readback(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    sha = capture(unit_inputs)
    prepared = prepare(unit_inputs)
    calls = fake_consumer_processes(unit_inputs, prepared, monkeypatch)
    report = verifier.replay(unit_inputs, sha)
    document = json.loads((unit_inputs.report_dir / report).read_bytes())
    assert document["input_manifest_sha256"] == sha
    assert document["test_counts"] == {
        "tests": 3,
        "passed": 3,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    assert calls[0][1] == "venv" and "--seed" not in calls[0]
    install = next(argv for argv in calls if "install" in argv)
    for flag in (
        "--offline",
        "--no-index",
        "--no-cache",
        "--no-config",
        "--no-python-downloads",
        "--only-binary=:all:",
        "--require-hashes",
        "--reinstall",
        "--strict",
    ):
        assert flag in install
    assert "--no-build" not in install  # Alias conflicts with --only-binary in uv 0.13.5.
    suite = next(argv for argv in calls if "pytest" in argv)
    assert "-I" in suite and "--import-mode=importlib" in suite
    assert str(unit_inputs.source_root / "tests") in suite
    # This report uses doubled processes/counts; only the separate real command establishes acceptance.


def test_supplied_lock_must_match_clean_source_lock_and_identical_copy_is_allowed(
    unit_inputs: Any,
) -> None:
    assert (
        prepare(unit_inputs).manifest["lock_sha256"]
        == hashlib.sha256(unit_inputs.lock.read_bytes()).hexdigest()
    )
    source_lock = unit_inputs.source_root / "requirements-dev.lock"
    source_lock.write_bytes(source_lock.read_bytes() + b"# different checked revision\n")
    with pytest.raises(ValueError, match="checked source"):
        prepare(unit_inputs)


@pytest.mark.parametrize("name,version", [("wrong-project", "0.1.0"), ("quant-test", "99")])
def test_local_wheel_identity_rejects_even_with_matching_caller_hash(
    unit_inputs: Any, name: str, version: str
) -> None:
    path = unit_inputs.local_wheel.parent / f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
    path.write_bytes(wheel_bytes(name, version))
    changed = verifier.ReplayInputs(
        unit_inputs.wheelhouse,
        path,
        unit_inputs.lock,
        unit_inputs.source_root,
        unit_inputs.report_dir,
    )
    with pytest.raises(ValueError, match="project identity"):
        prepare(changed)


def test_capture_publication_readback_failure_and_existing_archive_errors_propagate(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ArchiveIOError("injected publication failure")

    monkeypatch.setattr(verifier.LocalRawArchive, "put", fail)
    with pytest.raises(ArchiveIOError, match="publication"):
        capture(unit_inputs)
    assert list(unit_inputs.report_dir.iterdir()) == []
    monkeypatch.undo()


def test_capture_readback_must_equal_exact_published_bytes(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(verifier.LocalRawArchive, "get", lambda *_: b"{}")
    with pytest.raises(ValueError, match="read-back"):
        capture(unit_inputs)
    # The complete manifest may already exist; capture still cannot report success.
    assert len(list(unit_inputs.report_dir.iterdir())) == 1


def test_failed_report_publication_preserves_manifest_and_propagates(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    sha = capture(unit_inputs)
    prepared = prepare(unit_inputs)
    fake_consumer_processes(unit_inputs, prepared, monkeypatch)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ArchiveIOError("injected report publication failure")

    monkeypatch.setattr(verifier.LocalRawArchive, "put", fail)
    with pytest.raises(ArchiveIOError, match="report publication"):
        verifier.replay(unit_inputs, sha)
    assert len(list(unit_inputs.report_dir.iterdir())) == 1


def test_staged_byte_corruption_prevents_environment_creation(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    prepared = prepare(unit_inputs)
    real_write = Path.write_bytes

    def corrupt(path: Path, payload: bytes) -> int:
        return real_write(path, b"corrupt" if path.name == prepared.wheels[0].filename else payload)

    monkeypatch.setattr(Path, "write_bytes", corrupt)
    monkeypatch.setattr(verifier, "run", forbidden)
    with pytest.raises(ValueError, match="Staged wheel"):
        verifier.offline_consumer(unit_inputs, prepared)


@pytest.mark.parametrize(
    "xml",
    [
        "<testsuites/>",
        '<testsuite tests="0"/>',
        '<testsuite tests="1" skipped="1"/>',
        '<testsuite tests="2" failures="1"/>',
        '<testsuite tests="1" errors="1"/>',
        '<testsuite tests="1" skipped="2"/>',
        '<testsuite tests="-1"/>',
    ],
)
def test_junit_requires_actual_positive_pass_count_without_failures(
    tmp_path: Path, xml: str
) -> None:
    path = tmp_path.resolve() / "junit.xml"
    path.write_text(xml)
    with pytest.raises(ValueError):
        verifier.junit_counts(path)


def test_materialization_fixed_public_index_and_exclusive_destination(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    calls = []
    monkeypatch.setattr(
        verifier,
        "run",
        lambda argv, **kwargs: (
            calls.append((argv, kwargs)) or subprocess.CompletedProcess(argv, 0, "", "")
        ),
    )
    destination = unit_inputs.wheelhouse.parent / "download"
    verifier.download_locked_wheels(unit_inputs.lock, destination)
    command = calls[0][0]
    assert command[:4] == [sys.executable, "-I", "-m", "pip"]
    assert command[command.index("--index-url") + 1] == "https://pypi.org/simple"
    assert command[command.index("--keyring-provider") + 1] == "disabled"
    assert (
        "--require-hashes" in command
        and "--only-binary=:all:" in command
        and "--no-cache-dir" in command
    )
    assert "--no-deps" not in command and "--upgrade" not in command
    with pytest.raises(FileExistsError):
        verifier.download_locked_wheels(unit_inputs.lock, destination)
    assert len(calls) == 1


def test_invalid_materialization_lock_rejects_before_process(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    unit_inputs.lock.write_text("pip>=1\n")
    monkeypatch.setattr(verifier, "run", forbidden)
    with pytest.raises(ValueError):
        verifier.download_locked_wheels(
            unit_inputs.lock, unit_inputs.wheelhouse.parent / "download"
        )


def test_actual_isolated_child_probe_executes_observations_for_installed_locked_package(
    tmp_path: Path,
) -> None:
    # Execute the real probe body including platform/hash observations. Narrow
    # only its module tuple to packaging, whose locked installation is available
    # even when this host's quant_test is editable. This is not full replay.
    original = '("quant_test","quant_test.core.time","quant_test.data.raw_archive","quant_test.strategies.targets")'
    assert original in verifier.ORIGIN_CODE
    code = verifier.ORIGIN_CODE.replace(original, '("packaging",)')
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        env=verifier.controlled_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = json.loads(result.stdout)
    assert set(observed["environment"]) == CHILD_FIELDS
    assert observed["environment"]["python_version"] == "3.11.17"
    assert len(observed["environment"]["python_executable_sha256"]) == 64
    assert "site-packages" in observed["origins"]["packaging"]


def test_script_cli_and_explicit_import_layout_work_isolated_outside_checkout(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--help"],
        cwd=tmp_path,
        env=verifier.controlled_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "capture,replay" in result.stdout
    code = (
        "import importlib.util,sys;before=tuple(sys.path);"
        f"spec=importlib.util.spec_from_file_location('probe',{str(SCRIPT)!r});"
        "module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);"
        "assert tuple(sys.path)==before;print(module.POLICY)"
    )
    loaded = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        env=verifier.controlled_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert loaded.returncode == 0, loaded.stderr
    assert loaded.stdout.strip() == "offline-locked-toolchain-replay-v1"


def test_nested_vendored_metadata_is_package_data_not_distribution_identity(tmp_path: Path) -> None:
    path = tmp_path.resolve() / "demo-1-py3-none-any.whl"
    path.write_bytes(
        wheel_bytes(
            "demo",
            "1",
            extra_members={
                "demo/_vendor/other-99.dist-info/METADATA": b"Name: other\nVersion: 99\n",
                "demo/_vendor/other-99.dist-info/WHEEL": b"Wheel-Version: 1.0\nTag: py2-none-any\n",
            },
        )
    )
    inspected = verifier.inspect_wheel(path)
    assert (inspected.name, inspected.version) == ("demo", "1")


def test_additional_top_level_metadata_identity_still_rejects(tmp_path: Path) -> None:
    path = tmp_path.resolve() / "demo-1-py3-none-any.whl"
    path.write_bytes(
        wheel_bytes(
            "demo",
            "1",
            extra_members={
                "other-99.dist-info/METADATA": b"Name: other\nVersion: 99\n",
                "other-99.dist-info/WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\n",
            },
        )
    )
    with pytest.raises(ValueError, match="one METADATA"):
        verifier.inspect_wheel(path)


def test_unexpected_host_python_rejects_before_tools_or_consumer(
    unit_inputs: Any, monkeypatch: Any
) -> None:
    probe_spec = importlib.util.spec_from_file_location("quant_toolchain_python_probe", SCRIPT)
    assert probe_spec is not None and probe_spec.loader is not None
    module = importlib.util.module_from_spec(probe_spec)
    sys.modules[probe_spec.name] = module
    probe_spec.loader.exec_module(module)
    monkeypatch.setattr(module.platform, "python_version", lambda: "3.0.0")
    monkeypatch.setattr(module, "run", forbidden)
    requirements = verifier.parse_lock(unit_inputs.lock.read_bytes(), MARKERS)
    with pytest.raises(ValueError, match="baseline"):
        module.host_observation(requirements, unit_inputs.source_root)


def test_actual_origin_probe_rejects_module_outside_installed_site_packages(tmp_path: Path) -> None:
    original = '("quant_test","quant_test.core.time","quant_test.data.raw_archive","quant_test.strategies.targets")'
    assert original in verifier.ORIGIN_CODE
    # stdlib pathlib is real, but cannot stand in for an installed project module.
    result = subprocess.run(
        [sys.executable, "-I", "-c", verifier.ORIGIN_CODE.replace(original, '("pathlib",)')],
        cwd=tmp_path,
        env=verifier.controlled_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Source or host import fallback" in result.stderr


def test_real_uv_accepts_consumer_flag_combination_without_installing_unit_wheel(
    unit_inputs: Any, monkeypatch: Any, tmp_path: Path
) -> None:
    # Capture the production installer argv through sequencing doubles, then pass
    # its actual flag combination to uv. Only interpreter/plan paths change, and
    # --dry-run prevents installing this minimal parsing-only ZIP unit fixture.
    prepared = prepare(unit_inputs)
    calls = fake_consumer_processes(unit_inputs, prepared, monkeypatch)
    verifier.offline_consumer(unit_inputs, prepared)
    command = next(argv.copy() for argv in calls if "install" in argv)
    assert "--only-binary=:all:" in command and "--no-build" not in command
    wheel = tmp_path.resolve() / "probe_demo-1-py3-none-any.whl"
    payload = wheel_bytes("probe-demo", "1")
    wheel.write_bytes(payload)
    plan = tmp_path.resolve() / "probe-requirements.txt"
    plan.write_text(
        f"{wheel.as_uri()} --hash=sha256:{hashlib.sha256(payload).hexdigest()}\n",
        encoding="ascii",
    )
    command[command.index("--python") + 1] = sys.executable
    command[command.index("-r") + 1] = str(plan)
    command.append("--dry-run")
    inventory_command = [sys.executable, "-I", "-c", verifier.INVENTORY_CODE]
    before = subprocess.run(
        inventory_command,
        cwd=tmp_path,
        env=verifier.controlled_environment(),
        capture_output=True,
        text=True,
        check=True,
    )
    resolved = subprocess.run(
        command,
        cwd=tmp_path,
        env=verifier.controlled_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert resolved.returncode == 0, resolved.stdout + resolved.stderr
    assert "probe-demo" in resolved.stdout + resolved.stderr
    after = subprocess.run(
        inventory_command,
        cwd=tmp_path,
        env=verifier.controlled_environment(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(after.stdout) == json.loads(before.stdout)
    assert not any(item["name"] == "probe-demo" for item in json.loads(after.stdout))
