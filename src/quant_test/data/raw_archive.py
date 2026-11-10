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

from quant_test.data.catalog_inventories import (
    VersionCatalogInventory,
    VersionCatalogInventoryFormatError,
    build_version_catalog_inventory,
    decode_version_catalog_inventory,
    encode_version_catalog_inventory,
)
from quant_test.data.listing_records import (
    ListingHistoryRecord,
    ListingHistoryRecordFormatError,
    build_listing_history_record,
    decode_listing_history_record,
    encode_listing_history_record,
)
from quant_test.data.listings import ListingHistory
from quant_test.data.membership_records import (
    MembershipHistoryRecord,
    MembershipHistoryRecordFormatError,
    build_membership_history_record,
    decode_membership_history_record,
    encode_membership_history_record,
)
from quant_test.data.observation_records import (
    ObservationRecordFormatError,
    ReceiptLinkedVersion,
    build_observation_record,
    decode_observation_record,
    encode_observation_record,
)
from quant_test.data.receipt_sets import (
    RawReceiptSet,
    ReceiptSetFormatError,
    build_receipt_set,
    decode_receipt_set,
    encode_receipt_set,
)
from quant_test.data.receipts import (
    AdmissionReceipt,
    ReceiptFormatError,
    decode_receipt,
    encode_receipt,
)
from quant_test.data.universes import MembershipHistory
from quant_test.data.versions import ObservationVersion


class RawArchiveError(Exception):
    """Base error for raw-byte storage failures."""


class PayloadDigestMismatchError(RawArchiveError):
    """Supplied bytes do not match the requested digest; nothing was written."""


class PayloadMissingError(RawArchiveError):
    """The requested object does not exist; no substitute is returned."""


class PayloadCorruptError(RawArchiveError):
    """An object is unsafe, is not a regular file, or fails checksum verification."""


class ReceiptMissingError(RawArchiveError):
    """The requested receipt does not exist; no substitute is returned."""


class ReceiptCorruptError(RawArchiveError):
    """Receipt bytes, schema, policy, or recomputed admission are invalid."""


class ReceiptSetMissingError(RawArchiveError):
    """The explicitly requested raw receipt-set object does not exist."""


class ReceiptSetCorruptError(RawArchiveError):
    """Receipt-set checksum, schema, policy or recomputed report is invalid."""


class ObservationRecordMissingError(RawArchiveError):
    """The explicitly requested receipt-linked metadata object does not exist."""


class ObservationRecordCorruptError(RawArchiveError):
    """Metadata checksum, schema, policy or receipt linkage is invalid."""


class VersionCatalogInventoryMissingError(RawArchiveError):
    """The explicitly requested version-catalog inventory object does not exist."""


class VersionCatalogInventoryCorruptError(RawArchiveError):
    """Inventory checksum, schema, policy or catalog consistency is invalid."""


class ListingHistoryRecordMissingError(RawArchiveError):
    """The explicitly requested listing-history assertion object does not exist."""


class ListingHistoryRecordCorruptError(RawArchiveError):
    """Listing assertion checksum, schema, policy or consistency is invalid."""


class MembershipHistoryRecordMissingError(RawArchiveError):
    """The explicitly requested membership-history assertion does not exist."""


class MembershipHistoryRecordCorruptError(RawArchiveError):
    """Membership assertion checksum, schema, policy or consistency is invalid."""


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

    Raw admission receipts additionally bind payload provenance and syntactic
    admission. Explicit metadata inventories do not add a mutable version index
    or processing status. Select the
    historical version first, then call get_version; a missing/corrupt selected
    payload raises and must never trigger fallback.
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

    def put_receipt(self, receipt: AdmissionReceipt, payload: bytes) -> str:
        """Verify/store payload first, then publish deterministic receipt bytes.

        Pre-publication failure exposes no new receipt; an unreferenced payload
        may remain. As with put, cleanup failure after publication may raise
        despite a complete receipt existing; retry verifies existing content.
        """
        encoded = encode_receipt(receipt)
        digest = hashlib.sha256(encoded).hexdigest()
        self.put(receipt.content_sha256, payload)
        self.put(digest, encoded)
        return digest

    def get_receipt(self, receipt_sha256: str) -> AdmissionReceipt:
        """Verify receipt and referenced payload, recomputing the named policy.

        Missing/corrupt payload errors propagate without substituting another
        receipt or revision. Successful load establishes no evidence authenticity.
        """
        _require_digest(receipt_sha256)
        try:
            encoded = self.get(receipt_sha256)
        except PayloadMissingError as error:
            raise ReceiptMissingError(f"raw receipt missing: {receipt_sha256}") from error
        except PayloadCorruptError as error:
            raise ReceiptCorruptError(f"raw receipt checksum failed: {receipt_sha256}") from error
        try:
            receipt = decode_receipt(encoded)
        except ReceiptFormatError as error:
            raise ReceiptCorruptError(f"raw receipt format failed: {receipt_sha256}") from error
        self.get(receipt.content_sha256)
        return receipt

    def put_receipt_set(self, receipt_sha256s: tuple[str, ...] | list[str]) -> str:
        """Verify all receipt/payload dependencies and publish the manifest/report last.

        The explicit collection is sorted and duplicates reject. An empty list or
        tuple is valid. Existing publication/cleanup failure semantics apply.
        No new receipts, validated observations or dataset snapshots are created.
        """
        receipt_set = build_receipt_set(self, receipt_sha256s)
        encoded = encode_receipt_set(receipt_set)
        digest = hashlib.sha256(encoded).hexdigest()
        self.put(digest, encoded)
        return digest

    def get_receipt_set(self, receipt_set_sha256: str) -> RawReceiptSet:
        """Verify/recompute a raw receipt inventory; dependency failures propagate."""
        _require_digest(receipt_set_sha256)
        try:
            encoded = self.get(receipt_set_sha256)
        except PayloadMissingError as error:
            raise ReceiptSetMissingError(
                f"raw receipt set missing: {receipt_set_sha256}"
            ) from error
        except PayloadCorruptError as error:
            raise ReceiptSetCorruptError(
                f"raw receipt-set checksum failed: {receipt_set_sha256}"
            ) from error
        try:
            return decode_receipt_set(encoded, self)
        except ReceiptSetFormatError as error:
            raise ReceiptSetCorruptError(
                f"raw receipt-set format failed: {receipt_set_sha256}"
            ) from error

    def put_observation_record(self, version: ObservationVersion, receipt_sha256: str) -> str:
        """Verify existing receipt/payload and publish explicit metadata assertions last.

        No receipt or payload is created and no accepted receipt is promoted.
        Existing no-replace publication and post-link cleanup limits apply.
        """
        record = build_observation_record(self, version, receipt_sha256)
        encoded = encode_observation_record(record)
        digest = hashlib.sha256(encoded).hexdigest()
        self.put(digest, encoded)
        return digest

    def get_observation_record(self, observation_record_sha256: str) -> ReceiptLinkedVersion:
        """Verify metadata and every dependency; never return a substitute version."""
        _require_digest(observation_record_sha256)
        try:
            encoded = self.get(observation_record_sha256)
        except PayloadMissingError as error:
            raise ObservationRecordMissingError(
                f"observation record missing: {observation_record_sha256}"
            ) from error
        except PayloadCorruptError as error:
            raise ObservationRecordCorruptError(
                f"observation record checksum failed: {observation_record_sha256}"
            ) from error
        try:
            return decode_observation_record(encoded, self)
        except ObservationRecordFormatError as error:
            raise ObservationRecordCorruptError(
                f"observation record format failed: {observation_record_sha256}"
            ) from error

    def put_version_catalog_inventory(
        self, observation_record_sha256s: tuple[str, ...] | list[str]
    ) -> str:
        """Verify all selected dependencies and catalog rules, then publish manifest last."""
        inventory = build_version_catalog_inventory(self, observation_record_sha256s)
        encoded = encode_version_catalog_inventory(inventory)
        digest = hashlib.sha256(encoded).hexdigest()
        self.put(digest, encoded)
        return digest

    def get_version_catalog_inventory(
        self, version_catalog_inventory_sha256: str
    ) -> VersionCatalogInventory:
        """Verify one explicit inventory and every dependency without partial results."""
        _require_digest(version_catalog_inventory_sha256)
        try:
            encoded = self.get(version_catalog_inventory_sha256)
        except PayloadMissingError as error:
            raise VersionCatalogInventoryMissingError(
                f"version catalog inventory missing: {version_catalog_inventory_sha256}"
            ) from error
        except PayloadCorruptError as error:
            raise VersionCatalogInventoryCorruptError(
                f"version catalog inventory checksum failed: {version_catalog_inventory_sha256}"
            ) from error
        try:
            return decode_version_catalog_inventory(encoded, self)
        except VersionCatalogInventoryFormatError as error:
            raise VersionCatalogInventoryCorruptError(
                f"version catalog inventory format failed: {version_catalog_inventory_sha256}"
            ) from error

    def put_listing_history_record(
        self, history: ListingHistory, observation_record_sha256: str
    ) -> str:
        """Verify pinned metadata and publish one explicit listing assertion last."""
        record = build_listing_history_record(self, history, observation_record_sha256)
        encoded = encode_listing_history_record(record)
        digest = hashlib.sha256(encoded).hexdigest()
        self.put(digest, encoded)
        return digest

    def get_listing_history_record(
        self, listing_history_record_sha256: str
    ) -> ListingHistoryRecord:
        """Verify listing assertions and all metadata/receipt/payload dependencies."""
        _require_digest(listing_history_record_sha256)
        try:
            encoded = self.get(listing_history_record_sha256)
        except PayloadMissingError as error:
            raise ListingHistoryRecordMissingError(
                f"listing history record missing: {listing_history_record_sha256}"
            ) from error
        except PayloadCorruptError as error:
            raise ListingHistoryRecordCorruptError(
                f"listing history record checksum failed: {listing_history_record_sha256}"
            ) from error
        try:
            return decode_listing_history_record(encoded, self)
        except ListingHistoryRecordFormatError as error:
            raise ListingHistoryRecordCorruptError(
                f"listing history record format failed: {listing_history_record_sha256}"
            ) from error

    def put_membership_history_record(
        self, history: MembershipHistory, observation_record_sha256: str
    ) -> str:
        """Verify metadata and publish one exact universe membership assertion last."""
        record = build_membership_history_record(self, history, observation_record_sha256)
        encoded = encode_membership_history_record(record)
        digest = hashlib.sha256(encoded).hexdigest()
        self.put(digest, encoded)
        return digest

    def get_membership_history_record(
        self, membership_history_record_sha256: str
    ) -> MembershipHistoryRecord:
        """Verify exact membership and every selected metadata/receipt/payload dependency."""
        _require_digest(membership_history_record_sha256)
        try:
            encoded = self.get(membership_history_record_sha256)
        except PayloadMissingError as error:
            raise MembershipHistoryRecordMissingError(
                f"membership history record missing: {membership_history_record_sha256}"
            ) from error
        except PayloadCorruptError as error:
            raise MembershipHistoryRecordCorruptError(
                f"membership history record checksum failed: {membership_history_record_sha256}"
            ) from error
        try:
            return decode_membership_history_record(encoded, self)
        except MembershipHistoryRecordFormatError as error:
            raise MembershipHistoryRecordCorruptError(
                f"membership history record format failed: {membership_history_record_sha256}"
            ) from error
