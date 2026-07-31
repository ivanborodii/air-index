from iaq_hfis.reproducibility import get_git_commit, get_git_tree_dirty
from iaq_hfis.validation import REPO_ROOT, check_same_commit_and_clean_tree


def test_same_commit_check_passes_when_recorded_commit_matches_current():
    current = get_git_commit(REPO_ROOT)
    summary = {"environment": {"git_commit": current}}
    passed, violations = [], []
    check_same_commit_and_clean_tree(summary, passed, violations)
    assert any("commit matches" in p for p in passed)
    # Tree-dirty status is whatever it actually is right now -- don't assert it here,
    # a dev sandbox may legitimately have uncommitted changes.


def test_same_commit_check_fails_on_commit_mismatch():
    summary = {"environment": {"git_commit": "0000000000000000000000000000000000dead"}}
    passed, violations = [], []
    check_same_commit_and_clean_tree(summary, passed, violations)
    assert any("!= commit recorded" in v for v in violations)


def test_same_commit_check_fails_when_recorded_commit_missing():
    summary = {"environment": {"git_commit": None}}
    passed, violations = [], []
    check_same_commit_and_clean_tree(summary, passed, violations)
    assert any("could not be determined" in v for v in violations)


def test_dirty_tree_helper_returns_a_bool_or_none_never_raises():
    result = get_git_tree_dirty(REPO_ROOT)
    assert result is None or isinstance(result, bool)
