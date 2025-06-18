from unittest.mock import MagicMock

import gh_ext
from gh_ext import CreateVariableSecretReportContext, GhExtSettings, delete_secrets
from zero_3rdparty.file_utils import ensure_parents_write_text


def test_delete_secrets(tmp_path, monkeypatch):
    secret_name = "TEST"
    settings = GhExtSettings.for_testing(tmp_path)
    owner_project = "test_owner/test_project"
    secrets_path = settings.repo_secrets_path(owner_project)
    run_and_wait_called = False

    def store_run_and_wait(*_, **__):
        nonlocal run_and_wait_called
        run_and_wait_called = True

    monkeypatch.setattr(gh_ext, "run_and_wait", store_run_and_wait)
    export = MagicMock()
    ctx = CreateVariableSecretReportContext.model_construct(
        owner_project=owner_project,
        delete_safe=True,
        gh_ext_settings=settings,
        repo_path=tmp_path / "repo",
    )
    ctx.export = export
    delete_secrets([secret_name], ctx)
    assert not run_and_wait_called, (
        "run_and_wait should not be called when delete_safe is True and no secrets are stored locally"
    )
    ensure_parents_write_text(secrets_path, f"{secret_name}: secret_value\n")
    delete_secrets([secret_name], ctx)
    assert run_and_wait_called, (
        "run_and_wait should be called when secrets are stored locally"
    )
