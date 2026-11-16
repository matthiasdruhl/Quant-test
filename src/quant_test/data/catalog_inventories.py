"""Explicit immutable metadata inventories, without coverage or source authentication.

Every archive load verifies the entire selected dependency graph and existing
VersionCatalog invariants. A manifest is not an evaluable dataset snapshot.
"""

import hashlib
import json
from dataclasses import dataclass
from re import fullmatch
from typing import TYPE_CHECKING

from quant_test.data.observation_records import ReceiptLinkedVersion
from quant_test.data.versions import VersionCatalog

if TYPE_CHECKING:
    from quant_test.data.raw_archive import LocalRawArchive

VERSION_CATALOG_INVENTORY_SCHEMA_VERSION = 1
CATALOG_POLICY_ID = "observation-version-catalog-v1"


class VersionCatalogInventoryFormatError(ValueError):
    """Malformed, unsupported, noncanonical or inconsistent inventory bytes."""


def _digests(values: object) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)) or type(values) not in (tuple, list):
        raise ValueError("observation-record digests must be an explicit built-in tuple or list")
    for value in values:
        if not isinstance(value, str) or fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("observation-record digest must be a lowercase SHA-256 hex digest")
    if len(set(values)) != len(values):
        raise ValueError("duplicate observation-record digests are not permitted")
    return tuple(sorted(values))


@dataclass(frozen=True, slots=True, init=False)
class VersionCatalogManifest:
    """Sorted distinct record identities; tuple/list inputs are snapshotted."""

    observation_record_sha256s: tuple[str, ...]

    def __init__(self, observation_record_sha256s: tuple[str, ...] | list[str]) -> None:
        object.__setattr__(self, "observation_record_sha256s", _digests(observation_record_sha256s))


@dataclass(frozen=True, slots=True)
class VersionCatalogInventory:
    """Manifest and records in digest order, with catalog consistency checked.

    Direct construction verifies record correspondence and selection invariants,
    not the existence of archive dependencies or the truth of source assertions.
    """

    manifest: VersionCatalogManifest
    records: tuple[ReceiptLinkedVersion, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, VersionCatalogManifest):
            raise ValueError("manifest must be a VersionCatalogManifest")
        if type(self.records) is not tuple or any(
            not isinstance(record, ReceiptLinkedVersion) for record in self.records
        ):
            raise ValueError("records must be an immutable tuple of ReceiptLinkedVersion records")
        if tuple(record.observation_record_sha256 for record in self.records) != (
            self.manifest.observation_record_sha256s
        ):
            raise ValueError("inventory records must match manifest digests in order")
        self.to_catalog()

    def to_catalog(self) -> VersionCatalog:
        """Build a fresh historical selector; retained records preserve all provenance."""
        return VersionCatalog(record.version for record in self.records)

    @property
    def version_catalog_inventory_sha256(self) -> str:
        return hashlib.sha256(encode_version_catalog_inventory(self)).hexdigest()


def build_version_catalog_inventory(
    archive: "LocalRawArchive", observation_record_sha256s: tuple[str, ...] | list[str]
) -> VersionCatalogInventory:
    """Verify every explicit record/receipt/payload before validating one catalog.

    No archive discovery, implicit inclusion, deduplication or source assertion
    authentication occurs. An empty collection still requires a valid archive.
    """
    from quant_test.data.raw_archive import LocalRawArchive

    if not isinstance(archive, LocalRawArchive):
        raise ValueError("archive must be a LocalRawArchive")
    manifest = VersionCatalogManifest(observation_record_sha256s)
    records = tuple(
        archive.get_observation_record(digest) for digest in manifest.observation_record_sha256s
    )
    return VersionCatalogInventory(manifest, records)


def _manifest_bytes(manifest: VersionCatalogManifest) -> bytes:
    return json.dumps(
        {
            "schema_version": VERSION_CATALOG_INVENTORY_SCHEMA_VERSION,
            "catalog_policy_id": CATALOG_POLICY_ID,
            "manifest": {"observation_record_sha256s": manifest.observation_record_sha256s},
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def encode_version_catalog_inventory(inventory: VersionCatalogInventory) -> bytes:
    """Encode a manifest assertion without accessing or authenticating an archive."""
    if not isinstance(inventory, VersionCatalogInventory):
        raise ValueError("inventory must be a VersionCatalogInventory")
    return _manifest_bytes(inventory.manifest)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise VersionCatalogInventoryFormatError("duplicate catalog inventory object field")
        document[key] = value
    return document


def _reject_number(value: str) -> object:
    raise VersionCatalogInventoryFormatError(f"unsupported catalog inventory number: {value}")


def decode_version_catalog_inventory(
    payload: bytes, archive: "LocalRawArchive"
) -> VersionCatalogInventory:
    """Strictly reopen all dependencies and repeat the existing catalog invariants.

    Noncanonical manifest bytes reject before dependency reads. Dependency errors
    propagate unchanged; malformed membership or catalog contradictions are format
    failures. No partial inventory or fallback is returned.
    """
    if type(payload) is not bytes:
        raise VersionCatalogInventoryFormatError("inventory encoding must be immutable bytes")
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
        if not isinstance(document, dict) or set(document) != {
            "schema_version",
            "catalog_policy_id",
            "manifest",
        }:
            raise VersionCatalogInventoryFormatError("inventory fields do not match schema")
        if type(document["schema_version"]) is not int or (
            document["schema_version"] != VERSION_CATALOG_INVENTORY_SCHEMA_VERSION
        ):
            raise VersionCatalogInventoryFormatError("unsupported catalog inventory schema")
        if document["catalog_policy_id"] != CATALOG_POLICY_ID:
            raise VersionCatalogInventoryFormatError("unsupported catalog inventory policy")
        manifest_document = document["manifest"]
        if not isinstance(manifest_document, dict) or set(manifest_document) != {
            "observation_record_sha256s"
        }:
            raise VersionCatalogInventoryFormatError(
                "inventory manifest fields do not match schema"
            )
        manifest = VersionCatalogManifest(manifest_document["observation_record_sha256s"])
        if _manifest_bytes(manifest) != payload:
            raise VersionCatalogInventoryFormatError("inventory encoding is not canonical")
        inventory = build_version_catalog_inventory(archive, manifest.observation_record_sha256s)
        if encode_version_catalog_inventory(inventory) != payload:
            raise VersionCatalogInventoryFormatError("reopened inventory differs from manifest")
        return inventory
    except VersionCatalogInventoryFormatError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VersionCatalogInventoryFormatError(
            "malformed or inconsistent catalog inventory"
        ) from error
