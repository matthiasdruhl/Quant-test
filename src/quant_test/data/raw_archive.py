"""Checksum-verified local raw bytes; trusted local filesystem, no durability claim.

The root must already exist. Callers own it and must exclude hostile/concurrent
filesystem mutation. Objects are immutable through this API, not tamperproof.
Only local POSIX filesystems supporting no-replace hard links are supported.
"""

import errno
import hashlib
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from re import fullmatch

from quant_test.data.versions import ObservationVersion


class RawArchiveError(Exception):
    """Base error for raw-byte storage failures."""


class PayloadDigestMismatchError(RawArchiveError):
    """Supplied bytes do not match the requested digest; nothing was written."""


class PayloadMissingError(RawArchiveError):
    """The requested object does not exist; no substitute is returned."""


class PayloadCorruptError(RawArchiveError):
    """An object is unsafe, is not a regular file, or fails checksum verification."""


class ArchiveIOError(RawArchiveError):
    """Filesystem failure, possibly after publication of a complete object.

    In particular, failed temporary-file cleanup can follow successful publication.
    Retrying the same put verifies an existing object before reporting success.
    """


def _require_digest(value: str) -> None:
    if not isinstance(value, str) or fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("content_sha256 must be a lowercase SHA-256 hex digest")


def _require_version(value: ObservationVersion) -> None:
    if not isinstance(value, ObservationVersion):
        raise ValueError("version must be an ObservationVersion")


class LocalRawArchive:
    """A flat archive keyed only by exact lowercase SHA-256 digests.

    No observation metadata, timestamps, revision index, or processing status is
    persisted. Select the historical version first, then call get_version; a
    missing/corrupt selected payload raises and must never trigger fallback.
    """

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or ".." in root.parts:
            raise ValueError("root must be an absolute Path without '..' components")
        self._root = root
        with self._directory():
            pass

    @contextmanager
    def _directory(self) -> Iterator[int]:
        try:
            # The trusted-root assumption excludes races during these checks.
            for component in (*reversed(self._root.parents), self._root):
                if stat.S_ISLNK(component.lstat().st_mode):
                    raise ArchiveIOError("archive root must not contain symlink components")
            directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                yield directory
            finally:
                os.close(directory)
        except OSError as error:
            raise ArchiveIOError("raw archive filesystem operation failed") from error

    @staticmethod
    def _read(directory: int, name: str, digest: str) -> bytes:
        try:
            metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError as error:
            raise PayloadMissingError(f"raw payload missing: {digest}") from error
        if not stat.S_ISREG(metadata.st_mode):
            raise PayloadCorruptError(f"raw payload is not a regular file: {digest}")
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise PayloadCorruptError(f"raw payload is not a regular file: {digest}")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read()
        finally:
            os.close(descriptor)
        if hashlib.sha256(payload).hexdigest() != digest:
            raise PayloadCorruptError(f"raw payload checksum failed: {digest}")
        return payload

    def get(self, content_sha256: str) -> bytes:
        """Read exact bytes only after verifying their digest; never return fallback."""
        _require_digest(content_sha256)
        with self._directory() as directory:
            return self._read(directory, content_sha256, content_sha256)

    def put(self, content_sha256: str, payload: bytes) -> None:
        """Verify, stage, verify again, and publish without replacing an object.

        Existing objects must verify and equal the supplied bytes. Hard-link
        publication exposes only a complete staged file. No fsync is performed;
        process/power failure durability is outside this contract.
        """
        _require_digest(content_sha256)
        if type(payload) is not bytes:
            raise ValueError("payload must be immutable bytes")
        if hashlib.sha256(payload).hexdigest() != content_sha256:
            raise PayloadDigestMismatchError("payload does not match content_sha256")
        with self._directory() as directory:
            try:
                existing = self._read(directory, content_sha256, content_sha256)
            except PayloadMissingError:
                existing = None
            if existing is not None:
                if existing != payload:
                    raise PayloadCorruptError("existing payload differs despite matching digest")
                return
            temporary = f".staging-{secrets.token_hex(16)}"
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            try:
                try:
                    remaining = memoryview(payload)
                    while remaining:
                        written = os.write(descriptor, remaining)
                        if written <= 0:
                            raise OSError(errno.EIO, "raw archive write made no progress")
                        remaining = remaining[written:]
                    os.fchmod(descriptor, 0o400)
                finally:
                    os.close(descriptor)
                staged = self._read(directory, temporary, content_sha256)
                if staged != payload:
                    raise PayloadCorruptError("staged payload differs despite matching digest")
                try:
                    os.link(
                        temporary,
                        content_sha256,
                        src_dir_fd=directory,
                        dst_dir_fd=directory,
                        follow_symlinks=False,
                    )
                except FileExistsError as error:
                    if self._read(directory, content_sha256, content_sha256) != payload:
                        raise PayloadCorruptError(
                            "existing payload differs despite matching digest"
                        ) from error
            finally:
                os.unlink(temporary, dir_fd=directory)

    def put_version(self, version: ObservationVersion, payload: bytes) -> None:
        """Archive bytes under exactly this validated version's content checksum."""
        _require_version(version)
        self.put(version.content_sha256, payload)

    def get_version(self, version: ObservationVersion) -> bytes:
        """Read exactly this version's bytes without changing version eligibility."""
        _require_version(version)
        return self.get(version.content_sha256)
