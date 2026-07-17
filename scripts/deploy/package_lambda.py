"""Build the Lambda package exclusively from the verified deployment commit."""

import argparse
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from scripts.deploy.provenance import verify_provenance

SAM_BUILD_IMAGE = (
    "public.ecr.aws/sam/build-python3.12@"
    "sha256:a62d05eb8829ca1ef9d428337e4989e3074d25e41864bdc58085da5b34d18ef5"
)


def extract_lambda_source(repo: Path, full_sha: str, destination: Path) -> Path:
    """Extract committed Lambda sources without reading worktree file contents."""
    archive = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "archive",
            "--format=tar",
            full_sha,
            "lambda/processor",
        ],
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as package:
        package.extractall(destination, filter="data")
    return destination / "lambda" / "processor"


def package_lambda(repo: Path, full_sha: str, output: Path) -> None:
    """Install and zip Lambda dependencies in an AWS-compatible build image."""
    with tempfile.TemporaryDirectory(prefix="vantage-ai-lambda-") as temp:
        source = extract_lambda_source(repo, full_sha, Path(temp))
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/amd64",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--env",
                "HOME=/tmp",
                "-v",
                f"{source}:/var/task",
                SAM_BUILD_IMAGE,
                "/bin/sh",
                "-c",
                "pip install -r requirements.txt -t package && "
                "cp handler.py package/ && cd package && zip -qr ../package.zip .",
            ],
            check=True,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "package.zip", output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--commit", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    full_sha = verify_provenance(repo, arguments.commit, arguments.image_tag)
    package_lambda(repo, full_sha, arguments.output.resolve())
    print(f"lambda_packaged output={arguments.output} revision={full_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
