"""Shell-free coordinator for commit artifacts and saved Terraform plans."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.deploy.ensure_image import CommandRunner, ImageConfig, ensure_image
from scripts.deploy.package_lambda import package_lambda
from scripts.deploy.plan_manifest import PlanIntegrityError, verify_manifest, write_manifest
from scripts.deploy.provenance import (
    DeploymentProvenance,
    ProvenanceError,
    provenance_from_environment,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT = "portfolio"
PLAN_DIR = REPO_ROOT / ".tfplans" / ENVIRONMENT
PROVENANCE_PATH = PLAN_DIR / "deployment-provenance.json"
ACCOUNT_FILE = REPO_ROOT / ".aws-account-id"
LAMBDA_PACKAGE = REPO_ROOT / "lambda" / "processor" / "package.zip"
ACCOUNT_PATTERN = re.compile(r"^[0-9]{12}$")
ECR_REPOSITORY_PATTERN = re.compile(
    r"^(?P<account>[0-9]{12})\.dkr\.ecr\."
    r"(?P<region>[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+)\."
    r"amazonaws\.com(?:\.cn)?/[a-z0-9._/-]+$"
)
DESTROY_IMAGE_TAG = "000000000000"
DESTROY_IMAGE_DIGEST = f"sha256:{'0' * 64}"

LAYERS = {
    "l0": {
        "directory": REPO_ROOT / "terraform" / "layers" / "l0-foundation",
        "tfvars": REPO_ROOT
        / "terraform"
        / "environments"
        / ENVIRONMENT
        / "l0-foundation.tfvars",
        "plan": PLAN_DIR / "l0-foundation.tfplan",
        "manifest": PLAN_DIR / "l0-foundation.manifest.json",
    },
    "l1": {
        "directory": REPO_ROOT / "terraform" / "layers" / "l1-platform",
        "tfvars": REPO_ROOT
        / "terraform"
        / "environments"
        / ENVIRONMENT
        / "l1-platform.tfvars",
        "plan": PLAN_DIR / "l1-platform.tfplan",
        "manifest": PLAN_DIR / "l1-platform.manifest.json",
    },
    "l2": {
        "directory": REPO_ROOT
        / "terraform"
        / "layers"
        / "l2-application"
        / "vantage-ai",
        "tfvars": REPO_ROOT
        / "terraform"
        / "environments"
        / ENVIRONMENT
        / "l2-application-vantage-ai.tfvars",
        "plan": PLAN_DIR / "l2-application-vantage-ai.tfplan",
        "manifest": PLAN_DIR / "l2-application-vantage-ai.manifest.json",
    },
}


class WorkflowError(RuntimeError):
    """Raised before cloud mutation when deployment trust cannot be established."""


@dataclass(frozen=True)
class DeploymentContext:
    """Account and workspace identity proven before a deployment transaction."""

    account_id: str
    workspace: str


def _atomic_json(path: Path, value: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _provenance_dict(
    provenance: DeploymentProvenance,
    context: DeploymentContext,
) -> dict[str, str]:
    return {
        "commit_sha": provenance.commit_sha,
        "image_tag": provenance.image_tag,
        "aws_region": provenance.aws_region,
        "account_id": context.account_id,
        "workspace": context.workspace,
    }


def validate_inputs() -> DeploymentProvenance:
    return provenance_from_environment(REPO_ROOT)


def _read_allowed_account_id() -> str:
    try:
        account_id = ACCOUNT_FILE.read_text().strip()
    except OSError as exc:
        raise WorkflowError("Missing .aws-account-id") from exc
    if not ACCOUNT_PATTERN.fullmatch(account_id):
        raise WorkflowError(".aws-account-id must contain exactly 12 digits")
    return account_id


def _account_environment(account_id: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["TF_VAR_allowed_account_id"] = account_id
    return environment


def _run_command(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    environment: dict[str, str] | None = None,
):
    return subprocess.run(
        command,
        check=check,
        env=environment,
        capture_output=capture,
        text=capture,
    )


def _raw_terraform(
    layer: str,
    arguments: list[str],
    *,
    account_id: str,
    capture: bool = False,
):
    directory = str(LAYERS[layer]["directory"])
    return _run_command(
        ["terraform", f"-chdir={directory}", *arguments],
        check=True,
        environment=_account_environment(account_id),
        capture=capture,
    )


def deployment_preflight() -> DeploymentContext:
    """Prove AWS account and every layer workspace without changing either."""
    account_id = _read_allowed_account_id()
    try:
        identity = _run_command(
            [
                "aws",
                "sts",
                "get-caller-identity",
                "--query",
                "Account",
                "--output",
                "text",
            ],
            check=False,
            capture=True,
        )
    except OSError as exc:
        raise WorkflowError("Unable to query the active AWS account") from exc
    actual_account = identity.stdout.strip()
    if identity.returncode != 0 or not ACCOUNT_PATTERN.fullmatch(actual_account):
        raise WorkflowError("Unable to verify the active AWS account with STS")
    if actual_account != account_id:
        raise WorkflowError("AWS caller account does not match .aws-account-id")

    for layer in LAYERS:
        try:
            result = _raw_terraform(
                layer,
                ["workspace", "show"],
                account_id=account_id,
                capture=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise WorkflowError(
                f"Unable to verify the {layer} Terraform workspace; run make tf-workspace"
            ) from exc
        workspace = result.stdout.strip()
        if workspace != ENVIRONMENT:
            raise WorkflowError(
                f"{layer} must use the {ENVIRONMENT} workspace; found "
                f"{workspace or '<empty>'}. Run make tf-workspace"
            )
    return DeploymentContext(account_id=account_id, workspace=ENVIRONMENT)


def start_transaction(context: DeploymentContext | None = None) -> dict[str, str]:
    provenance = validate_inputs()
    context = context or deployment_preflight()
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    for generated in PLAN_DIR.iterdir():
        if generated.is_file():
            generated.unlink()
    metadata = _provenance_dict(provenance, context)
    _atomic_json(PROVENANCE_PATH, metadata)
    return metadata


def load_provenance(
    *,
    context: DeploymentContext | None = None,
    require_digest: bool = False,
) -> dict[str, str]:
    context = context or deployment_preflight()
    if not PROVENANCE_PATH.is_file():
        raise WorkflowError("Deployment provenance metadata is missing; start with tf-plan-l0")
    try:
        metadata = json.loads(PROVENANCE_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise WorkflowError("Deployment provenance metadata is invalid") from exc
    current = _provenance_dict(validate_inputs(), context)
    for field, expected in current.items():
        if metadata.get(field) != expected:
            raise WorkflowError(f"{field} differs from deployment provenance metadata")
    if require_digest and not isinstance(metadata.get("image_digest"), str):
        raise WorkflowError("Trusted local image digest metadata is missing")
    return metadata


def _terraform(
    layer: str,
    arguments: list[str],
    *,
    context: DeploymentContext | None = None,
    capture: bool = False,
):
    context = context or deployment_preflight()
    return _raw_terraform(
        layer,
        arguments,
        account_id=context.account_id,
        capture=capture,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_layer(layer: str) -> None:
    context = deployment_preflight()
    metadata = (
        start_transaction(context) if layer == "l0" else load_provenance(context=context)
    )
    paths = LAYERS[layer]
    plan_path = paths["plan"]
    manifest_path = paths["manifest"]
    plan_path.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)
    _terraform(
        layer,
        [
            "plan",
            "-input=false",
            f"-var-file={paths['tfvars']}",
            f"-out={plan_path}",
        ],
        context=context,
    )
    write_manifest(
        plan_path,
        manifest_path,
        {
            "commit_sha": metadata["commit_sha"],
            "image_tag": metadata["image_tag"],
            "account_id": metadata["account_id"],
            "workspace": metadata["workspace"],
        },
    )


def apply_layer(layer: str) -> None:
    paths = LAYERS[layer]
    manifest = verify_manifest(paths["plan"], paths["manifest"])
    context = deployment_preflight()
    metadata = load_provenance(context=context)
    for field in ("commit_sha", "image_tag", "account_id", "workspace"):
        if manifest.get(field) != metadata[field]:
            raise PlanIntegrityError(
                f"Saved plan {field} differs from deployment provenance"
            )
    _terraform(
        layer,
        ["apply", "-input=false", str(paths["plan"])],
        context=context,
    )


def _image_config(metadata: dict[str, str], repository_url: str) -> ImageConfig:
    return ImageConfig(
        repo=REPO_ROOT,
        repository_url=repository_url,
        region=metadata["aws_region"],
        image_tag=metadata["image_tag"],
        full_sha=metadata["commit_sha"],
    )


def _validate_ecr_repository(
    repository_url: str,
    metadata: dict[str, str],
    context: DeploymentContext,
) -> None:
    match = ECR_REPOSITORY_PATTERN.fullmatch(repository_url)
    if not match:
        raise WorkflowError("Terraform returned a non-canonical ECR repository URL")
    if match.group("account") != context.account_id:
        raise WorkflowError("ECR repository account differs from the approved account")
    if match.group("region") != metadata["aws_region"]:
        raise WorkflowError("ECR repository region differs from deployment provenance")


def ensure_deployment_image(
    context: DeploymentContext | None = None,
) -> dict[str, str]:
    context = context or deployment_preflight()
    metadata = load_provenance(context=context)
    repository_url = _terraform(
        "l1",
        ["output", "-raw", "ecr_repository_url"],
        context=context,
        capture=True,
    ).stdout.strip()
    _validate_ecr_repository(repository_url, metadata, context)
    recorded_repository = metadata.get("repository_url")
    if recorded_repository is not None and recorded_repository != repository_url:
        raise WorkflowError("ECR repository differs from trusted local metadata")
    result, digest = ensure_image(
        _image_config(metadata, repository_url),
        CommandRunner(),
        trusted_digest=metadata.get("image_digest"),
    )
    metadata["repository_url"] = repository_url
    metadata["image_digest"] = digest
    _atomic_json(PROVENANCE_PATH, metadata)
    print(f"image_{result} digest={digest}")
    return metadata


def package_deployment_lambda(
    context: DeploymentContext | None = None,
) -> dict[str, str]:
    context = context or deployment_preflight()
    metadata = load_provenance(context=context)
    package_lambda(REPO_ROOT, metadata["commit_sha"], LAMBDA_PACKAGE)
    return metadata


def package_ci_lambda() -> DeploymentProvenance:
    """Package the checked-out commit without cloud deployment preflight."""
    provenance = validate_inputs()
    package_lambda(REPO_ROOT, provenance.commit_sha, LAMBDA_PACKAGE)
    return provenance


def build_local_image() -> None:
    context = deployment_preflight()
    metadata = load_provenance(context=context)
    config = _image_config(metadata, "vantage-ai")
    CommandRunner().build_archive(config)


def plan_l2() -> None:
    context = deployment_preflight()
    ensure_deployment_image(context)
    package_deployment_lambda(context)
    metadata = load_provenance(context=context, require_digest=True)
    paths = LAYERS["l2"]
    paths["plan"].unlink(missing_ok=True)
    paths["manifest"].unlink(missing_ok=True)
    lambda_sha = _sha256(LAMBDA_PACKAGE)
    _terraform(
        "l2",
        [
            "plan",
            "-input=false",
            f"-var-file={paths['tfvars']}",
            f"-var=app_image_tag={metadata['image_tag']}",
            f"-var=app_image_digest={metadata['image_digest']}",
            f"-out={paths['plan']}",
        ],
        context=context,
    )
    write_manifest(
        paths["plan"],
        paths["manifest"],
        {
            "commit_sha": metadata["commit_sha"],
            "image_tag": metadata["image_tag"],
            "image_digest": metadata["image_digest"],
            "account_id": metadata["account_id"],
            "workspace": metadata["workspace"],
            "lambda_package_sha256": lambda_sha,
        },
    )


def apply_l2() -> None:
    paths = LAYERS["l2"]
    manifest = verify_manifest(paths["plan"], paths["manifest"])
    context = deployment_preflight()
    metadata = load_provenance(context=context, require_digest=True)
    for field in (
        "commit_sha",
        "image_tag",
        "image_digest",
        "account_id",
        "workspace",
    ):
        if manifest.get(field) != metadata[field]:
            raise PlanIntegrityError(f"Saved L2 plan {field} differs from trusted metadata")
    if manifest.get("lambda_package_sha256") != _sha256(LAMBDA_PACKAGE):
        raise PlanIntegrityError("Lambda package changed after the saved L2 plan")
    _terraform(
        "l2",
        ["apply", "-input=false", str(paths["plan"])],
        context=context,
    )


def destroy() -> None:
    context = deployment_preflight()
    destroy_arguments = {
        "l2": [
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-var-file={LAYERS['l2']['tfvars']}",
            f"-var=app_image_tag={DESTROY_IMAGE_TAG}",
            f"-var=app_image_digest={DESTROY_IMAGE_DIGEST}",
        ],
        "l1": [
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-var-file={LAYERS['l1']['tfvars']}",
        ],
        "l0": [
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-var-file={LAYERS['l0']['tfvars']}",
        ],
    }
    failed_layers = []
    for layer in ("l2", "l1", "l0"):
        try:
            state = _terraform(
                layer,
                ["state", "list"],
                context=context,
                capture=True,
            )
            if not state.stdout.strip():
                print(f"destroy_skipped layer={layer} reason=empty_state")
                continue
            _terraform(layer, destroy_arguments[layer], context=context)
        except (OSError, subprocess.CalledProcessError):
            failed_layers.append(layer)
            print(f"destroy_failed layer={layer}")
    if failed_layers:
        raise WorkflowError(
            "Destroy failed for layer(s): " + ", ".join(failed_layers)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "validate-inputs",
            "build-image",
            "ensure-image",
            "package-lambda",
            "package-lambda-ci",
            "plan-l0",
            "apply-l0",
            "plan-l1",
            "apply-l1",
            "plan-l2",
            "apply-l2",
            "destroy",
        ],
    )
    command = parser.parse_args().command
    actions = {
        "validate-inputs": validate_inputs,
        "build-image": build_local_image,
        "ensure-image": ensure_deployment_image,
        "package-lambda": package_deployment_lambda,
        "package-lambda-ci": package_ci_lambda,
        "plan-l0": lambda: plan_layer("l0"),
        "apply-l0": lambda: apply_layer("l0"),
        "plan-l1": lambda: plan_layer("l1"),
        "apply-l1": lambda: apply_layer("l1"),
        "plan-l2": plan_l2,
        "apply-l2": apply_l2,
        "destroy": destroy,
    }
    try:
        actions[command]()
    except (ProvenanceError, WorkflowError, PlanIntegrityError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
