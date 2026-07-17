"""Build the Lambda package exclusively from the verified deployment commit."""

import argparse
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

from scripts.deploy.provenance import verify_provenance

SAM_BUILD_IMAGE = (
    "public.ecr.aws/sam/build-python3.12@"
    "sha256:a62d05eb8829ca1ef9d428337e4989e3074d25e41864bdc58085da5b34d18ef5"
)
DETERMINISTIC_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


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


def write_deterministic_zip(source: Path, output: Path) -> None:
    """Write a stable ZIP independent of timestamps and traversal order."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(
                path.relative_to(source).as_posix(),
                DETERMINISTIC_ZIP_TIMESTAMP,
            )
            info.create_system = 3
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compresslevel=9)


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
                "pip install --no-compile -r requirements.txt -t package && "
                "cp handler.py package/",
            ],
            check=True,
        )
        temporary_zip = Path(temp) / "package.zip"
        write_deterministic_zip(source / "package", temporary_zip)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(temporary_zip, output)


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
