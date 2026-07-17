"""Resolve and verify a deployment commit and its canonical image tag."""

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
AWS_REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$")


class ProvenanceError(RuntimeError):
    """Raised when a deployment ref or tag is not canonical."""


@dataclass(frozen=True)
class DeploymentProvenance:
    commit_sha: str
    image_tag: str
    aws_region: str


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git command failed"
        raise ProvenanceError(detail)
    return result.stdout.strip()


def resolve_commit(repo: Path, deploy_commit: str) -> str:
    """Resolve any commit-ish to one canonical 40-character commit SHA."""
    full_sha = _git(repo, "rev-parse", "--verify", f"{deploy_commit}^{{commit}}")
    if not FULL_SHA_PATTERN.fullmatch(full_sha):
        raise ProvenanceError("DEPLOY_COMMIT did not resolve to a canonical commit SHA")
    return full_sha


def canonical_image_tag(repo: Path, full_sha: str) -> str:
    """Return Git's canonical 12-character abbreviation for the full commit."""
    if not FULL_SHA_PATTERN.fullmatch(full_sha):
        raise ProvenanceError("Full deployment SHA is invalid")
    return _git(repo, "rev-parse", "--short=12", full_sha)


def verify_provenance(repo: Path, deploy_commit: str, image_tag: str) -> str:
    """Reject arbitrary hex tags and return the verified full deployment SHA."""
    full_sha = resolve_commit(repo, deploy_commit)
    expected_tag = canonical_image_tag(repo, full_sha)
    if image_tag != expected_tag:
        raise ProvenanceError(
            f"IMAGE_TAG must be {expected_tag}, the canonical tag for {full_sha}"
        )
    return full_sha


def provenance_from_environment(
    repo: Path,
    environment: dict[str, str] | None = None,
) -> DeploymentProvenance:
    """Validate raw environment input without evaluating it through a shell."""
    values = environment if environment is not None else os.environ
    deploy_commit = values.get("DEPLOY_COMMIT", "HEAD")
    aws_region = values.get("AWS_REGION", "ap-southeast-2")
    if not AWS_REGION_PATTERN.fullmatch(aws_region):
        raise ProvenanceError("AWS_REGION is not a valid canonical AWS region")
    full_sha = resolve_commit(repo, deploy_commit)
    expected_tag = canonical_image_tag(repo, full_sha)
    image_tag = values.get("IMAGE_TAG", "") or expected_tag
    verify_provenance(repo, deploy_commit, image_tag)
    return DeploymentProvenance(full_sha, image_tag, aws_region)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--commit", required=True)
    parser.add_argument("--image-tag", required=True)
    arguments = parser.parse_args()
    try:
        print(
            verify_provenance(
                arguments.repo.resolve(),
                arguments.commit,
                arguments.image_tag,
            )
        )
    except ProvenanceError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
