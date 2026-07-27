import pandas as pd

from iaq_hfis.plots import render_all, render_plot


def test_render_plot_skips_when_csv_missing(tmp_path):
    spec = {"id": "x", "title": "X", "source_csv": "nope.csv", "plot_type": "line", "x": "a", "y": ["b"], "group_by": None}
    result = render_plot(spec, tmp_path, tmp_path)
    assert result is None


def test_render_plot_skips_when_csv_empty(tmp_path):
    csv_path = tmp_path / "empty.csv"
    pd.DataFrame({"a": [], "b": []}).to_csv(csv_path, index=False)
    spec = {"id": "x", "title": "X", "source_csv": "empty.csv", "plot_type": "line", "x": "a", "y": ["b"], "group_by": None}
    result = render_plot(spec, tmp_path, tmp_path)
    assert result is None


def test_render_plot_skips_when_all_y_values_null(tmp_path):
    csv_path = tmp_path / "allnull.csv"
    pd.DataFrame({"method": ["A", "B"], "rate": [None, None]}).to_csv(csv_path, index=False)
    spec = {"id": "x", "title": "X", "source_csv": "allnull.csv", "plot_type": "bar", "x": "method", "y": ["rate"], "group_by": None}
    result = render_plot(spec, tmp_path, tmp_path)
    assert result is None


def test_render_plot_line_succeeds(tmp_path):
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"computed_ts": ["2026-01-01T00:00:00", "2026-01-01T00:05:00"], "index_value": [10.0, 20.0]}).to_csv(csv_path, index=False)
    spec = {"id": "line_test", "title": "Line Test", "source_csv": "data.csv", "plot_type": "line", "x": "computed_ts", "y": ["index_value"], "group_by": None}
    result = render_plot(spec, tmp_path, tmp_path)
    assert result is not None
    assert result.is_file()
    assert result.name == "line_test.png"


def test_render_plot_bar_succeeds(tmp_path):
    csv_path = tmp_path / "bar.csv"
    pd.DataFrame({"method": ["A", "B"], "score": [0.5, 0.9]}).to_csv(csv_path, index=False)
    spec = {"id": "bar_test", "title": "Bar Test", "source_csv": "bar.csv", "plot_type": "bar", "x": "method", "y": ["score"], "group_by": None}
    result = render_plot(spec, tmp_path, tmp_path)
    assert result is not None and result.is_file()


def test_render_plot_histogram_succeeds(tmp_path):
    csv_path = tmp_path / "hist.csv"
    pd.DataFrame({"trial_class": ["Favorable", "Favorable", "Acceptable"]}).to_csv(csv_path, index=False)
    spec = {"id": "hist_test", "title": "Hist Test", "source_csv": "hist.csv", "plot_type": "histogram", "x": "trial_class", "y": [], "group_by": None}
    result = render_plot(spec, tmp_path, tmp_path)
    assert result is not None and result.is_file()


def test_render_plot_grouped_line_succeeds(tmp_path):
    csv_path = tmp_path / "grouped.csv"
    pd.DataFrame(
        {"computed_ts": ["2026-01-01T00:00:00"] * 2 + ["2026-01-01T00:05:00"] * 2, "component": ["A", "V"] * 2, "crisp_score": [10.0, 20.0, 12.0, 22.0]}
    ).to_csv(csv_path, index=False)
    spec = {"id": "grouped_test", "title": "Grouped", "source_csv": "grouped.csv", "plot_type": "line", "x": "computed_ts", "y": ["crisp_score"], "group_by": "component"}
    result = render_plot(spec, tmp_path, tmp_path)
    assert result is not None and result.is_file()


def test_render_all_returns_entry_per_manifest_item(tmp_path):
    import json

    manifest = [
        {"id": "a", "title": "A", "source_csv": "missing.csv", "plot_type": "line", "x": "x", "y": ["y"], "group_by": None},
        {"id": "b", "title": "B", "source_csv": "present.csv", "plot_type": "bar", "x": "k", "y": ["v"], "group_by": None},
    ]
    manifest_path = tmp_path / "plot_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    pd.DataFrame({"k": ["x"], "v": [1.0]}).to_csv(tmp_path / "present.csv", index=False)

    result = render_all(manifest_path, tmp_path, tmp_path)
    assert result["a"] is None
    assert result["b"] is not None
