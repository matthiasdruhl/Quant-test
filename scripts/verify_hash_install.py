"""Offline acceptance check using the repository's built, dependency-free wheel.

Run with the baseline interpreter and uv 0.13.5:
    python scripts/verify_hash_install.py dist/quant_test-0.1.0-py3-none-any.whl
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


def main(wheel: Path) -> None:
    version = run("uv", "--version")
    require_success(version)
    if version.stdout.split()[:2] != ["uv", "0.13.5"]:
        raise RuntimeError(f"Expected uv 0.13.5, got {version.stdout.strip()}")
    wheel = wheel.resolve(strict=True)
    if not wheel.name.startswith("quant_test-") or wheel.suffix != ".whl":
        raise ValueError("Supply the built quant-test wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    invalid_digest = ("1" if digest[0] == "0" else "0") + digest[1:]
    package_version = wheel.name.split("-")[1]

    with TemporaryDirectory(prefix="quant-hash-install-") as directory:
        root = Path(directory)
        wheelhouse = root / "wheelhouse"
        wheelhouse.mkdir()
        shutil.copyfile(wheel, wheelhouse / wheel.name)
        environment = root / "venv"
        require_success(
            run(
                "uv",
                "venv",
                "--offline",
                "--no-cache",
                "--no-config",
                "--no-python-downloads",
                "--python",
                sys.executable,
                str(environment),
            )
        )
        python = str(environment / "bin" / "python")
        require_success(
            run(
                python,
                "-c",
                "from importlib.metadata import distributions; "
                "raise SystemExit(bool(list(distributions())))",
            )
        )
        requirements = root / "requirements.txt"
        command = (
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-index",
            "--no-cache",
            "--no-config",
            "--find-links",
            str(wheelhouse),
            "--require-hashes",
            "--only-binary=:all:",
            "--reinstall",
            "-r",
            str(requirements),
        )

        def write_requirement(hash_value: str) -> None:
            requirements.write_text(
                f"quant-test=={package_version} --hash=sha256:{hash_value}\n", encoding="utf-8"
            )

        write_requirement(digest)
        require_success(run(*command))
        require_success(run(python, "-c", "import quant_test.core.time"))
        write_requirement(invalid_digest)
        rejected = run(*command)
        if rejected.returncode == 0 or "Hash mismatch" not in rejected.stderr:
            raise RuntimeError(
                "Invalid hash was not rejected for the preinstalled package:\n"
                + rejected.stdout
                + rejected.stderr
            )
        write_requirement(digest)
        require_success(run(*command))
        require_success(run(python, "-c", "import quant_test.core.time"))
    print(
        "PASS: empty environment; preinstalled package rejects wrong hash; valid reinstall succeeds"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/verify_hash_install.py PATH_TO_QUANT_TEST_WHEEL")
    main(Path(sys.argv[1]))
