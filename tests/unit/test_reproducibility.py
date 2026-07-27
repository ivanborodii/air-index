from pathlib import Path

from iaq_hfis.reproducibility import collect_environment_metadata, get_git_commit


def test_collect_environment_metadata_has_expected_keys():
    meta = collect_environment_metadata()
    expected_keys = {
        "iaq_hfis_version",
        "python_version",
        "duckdb_version",
        "platform",
        "processor",
        "cpu_count",
        "git_commit",
        "rule_generation_version",
    }
    assert expected_keys <= set(meta.keys())


def test_git_commit_none_without_repo_root():
    meta = collect_environment_metadata(repo_root=None)
    assert meta["git_commit"] is None


def test_get_git_commit_returns_none_for_non_git_directory(tmp_path):
    # air_ml/ itself has no .git (confirmed: not a git repository) --
    # exercise the same code path against a definitely-non-git tmp_path.
    assert get_git_commit(tmp_path) is None


def test_get_git_commit_none_for_nonexistent_path():
    assert get_git_commit(Path("/nonexistent/path/xyz")) is None
