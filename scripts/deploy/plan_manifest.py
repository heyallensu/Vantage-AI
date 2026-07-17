"""Create and verify saved-plan integrity manifests."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path


class PlanIntegrityError(RuntimeError):
    """Raised before Terraform when a saved plan or manifest is untrusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(
    plan_path: Path,
    manifest_path: Path,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    if not plan_path.is_file():
        raise PlanIntegrityError(f"Saved plan does not exist: {plan_path}")
    manifest = {"plan_sha256": sha256_file(plan_path), **dict(extra or {})}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def verify_manifest(plan_path: Path, manifest_path: Path) -> dict[str, str]:
    if not plan_path.is_file() or not manifest_path.is_file():
        raise PlanIntegrityError("Saved plan or integrity manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise PlanIntegrityError("Saved-plan manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise PlanIntegrityError("Saved-plan manifest must be a JSON object")
    expected = manifest.get("plan_sha256")
    actual = sha256_file(plan_path)
    if not isinstance(expected, str) or expected != actual:
        raise PlanIntegrityError("Saved plan SHA-256 does not match its manifest")
    return manifest
