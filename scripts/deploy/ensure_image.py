"""Publish one immutable commit image or reuse a locally trusted ECR digest."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REVISION_LABEL = "org.opencontainers.image.revision"
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ImagePublicationError(RuntimeError):
    """Raised when ECR or Docker cannot prove the immutable image contract."""


@dataclass(frozen=True)
class ImageConfig:
    repo: Path
    repository_url: str
    region: str
    image_tag: str
    full_sha: str

    @property
    def image_uri(self) -> str:
        return f"{self.repository_url}:{self.image_tag}"

    def digest_uri(self, digest: str) -> str:
        return f"{self.repository_url}@{digest}"

    @property
    def repository_name(self) -> str:
        try:
            return self.repository_url.split("/", 1)[1]
        except IndexError as exc:
            raise ImagePublicationError("ECR repository URL is malformed") from exc

    @property
    def registry(self) -> str:
        return self.repository_url.split("/", 1)[0]


class CommandRunner:
    """Subprocess boundary kept injectable for fail-closed unit tests."""

    def run(self, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(command, check=check, capture_output=True, text=True)

    def login(self, config: ImageConfig) -> None:
        password = self.run(
            ["aws", "ecr", "get-login-password", "--region", config.region]
        ).stdout
        subprocess.run(
            [
                "docker",
                "login",
                "--username",
                "AWS",
                "--password-stdin",
                config.registry,
            ],
            check=True,
            input=password,
            text=True,
        )

    def build_archive(self, config: ImageConfig) -> None:
        archive = subprocess.Popen(
            ["git", "-C", str(config.repo), "archive", "--format=tar", config.full_sha],
            stdout=subprocess.PIPE,
        )
        if archive.stdout is None:
            raise ImagePublicationError("Unable to stream the Git archive")
        build = subprocess.Popen(
            [
                "docker",
                "buildx",
                "build",
                "--load",
                "--platform",
                "linux/amd64",
                "-f",
                "app/Dockerfile",
                "--label",
                f"{REVISION_LABEL}={config.full_sha}",
                "-t",
                config.image_uri,
                "-",
            ],
            stdin=archive.stdout,
        )
        archive.stdout.close()
        build_code = build.wait()
        archive_code = archive.wait()
        if archive_code != 0 or build_code != 0:
            raise ImagePublicationError("Git archive or Docker build failed")


def _describe_digest(config: ImageConfig, runner: CommandRunner):
    return runner.run(
        [
            "aws",
            "ecr",
            "describe-images",
            "--region",
            config.region,
            "--repository-name",
            config.repository_name,
            "--image-ids",
            f"imageTag={config.image_tag}",
            "--query",
            "imageDetails[0].imageDigest",
            "--output",
            "text",
        ],
        check=False,
    )


def _validated_digest(value: str) -> str:
    digest = value.strip()
    if not DIGEST_PATTERN.fullmatch(digest):
        raise ImagePublicationError(f"ECR returned an invalid image digest: {digest!r}")
    return digest


def _verify_pulled_digest(
    config: ImageConfig,
    digest: str,
    runner: CommandRunner,
) -> None:
    digest_uri = config.digest_uri(digest)
    runner.run(["docker", "pull", "--platform", "linux/amd64", digest_uri])
    revision = runner.run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            f'{{{{ index .Config.Labels "{REVISION_LABEL}" }}}}',
            digest_uri,
        ]
    ).stdout.strip()
    if revision != config.full_sha:
        raise ImagePublicationError(
            f"Image revision {revision!r} does not match {config.full_sha}"
        )
    raw_repo_digests = runner.run(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", digest_uri]
    ).stdout
    try:
        repo_digests = json.loads(raw_repo_digests)
    except json.JSONDecodeError as exc:
        raise ImagePublicationError("Docker returned invalid RepoDigests JSON") from exc
    if config.digest_uri(digest) not in repo_digests:
        raise ImagePublicationError("Pulled image RepoDigest does not match trusted ECR digest")


def ensure_image(
    config: ImageConfig,
    runner: CommandRunner,
    *,
    trusted_digest: str | None,
) -> tuple[str, str]:
    """Reuse only a locally trusted digest; publish only a provably missing tag."""
    describe = _describe_digest(config, runner)
    if describe.returncode == 0:
        ecr_digest = _validated_digest(describe.stdout)
        if trusted_digest is None:
            raise ImagePublicationError(
                "ECR tag exists but trusted local digest metadata is missing"
            )
        trusted_digest = _validated_digest(trusted_digest)
        if ecr_digest != trusted_digest:
            raise ImagePublicationError("ECR digest does not match trusted local metadata")
        runner.login(config)
        _verify_pulled_digest(config, trusted_digest, runner)
        return "reused", trusted_digest

    describe_error = describe.stderr or describe.stdout
    if "ImageNotFoundException" not in describe_error:
        raise ImagePublicationError(
            f"Unable to determine whether the ECR tag exists: {describe_error.strip()}"
        )
    if trusted_digest is not None:
        raise ImagePublicationError("Trusted image metadata exists but the ECR tag is missing")

    runner.login(config)
    runner.build_archive(config)
    runner.run(["docker", "push", config.image_uri])
    published = _describe_digest(config, runner)
    if published.returncode != 0:
        raise ImagePublicationError("Unable to resolve digest after publishing the image")
    digest = _validated_digest(published.stdout)
    _verify_pulled_digest(config, digest, runner)
    return "published", digest
