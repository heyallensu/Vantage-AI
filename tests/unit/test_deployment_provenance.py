"""Fail-closed deployment provenance, image reuse, and saved-plan tests."""

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts.deploy import provenance as deployment_provenance
from scripts.deploy import workflow as deployment_workflow
from scripts.deploy.ensure_image import (
    CommandRunner,
    ImageConfig,
    ImagePublicationError,
    ensure_image,
)
from scripts.deploy.package_lambda import write_deterministic_zip
from scripts.deploy.plan_manifest import PlanIntegrityError, verify_manifest, write_manifest
from scripts.deploy.provenance import (
    ProvenanceError,
    canonical_image_tag,
    resolve_commit,
    verify_provenance,
)


class StubRunner(CommandRunner):
    def __init__(self, responses: list[subprocess.CompletedProcess]) -> None:
        self.responses = responses
        self.commands: list[list[str]] = []
        self.login_called = False
        self.build_called = False

    def run(self, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        del check
        self.commands.append(command)
        return self.responses.pop(0)

    def login(self, config: ImageConfig) -> None:
        del config
        self.login_called = True

    def build_archive(self, config: ImageConfig) -> None:
        del config
        self.build_called = True


def _completed(*, code: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def _image_config(full_sha: str) -> ImageConfig:
    return ImageConfig(
        repo=Path.cwd(),
        repository_url="123456789012.dkr.ecr.ap-southeast-2.amazonaws.com/vantage-ai",
        region="ap-southeast-2",
        image_tag=full_sha[:12],
        full_sha=full_sha,
    )


DIGEST_A = f"sha256:{'1' * 64}"
DIGEST_B = f"sha256:{'2' * 64}"
ACCOUNT_ID = "123456789012"


def _stub_preflight_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    actual_account: str = ACCOUNT_ID,
    sts_code: int = 0,
    workspaces: tuple[str, str, str] = ("portfolio", "portfolio", "portfolio"),
) -> list[list[str]]:
    account_file = tmp_path / ".aws-account-id"
    account_file.write_text(f"{ACCOUNT_ID}\n")
    monkeypatch.setattr(deployment_workflow, "ACCOUNT_FILE", account_file)
    commands: list[list[str]] = []
    workspace_values = iter(workspaces)

    def fake_run(
        command: list[str],
        *,
        check: bool = True,
        capture: bool = False,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        del check, capture
        commands.append(command)
        if command[:3] == ["aws", "sts", "get-caller-identity"]:
            return _completed(code=sts_code, stdout=f"{actual_account}\n")
        if command[0] == "terraform" and command[-2:] == ["workspace", "show"]:
            assert environment is not None
            assert environment["TF_VAR_allowed_account_id"] == ACCOUNT_ID
            return _completed(stdout=f"{next(workspace_values)}\n")
        raise AssertionError(f"Downstream command ran after failed preflight: {command}")

    monkeypatch.setattr(deployment_workflow, "_run_command", fake_run)
    return commands


def _invoke_guarded_entry(
    entry: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if entry == "plan":
        deployment_workflow.plan_layer("l0")
        return
    if entry == "apply":
        plan = tmp_path / "layer.tfplan"
        manifest = tmp_path / "layer.manifest.json"
        plan.write_bytes(b"reviewed-plan")
        write_manifest(plan, manifest)
        paths = dict(deployment_workflow.LAYERS["l0"])
        paths.update({"plan": plan, "manifest": manifest})
        monkeypatch.setitem(deployment_workflow.LAYERS, "l0", paths)
        deployment_workflow.apply_layer("l0")
        return
    if entry == "destroy":
        deployment_workflow.destroy()
        return
    if entry == "ecr":
        deployment_workflow.ensure_deployment_image()
        return
    raise AssertionError(f"Unknown entry: {entry}")


def test_random_hex_tag_is_rejected_for_real_commit() -> None:
    repo = Path.cwd()
    full_sha = resolve_commit(repo, "HEAD")
    random_tag = "0123456789ab"
    if random_tag == canonical_image_tag(repo, full_sha):
        random_tag = "abcdef012345"

    with pytest.raises(ProvenanceError, match="canonical tag"):
        verify_provenance(repo, "HEAD", random_tag)


def test_moving_ref_is_resolved_once_before_provenance_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_sha = "a" * 40
    calls: list[str] = []

    def moving_resolve(repo: Path, ref: str) -> str:
        del repo
        calls.append(ref)
        if ref == first_sha:
            return first_sha
        return first_sha if calls.count("moving") == 1 else "b" * 40

    monkeypatch.setattr(deployment_provenance, "resolve_commit", moving_resolve)
    monkeypatch.setattr(
        deployment_provenance,
        "canonical_image_tag",
        lambda repo, sha: sha[:12],
    )

    result = deployment_provenance.provenance_from_environment(
        Path.cwd(),
        {
            "DEPLOY_COMMIT": "moving",
            "IMAGE_TAG": first_sha[:12],
            "AWS_REGION": "ap-southeast-2",
        },
    )

    assert result.commit_sha == first_sha
    assert calls == ["moving", first_sha]


def test_git_archive_excludes_uncommitted_worktree_modification(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    source = repo / "app" / "value.txt"
    source.parent.mkdir()
    source.write_text("committed\n")
    subprocess.run(["git", "-C", str(repo), "add", "app/value.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    full_sha = resolve_commit(repo, "HEAD")
    source.write_text("uncommitted\n")

    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", full_sha],
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as package:
        archived = package.extractfile("app/value.txt")
        assert archived is not None
        assert archived.read() == b"committed\n"


def test_image_archive_uses_buildx_for_cross_platform_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    class FakeProcess:
        def __init__(self, *, stdout: io.BytesIO | None = None) -> None:
            self.stdout = stdout

        def wait(self) -> int:
            return 0

    def fake_popen(command: list[str], **kwargs) -> FakeProcess:
        del kwargs
        commands.append(command)
        return FakeProcess(stdout=io.BytesIO(b"archive")) if command[0] == "git" else FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    CommandRunner().build_archive(_image_config("a" * 40))

    assert commands[1][:5] == ["docker", "buildx", "build", "--load", "--platform"]
    assert commands[1][5] == "linux/amd64"


def test_existing_matching_image_is_reused_without_push() -> None:
    full_sha = "a" * 40
    runner = StubRunner(
        [
            _completed(stdout=f"{DIGEST_A}\n"),
            _completed(),
            _completed(stdout=f"{full_sha}\n"),
            _completed(stdout=f'["{_image_config(full_sha).digest_uri(DIGEST_A)}"]\n'),
        ]
    )

    assert ensure_image(
        _image_config(full_sha), runner, trusted_digest=DIGEST_A
    ) == ("reused", DIGEST_A)
    assert runner.login_called
    assert not runner.build_called
    assert all(command[:2] != ["docker", "push"] for command in runner.commands)
    assert ["docker", "pull", "--platform", "linux/amd64", _image_config(full_sha).digest_uri(DIGEST_A)] in runner.commands


def test_existing_image_revision_mismatch_fails() -> None:
    full_sha = "b" * 40
    runner = StubRunner(
        [
            _completed(stdout=f"{DIGEST_A}\n"),
            _completed(),
            _completed(stdout=f"{'c' * 40}\n"),
        ]
    )

    with pytest.raises(ImagePublicationError, match="does not match"):
        ensure_image(_image_config(full_sha), runner, trusted_digest=DIGEST_A)
    assert runner.login_called
    assert all(command[:2] != ["docker", "push"] for command in runner.commands)


def test_missing_image_is_built_and_pushed() -> None:
    full_sha = "d" * 40
    runner = StubRunner(
        [
            _completed(code=254, stderr="ImageNotFoundException"),
            _completed(),
            _completed(stdout=f"{DIGEST_A}\n"),
            _completed(),
            _completed(stdout=f"{full_sha}\n"),
            _completed(stdout=f'["{_image_config(full_sha).digest_uri(DIGEST_A)}"]\n'),
        ]
    )

    assert ensure_image(
        _image_config(full_sha), runner, trusted_digest=None
    ) == ("published", DIGEST_A)
    assert runner.login_called
    assert runner.build_called
    assert any(command[:2] == ["docker", "push"] for command in runner.commands)


def test_unknown_ecr_error_fails_without_build_or_push() -> None:
    full_sha = "e" * 40
    runner = StubRunner([_completed(code=255, stderr="network timeout")])

    with pytest.raises(ImagePublicationError, match="Unable to determine"):
        ensure_image(_image_config(full_sha), runner, trusted_digest=None)
    assert not runner.login_called
    assert not runner.build_called


def test_existing_tag_without_trusted_metadata_is_rejected() -> None:
    full_sha = "f" * 40
    runner = StubRunner([_completed(stdout=f"{DIGEST_A}\n")])

    with pytest.raises(ImagePublicationError, match="metadata is missing"):
        ensure_image(_image_config(full_sha), runner, trusted_digest=None)
    assert not runner.login_called


def test_correct_revision_cannot_override_digest_mismatch() -> None:
    full_sha = "a" * 40
    runner = StubRunner([_completed(stdout=f"{DIGEST_B}\n")])

    with pytest.raises(ImagePublicationError, match="digest does not match"):
        ensure_image(_image_config(full_sha), runner, trusted_digest=DIGEST_A)
    assert not runner.login_called


def test_plan_hash_tampering_fails_before_apply(tmp_path: Path) -> None:
    plan = tmp_path / "layer.tfplan"
    manifest = tmp_path / "layer.manifest.json"
    plan.write_bytes(b"reviewed-plan")
    write_manifest(plan, manifest)
    plan.write_bytes(b"tampered-plan")

    with pytest.raises(PlanIntegrityError, match="SHA-256"):
        verify_manifest(plan, manifest)


def test_non_object_plan_manifest_is_rejected(tmp_path: Path) -> None:
    plan = tmp_path / "layer.tfplan"
    manifest = tmp_path / "layer.manifest.json"
    plan.write_bytes(b"reviewed-plan")
    manifest.write_text("[]\n")

    with pytest.raises(PlanIntegrityError, match="JSON object"):
        verify_manifest(plan, manifest)


def test_deterministic_lambda_zip_ignores_file_timestamps(tmp_path: Path) -> None:
    source = tmp_path / "package"
    source.mkdir()
    (source / "handler.py").write_text("def handler(event, context): return event\n")
    package = source / "dependency"
    package.mkdir()
    dependency = package / "value.py"
    dependency.write_text("VALUE = 1\n")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    write_deterministic_zip(source, first)
    os.utime(source / "handler.py", (1_800_000_000, 1_800_000_000))
    os.utime(dependency, (1_900_000_000, 1_900_000_000))
    write_deterministic_zip(source, second)

    assert first.read_bytes() == second.read_bytes()


def test_apply_rejects_tampered_plan_before_terraform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = tmp_path / "layer.tfplan"
    manifest = tmp_path / "layer.manifest.json"
    plan.write_bytes(b"reviewed-plan")
    write_manifest(plan, manifest)
    plan.write_bytes(b"reviewed-plao")
    terraform_called = False

    def unexpected_terraform(*args, **kwargs):
        del args, kwargs
        nonlocal terraform_called
        terraform_called = True

    monkeypatch.setitem(
        deployment_workflow.LAYERS,
        "l0",
        {"plan": plan, "manifest": manifest},
    )
    monkeypatch.setattr(deployment_workflow, "_terraform", unexpected_terraform)

    with pytest.raises(PlanIntegrityError, match="SHA-256"):
        deployment_workflow.apply_layer("l0")

    assert not terraform_called


@pytest.mark.parametrize("entry", ["plan", "apply", "destroy", "ecr"])
@pytest.mark.parametrize("invalid_workspace", ["default", "other"])
def test_workspace_preflight_blocks_every_downstream_entry(
    entry: str,
    invalid_workspace: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _stub_preflight_commands(
        monkeypatch,
        tmp_path,
        workspaces=("portfolio", invalid_workspace, "portfolio"),
    )
    image_called = False

    def unexpected_image(*args, **kwargs):
        del args, kwargs
        nonlocal image_called
        image_called = True

    monkeypatch.setattr(deployment_workflow, "ensure_image", unexpected_image)

    with pytest.raises(deployment_workflow.WorkflowError, match="tf-workspace"):
        _invoke_guarded_entry(entry, monkeypatch, tmp_path)

    assert not image_called
    assert all(command[-2:] == ["workspace", "show"] for command in commands[1:])
    assert all(
        not ({"plan", "apply", "destroy", "output"} & set(command))
        for command in commands
    )


@pytest.mark.parametrize("entry", ["plan", "apply", "destroy", "ecr"])
@pytest.mark.parametrize(
    ("actual_account", "sts_code", "message"),
    [
        ("999999999999", 0, "does not match"),
        ("", 255, "Unable to verify"),
    ],
)
def test_account_preflight_blocks_every_downstream_entry(
    entry: str,
    actual_account: str,
    sts_code: int,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _stub_preflight_commands(
        monkeypatch,
        tmp_path,
        actual_account=actual_account,
        sts_code=sts_code,
    )
    image_called = False

    def unexpected_image(*args, **kwargs):
        del args, kwargs
        nonlocal image_called
        image_called = True

    monkeypatch.setattr(deployment_workflow, "ensure_image", unexpected_image)

    with pytest.raises(deployment_workflow.WorkflowError, match=message):
        _invoke_guarded_entry(entry, monkeypatch, tmp_path)

    assert not image_called
    assert commands == [
        [
            "aws",
            "sts",
            "get-caller-identity",
            "--query",
            "Account",
            "--output",
            "text",
        ]
    ]


def test_matching_account_and_portfolio_workspaces_pass_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _stub_preflight_commands(monkeypatch, tmp_path)

    assert deployment_workflow.deployment_preflight() == (
        deployment_workflow.DeploymentContext(
            account_id=ACCOUNT_ID,
            workspace="portfolio",
        )
    )
    assert len(commands) == 4
    assert commands[0][:3] == ["aws", "sts", "get-caller-identity"]
    assert all(command[-2:] == ["workspace", "show"] for command in commands[1:])


def test_destroy_skips_empty_partial_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = deployment_workflow.DeploymentContext(ACCOUNT_ID, "portfolio")
    destroy_calls: list[tuple[str, list[str]]] = []

    def fake_terraform(
        layer: str,
        arguments: list[str],
        *,
        context: deployment_workflow.DeploymentContext | None = None,
        capture: bool = False,
    ) -> subprocess.CompletedProcess:
        del capture
        assert context == deployment_workflow.DeploymentContext(ACCOUNT_ID, "portfolio")
        if arguments == ["state", "list"]:
            return _completed(stdout="aws_vpc.this\n" if layer == "l0" else "")
        assert arguments[0] == "destroy"
        destroy_calls.append((layer, arguments))
        return _completed()

    monkeypatch.setattr(deployment_workflow, "deployment_preflight", lambda: context)
    monkeypatch.setattr(deployment_workflow, "_terraform", fake_terraform)

    deployment_workflow.destroy()

    assert [layer for layer, _ in destroy_calls] == ["l0"]
    assert all("-auto-approve" in arguments for _, arguments in destroy_calls)


def test_destroy_continues_lower_layers_after_upper_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = deployment_workflow.DeploymentContext(ACCOUNT_ID, "portfolio")
    destroy_attempts = []

    def fake_terraform(
        layer: str,
        arguments: list[str],
        *,
        context: deployment_workflow.DeploymentContext | None = None,
        capture: bool = False,
    ) -> subprocess.CompletedProcess:
        del capture
        assert context == deployment_workflow.DeploymentContext(ACCOUNT_ID, "portfolio")
        if arguments == ["state", "list"]:
            return _completed(stdout=f"resource.{layer}\n")
        destroy_attempts.append(layer)
        if layer == "l2":
            raise subprocess.CalledProcessError(1, ["terraform", "destroy"])
        return _completed()

    monkeypatch.setattr(deployment_workflow, "deployment_preflight", lambda: context)
    monkeypatch.setattr(deployment_workflow, "_terraform", fake_terraform)

    with pytest.raises(deployment_workflow.WorkflowError, match="l2"):
        deployment_workflow.destroy()

    assert destroy_attempts == ["l2", "l1", "l0"]


def test_plan_and_apply_bind_account_and_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = deployment_workflow.DeploymentContext(ACCOUNT_ID, "portfolio")
    plan_dir = tmp_path / ".tfplans" / "portfolio"
    provenance_path = plan_dir / "deployment-provenance.json"
    plan = plan_dir / "l0.tfplan"
    manifest = plan_dir / "l0.manifest.json"
    paths = dict(deployment_workflow.LAYERS["l0"])
    paths.update({"plan": plan, "manifest": manifest})
    terraform_actions: list[str] = []

    def fake_terraform(
        layer: str,
        arguments: list[str],
        *,
        context: deployment_workflow.DeploymentContext | None = None,
        capture: bool = False,
    ) -> subprocess.CompletedProcess:
        del layer, capture
        assert context == deployment_workflow.DeploymentContext(ACCOUNT_ID, "portfolio")
        terraform_actions.append(arguments[0])
        if arguments[0] == "plan":
            plan.write_bytes(b"saved-plan")
        return _completed()

    monkeypatch.setattr(deployment_workflow, "PLAN_DIR", plan_dir)
    monkeypatch.setattr(deployment_workflow, "PROVENANCE_PATH", provenance_path)
    monkeypatch.setitem(deployment_workflow.LAYERS, "l0", paths)
    monkeypatch.setattr(deployment_workflow, "deployment_preflight", lambda: context)
    monkeypatch.setattr(
        deployment_workflow,
        "validate_inputs",
        lambda: deployment_workflow.DeploymentProvenance(
            commit_sha="a" * 40,
            image_tag="a" * 12,
            aws_region="ap-southeast-2",
        ),
    )
    monkeypatch.setattr(deployment_workflow, "_terraform", fake_terraform)

    deployment_workflow.plan_layer("l0")
    metadata = json.loads(provenance_path.read_text())
    saved_manifest = verify_manifest(plan, manifest)
    assert metadata["account_id"] == ACCOUNT_ID
    assert metadata["workspace"] == "portfolio"
    assert saved_manifest["account_id"] == ACCOUNT_ID
    assert saved_manifest["workspace"] == "portfolio"

    deployment_workflow.apply_layer("l0")
    assert terraform_actions == ["plan", "apply"]


def test_ci_lambda_package_skips_cloud_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "package.zip"
    provenance = deployment_workflow.DeploymentProvenance(
        commit_sha="a" * 40,
        image_tag="a" * 12,
        aws_region="ap-southeast-2",
    )
    packaged: list[tuple[Path, str, Path]] = []

    monkeypatch.setattr(deployment_workflow, "LAMBDA_PACKAGE", package_path)
    monkeypatch.setattr(deployment_workflow, "validate_inputs", lambda: provenance)
    monkeypatch.setattr(
        deployment_workflow,
        "deployment_preflight",
        lambda: pytest.fail("CI packaging must not run deployment preflight"),
    )
    monkeypatch.setattr(
        deployment_workflow,
        "package_lambda",
        lambda repo, commit, output: packaged.append((repo, commit, output)),
    )

    assert deployment_workflow.package_ci_lambda() == provenance
    assert packaged == [
        (deployment_workflow.REPO_ROOT, provenance.commit_sha, package_path)
    ]


@pytest.mark.parametrize(
    ("repository_url", "message"),
    [
        (
            "123456789012.dkr.ecr.us-east-1.amazonaws.com/vantage-ai-portfolio-api",
            "region differs",
        ),
        (
            "999999999999.dkr.ecr.ap-southeast-2.amazonaws.com/vantage-ai-portfolio-api",
            "account differs",
        ),
    ],
)
def test_ecr_repository_must_match_approved_account_and_region(
    repository_url: str,
    message: str,
) -> None:
    metadata = {"aws_region": "ap-southeast-2"}
    context = deployment_workflow.DeploymentContext(ACCOUNT_ID, "portfolio")

    with pytest.raises(deployment_workflow.WorkflowError, match=message):
        deployment_workflow._validate_ecr_repository(repository_url, metadata, context)


@pytest.mark.parametrize("variable", ["DEPLOY_COMMIT", "IMAGE_TAG", "AWS_REGION"])
def test_make_environment_injection_fails_closed(
    variable: str,
    tmp_path: Path,
) -> None:
    marker = tmp_path / f"{variable}.marker"
    payload = (
        f'bad"; touch {marker}; $(shell touch {marker}); '
        f'$(touch {marker}); `touch {marker}`\nmore'
    )
    environment = os.environ.copy()
    environment.update(
        {
            "DEPLOY_COMMIT": "HEAD",
            "IMAGE_TAG": canonical_image_tag(Path.cwd(), resolve_commit(Path.cwd(), "HEAD")),
            "AWS_REGION": "ap-southeast-2",
            variable: payload,
        }
    )

    result = subprocess.run(
        ["make", "validate-deployment-inputs"],
        cwd=Path.cwd(),
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not marker.exists()


def test_saved_plan_workflow_and_digest_pin_are_explicit() -> None:
    makefile = (Path.cwd() / "Makefile").read_text()

    assert ".tfplans/$(ENV)" in makefile
    assert "tf-plan-l0:" in makefile and "tf-apply-l0:" in makefile
    assert "tf-plan-l1:" in makefile and "tf-apply-l1:" in makefile
    assert "tf-plan-l2:" in makefile and "tf-apply-l2:" in makefile
    workflow = (Path.cwd() / "scripts/deploy/workflow.py").read_text()
    l2_function = workflow[workflow.index("def plan_l2()") : workflow.index("def apply_l2()")]
    assert l2_function.index("ensure_deployment_image") < l2_function.index(
        "package_deployment_lambda"
    )
    assert l2_function.index("package_deployment_lambda") < l2_function.index(
        '"plan"'
    )
    assert "lambda_package_sha256" in l2_function
    assert "verify_manifest" in workflow[workflow.index("def apply_l2()") :]

    ecs_task = (
        Path.cwd()
        / "terraform/layers/l2-application/vantage-ai/modules/ecs-service/main.tf"
    ).read_text()
    assert '${var.ecr_repository_url}@${var.image_digest}' in ecs_task

    dockerignore = (Path.cwd() / ".dockerignore").read_text().splitlines()
    assert dockerignore[0] == "*"
    assert set(dockerignore[1:]) == {
        "!app/",
        "!app/**",
        "!alembic/",
        "!alembic/**",
        "!alembic.ini",
        "!scripts/",
        "!scripts/**",
    }


def test_compose_uses_non_root_aws_home() -> None:
    dockerfile = (Path.cwd() / "app/Dockerfile").read_text()
    compose = (Path.cwd() / "docker-compose.yml").read_text()

    assert "--create-home --home-dir /home/vantage" in dockerfile
    assert "ENV HOME=/home/vantage" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "~/.aws:/home/vantage/.aws:ro" in compose
    assert "AWS_SHARED_CREDENTIALS_FILE: /home/vantage/.aws/credentials" in compose
    assert "AWS_CONFIG_FILE: /home/vantage/.aws/config" in compose
    assert "/root/.aws" not in compose
