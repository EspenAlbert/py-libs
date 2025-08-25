import os

import pytest
from git import Repo

from pkg_ext.git_state import (
    GitChangesInput,
    GitSince,
    find_git_changes,
    solve_since_sha,
)


@pytest.mark.skipif(
    os.environ.get("MANUAL", "") == "", reason="needs os.environ[MANUAL]"
)
def test_solve_since_sha(repo_path):
    tag_commit = solve_since_sha(Repo(repo_path), repo_path, GitSince.LAST_GIT_TAG)
    assert tag_commit.hexsha[:6] == "25e96d"


@pytest.mark.skipif(
    os.environ.get("MANUAL", "") == "", reason="needs os.environ[MANUAL]"
)
def test_find_git_changes(repo_path):
    event = GitChangesInput(repo_path=repo_path, since=GitSince.LAST_GIT_TAG)
    output = find_git_changes(event)
    messages = [f"{c.sha}: {c.message}" for c in output.commits]
    assert messages == [
        "b2e8fc: feat: add dev_mode support and update public groups parsing logic",
        "c9b6c6: feat: enhance public groups management with module tracking and update changelog actions",
    ]
    assert sorted(output.files_changed) == [
        "pkg-ext/pkg_ext/cli.py",
        "pkg-ext/pkg_ext/conftest.py",
        "pkg-ext/pkg_ext/gen_changelog.py",
        "pkg-ext/pkg_ext/interactive_choices.py",
        "pkg-ext/pkg_ext/models.py",
        "pkg-ext/pkg_ext/models_test.py",
        "pkg-ext/pkg_ext/ref_added.py",
        "pkg-ext/pkg_ext/ref_removed.py",
        "pkg-ext/pkg_ext/settings.py",
        "pkg-ext/pkg_ext/settings_test.py",
        "pkg-ext/pkg_ext/testdata/e2e/01_initial/.changelog.yaml",
        "pkg-ext/pkg_ext/testdata/e2e/01_initial/.groups.yaml",
        "pkg-ext/pkg_ext/testdata/e2e/02_dep_order/.changelog.yaml",
        "pkg-ext/pkg_ext/testdata/e2e/02_dep_order/.groups.yaml",
        "pkg-ext/pkg_ext/testdata/e2e/03_nested/.changelog.yaml",
        "pkg-ext/pkg_ext/testdata/e2e/03_nested/.groups.yaml",
        "pkg-ext/pkg_ext/testdata/test_public_groups_add_to_existing_group.yaml",
        "pkg-ext/pkg_ext/testdata/test_public_groups_dumping.yaml",
        "pkg-ext/pkg_ext/testdata/test_public_groups_dumping_after_new_ref_symbol.yaml",
        "pyproject.toml",
    ]
    assert (
        output.old_version("pkg-ext/pkg_ext/testdata/e2e/01_initial/.groups.yaml")
        == "groups:\n- name: __ROOT__\n  owned_refs: []\n- name: my_dep\n  owned_refs:\n  - _internal2.MyCls\n- name: my_group\n  owned_refs:\n  - _internal.expose\n  - _internal.expose_with_arg"
    )
