"""Independent digest vector, exact bytes, temporal composition and filesystem faults."""

import errno
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from quant_test.core.time import InformationAvailability
from quant_test.data import raw_archive
from quant_test.data.raw_archive import (
    ArchiveIOError,
    LocalRawArchive,
    PayloadCorruptError,
    PayloadDigestMismatchError,
    PayloadMissingError,
)
from quant_test.data.versions import ObservationKey, ObservationVersion, VersionCatalog

# Published SHA-256 test vector: ASCII abc, no newline.
ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
KEY = ObservationKey("security-1", "fixture-source", "raw-record")


def version(digest: str, rank: int, usable_hour: int) -> ObservationVersion:
    return ObservationVersion(
        key=KEY,
        version_id=f"revision-{rank}",
        revision_rank=rank,
        availability=InformationAvailability(
            event_at=None,
            published_at=datetime(2025, 1, 3, usable_hour, tzinfo=UTC),
            source_available_at=datetime(2025, 1, 3, usable_hour, tzinfo=UTC),
            ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        source_uri="https://source.example/fixture",
        license_id="test-fixture",
        content_sha256=digest,
        retracted=False,
    )


def test_independent_digest_vector_and_idempotent_reopen(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    archive.put(ABC, b"abc")
    object_path = tmp_path / ABC
    inode = object_path.stat().st_ino
    assert object_path.read_bytes() == b"abc"
    assert archive.get(ABC) == b"abc"
    assert LocalRawArchive(tmp_path).get(ABC) == b"abc"
    archive.put(ABC, b"abc")
    assert object_path.stat().st_ino == inode
    assert list(tmp_path.iterdir()) == [object_path]
    assert object_path.stat().st_mode & 0o222 == 0


@pytest.mark.parametrize("payload", [b"", b"\x00\xff\r\n\xef\xbb\xbf a\t\n", bytes(range(256))])
def test_exact_bytes_preserved_without_decoding_or_normalization(
    tmp_path: Path, payload: bytes
) -> None:
    digest = EMPTY if payload == b"" else hashlib.sha256(payload).hexdigest()
    archive = LocalRawArchive(tmp_path)
    metadata = version(digest, 1, 11)
    archive.put_version(metadata, payload)
    assert archive.get_version(metadata) == payload
    assert (tmp_path / digest).read_bytes() == payload


@pytest.mark.parametrize(
    "digest",
    [
        None,
        123,
        "",
        "A" * 64,
        "../" + "a" * 61,
        "a" * 63,
        "a" * 65,
        "a" * 63 + "\n",
        "/" + "a" * 63,
    ],
)
def test_invalid_digest_cannot_address_files(tmp_path: Path, digest: Any) -> None:
    archive = LocalRawArchive(tmp_path)
    with pytest.raises(ValueError, match="content_sha256"):
        archive.put(digest, b"abc")
    with pytest.raises(ValueError, match="content_sha256"):
        archive.get(digest)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "payload", [None, "abc", bytearray(b"abc"), memoryview(b"abc"), [97, 98, 99]]
)
def test_only_immutable_bytes_are_accepted(tmp_path: Path, payload: Any) -> None:
    with pytest.raises(ValueError, match="immutable bytes"):
        LocalRawArchive(tmp_path).put(ABC, payload)
    assert list(tmp_path.iterdir()) == []


def test_mismatch_is_rejected_before_creating_any_object(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    with pytest.raises(PayloadDigestMismatchError):
        archive.put_version(version(ABC, 1, 11), b"abc\n")
    assert list(tmp_path.iterdir()) == []


def test_missing_object_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(PayloadMissingError):
        LocalRawArchive(tmp_path).get(ABC)


@pytest.mark.parametrize("operation", ["get", "put"])
def test_corrupt_existing_object_is_never_accepted_or_replaced(
    tmp_path: Path, operation: str
) -> None:
    object_path = tmp_path / ABC
    object_path.write_bytes(b"wrong")
    archive = LocalRawArchive(tmp_path)
    with pytest.raises(PayloadCorruptError, match="checksum"):
        if operation == "get":
            archive.get(ABC)
        else:
            archive.put(ABC, b"abc")
    assert object_path.read_bytes() == b"wrong"
    assert list(tmp_path.iterdir()) == [object_path]


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_nonregular_objects_reject_without_following_or_blocking(tmp_path: Path, kind: str) -> None:
    outside = tmp_path / "outside"
    outside.write_bytes(b"abc")
    target = tmp_path / ABC
    if kind == "symlink":
        target.symlink_to(outside)
    elif kind == "directory":
        target.mkdir()
    else:
        os.mkfifo(target)
    archive = LocalRawArchive(tmp_path)
    with pytest.raises(PayloadCorruptError, match="regular file"):
        archive.get(ABC)
    with pytest.raises(PayloadCorruptError, match="regular file"):
        archive.put(ABC, b"abc")
    assert outside.read_bytes() == b"abc"


@pytest.mark.parametrize("root", ["relative", Path("relative"), None, Path("/a/../b")])
def test_invalid_root_input_rejects(root: Any) -> None:
    with pytest.raises(ValueError, match="absolute Path"):
        LocalRawArchive(root)


def test_root_must_exist_and_be_a_directory(tmp_path: Path) -> None:
    with pytest.raises(ArchiveIOError):
        LocalRawArchive(tmp_path / "missing")
    regular = tmp_path / "file"
    regular.write_bytes(b"abc")
    with pytest.raises(ArchiveIOError):
        LocalRawArchive(regular)


def test_root_symlink_and_symlink_ancestor_reject(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "nested").mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    for root in (alias, alias / "nested"):
        with pytest.raises(ArchiveIOError, match="symlink"):
            LocalRawArchive(root)


@pytest.mark.parametrize("invalid", [None, "raw", KEY])
def test_version_methods_require_validated_metadata(tmp_path: Path, invalid: Any) -> None:
    archive = LocalRawArchive(tmp_path)
    with pytest.raises(ValueError, match="ObservationVersion"):
        archive.put_version(invalid, b"abc")
    with pytest.raises(ValueError, match="ObservationVersion"):
        archive.get_version(invalid)


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_late_correction_selects_first_then_missing_or_corrupt_fails_without_fallback(
    tmp_path: Path,
    failure: str,
) -> None:
    first = version(ABC, 1, 11)
    correction = version(EMPTY, 2, 13)
    catalog = VersionCatalog([correction, first])
    archive = LocalRawArchive(tmp_path)
    archive.put_version(first, b"abc")
    assert catalog.latest_usable_at(KEY, datetime(2025, 1, 3, 10, tzinfo=UTC)) is None
    selected = catalog.latest_usable_at(KEY, datetime(2025, 1, 3, 12, tzinfo=UTC))
    assert selected == first
    assert archive.get_version(selected) == b"abc"
    selected = catalog.latest_usable_at(KEY, datetime(2025, 1, 3, 13, tzinfo=UTC))
    assert selected == correction
    if failure == "corrupt":
        (tmp_path / EMPTY).write_bytes(b"not empty")
    with pytest.raises(PayloadMissingError if failure == "missing" else PayloadCorruptError):
        archive.get_version(selected)
    assert archive.get_version(first) == b"abc"
    if failure == "corrupt":
        (tmp_path / EMPTY).unlink()
    archive.put_version(correction, b"")
    assert archive.get_version(selected) == b""


def test_short_writes_complete_before_atomic_publication(tmp_path: Path, monkeypatch: Any) -> None:
    archive = LocalRawArchive(tmp_path)
    real_write, real_link = os.write, os.link

    def short_write(descriptor: int, payload: Any) -> int:
        assert not (tmp_path / ABC).exists()
        return real_write(descriptor, payload[:1])

    def inspect_link(source: str, destination: str, **kwargs: Any) -> None:
        assert (tmp_path / source).read_bytes() == b"abc"
        assert not (tmp_path / ABC).exists()
        real_link(source, destination, **kwargs)

    monkeypatch.setattr(raw_archive.os, "write", short_write)
    monkeypatch.setattr(raw_archive.os, "link", inspect_link)
    archive.put(ABC, b"abc")
    assert archive.get(ABC) == b"abc"


@pytest.mark.parametrize("failure", ["create", "write", "zero_write", "chmod", "link"])
def test_filesystem_failure_does_not_publish_partial_object(
    tmp_path: Path,
    monkeypatch: Any,
    failure: str,
) -> None:
    archive = LocalRawArchive(tmp_path)
    real_open = os.open

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(errno.EIO, "injected filesystem failure")

    def open_fail(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & os.O_CREAT:
            return fail()
        return real_open(path, flags, *args, **kwargs)

    if failure == "create":
        monkeypatch.setattr(raw_archive.os, "open", open_fail)
    elif failure == "zero_write":
        monkeypatch.setattr(raw_archive.os, "write", lambda *args: 0)
    else:
        monkeypatch.setattr(raw_archive.os, {"chmod": "fchmod"}.get(failure, failure), fail)
    with pytest.raises(ArchiveIOError) as caught:
        archive.put(ABC, b"abc")
    assert isinstance(caught.value.__cause__, OSError)
    assert list(tmp_path.iterdir()) == []


def test_staged_bytes_are_verified_before_publication(tmp_path: Path, monkeypatch: Any) -> None:
    real_write = os.write
    monkeypatch.setattr(
        raw_archive.os, "write", lambda descriptor, data: real_write(descriptor, b"bad")
    )
    with pytest.raises(PayloadCorruptError, match="checksum"):
        LocalRawArchive(tmp_path).put(ABC, b"abc")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("competitor_bytes", [b"abc", b"bad"])
def test_no_replace_publication_verifies_object_created_by_competing_writer(
    tmp_path: Path,
    monkeypatch: Any,
    competitor_bytes: bytes,
) -> None:
    real_link = os.link

    def race(source: str, destination: str, **kwargs: Any) -> None:
        (tmp_path / destination).write_bytes(competitor_bytes)
        real_link(source, destination, **kwargs)

    monkeypatch.setattr(raw_archive.os, "link", race)
    archive = LocalRawArchive(tmp_path)
    if competitor_bytes == b"abc":
        archive.put(ABC, b"abc")
    else:
        with pytest.raises(PayloadCorruptError):
            archive.put(ABC, b"abc")
    assert (tmp_path / ABC).read_bytes() == competitor_bytes
    assert list(tmp_path.iterdir()) == [tmp_path / ABC]


def test_cleanup_failure_can_follow_complete_publication_and_retry_verifies(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    archive = LocalRawArchive(tmp_path)

    def fail_unlink(*args: Any, **kwargs: Any) -> None:
        raise PermissionError("injected cleanup failure")

    with monkeypatch.context() as patch:
        patch.setattr(raw_archive.os, "unlink", fail_unlink)
        with pytest.raises(ArchiveIOError):
            archive.put(ABC, b"abc")
    assert archive.get(ABC) == b"abc"
    archive.put(ABC, b"abc")
    assert len(list(tmp_path.glob(".staging-*"))) == 1


def test_read_filesystem_failure_is_not_reported_as_missing(
    tmp_path: Path, monkeypatch: Any
) -> None:
    archive = LocalRawArchive(tmp_path)
    archive.put(ABC, b"abc")
    real_open = os.open

    def deny_object(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == ABC:
            raise PermissionError("injected read failure")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(raw_archive.os, "open", deny_object)
    with pytest.raises(ArchiveIOError):
        archive.get(ABC)
