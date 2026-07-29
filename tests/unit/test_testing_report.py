from iaq_hfis.testing_report import build_test_report_markdown, run_full_test_suite, write_test_report


def _summary(**overrides):
    base = {
        "total": 10, "passed": 9, "failed": 1, "errors": 0, "skipped": 0,
        "wall_seconds": 12.3, "exit_code": 1, "ok": False,
        "environment": {"python_version": "3.13.5", "duckdb_version": "1.5.2", "platform": "Linux-test", "git_commit": "abc123"},
        "generated_at_utc": "2026-07-29T00:00:00+00:00",
        "command": "pytest tests/ -q",
        "stdout_tail": "1 failed, 9 passed in 12.3s",
    }
    base.update(overrides)
    return base


def test_build_test_report_markdown_reports_failure_result():
    md = build_test_report_markdown(_summary())
    assert "FAILED" in md
    assert "Total: 10" in md
    assert "Passed: 9" in md
    assert "Failed: 1" in md
    assert "3.13.5" in md
    assert "1.5.2" in md
    assert "## Last output lines" in md  # only shown on failure


def test_build_test_report_markdown_ok_omits_failure_output():
    md = build_test_report_markdown(_summary(ok=True, failed=0, exit_code=0))
    assert "**Result: OK**" in md
    assert "## Last output lines" not in md


def test_write_test_report_writes_both_files(tmp_path):
    summary = _summary(ok=True, failed=0)
    json_path, md_path = write_test_report(summary, tmp_path)
    assert json_path.is_file()
    assert md_path.is_file()
    import json as json_module

    parsed = json_module.loads(json_path.read_text())
    assert parsed["total"] == 10
    assert parsed["ok"] is True


def test_run_full_test_suite_parses_junit_xml_and_reports_ok(tmp_path):
    """Integration-style check: run a tiny, fast, self-contained test file
    through the real subprocess/JUnit-XML pipeline (not a synthetic dict) --
    confirms total/passed/failed/skipped are parsed correctly from a real
    pytest invocation, and the temporary JUnit XML file is cleaned up."""
    test_file = tmp_path / "test_trivial.py"
    test_file.write_text(
        "def test_pass():\n    assert True\n\n"
        "def test_pass_2():\n    assert 1 + 1 == 2\n"
    )
    summary = run_full_test_suite(tmp_path, pytest_args=[str(test_file), "--no-header"])
    assert summary["ok"] is True
    assert summary["total"] == 2
    assert summary["passed"] == 2
    assert summary["failed"] == 0
    assert summary["errors"] == 0
    assert summary["skipped"] == 0
    assert summary["environment"]["python_version"]
    assert summary["environment"]["duckdb_version"]
    assert not (tmp_path / ".pytest_junit_report.xml").exists()


def test_run_full_test_suite_reports_failure(tmp_path):
    test_file = tmp_path / "test_trivial_fail.py"
    test_file.write_text("def test_fails():\n    assert False\n")
    summary = run_full_test_suite(tmp_path, pytest_args=[str(test_file)])
    assert summary["ok"] is False
    assert summary["total"] == 1
    assert summary["failed"] == 1
    assert summary["passed"] == 0
