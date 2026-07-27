import pytest

from iaq_hfis.reporting.exports import COLUMNS
from iaq_hfis.reporting.plot_manifest import PlotSpec, build_plot_manifest, validate_plots


def test_build_plot_manifest_validates_cleanly():
    manifest = build_plot_manifest()
    assert len(manifest) > 0


def test_every_plot_references_a_real_csv_and_real_columns():
    manifest = build_plot_manifest()
    for entry in manifest:
        assert entry["source_csv"] in COLUMNS
        valid_columns = {c.name for c in COLUMNS[entry["source_csv"]]}
        assert entry["x"] in valid_columns
        for y in entry["y"]:
            assert y in valid_columns
        if entry["group_by"] is not None:
            assert entry["group_by"] in valid_columns


def test_validate_plots_rejects_unknown_source_csv():
    bad = [PlotSpec(id="x", title="x", source_csv="does_not_exist.csv", plot_type="line", x="a")]
    with pytest.raises(ValueError, match="unknown source_csv"):
        validate_plots(bad)


def test_validate_plots_rejects_unknown_x_column():
    from iaq_hfis.reporting.exports import INDEX_TIMESERIES

    bad = [PlotSpec(id="x", title="x", source_csv=INDEX_TIMESERIES, plot_type="line", x="not_a_real_column")]
    with pytest.raises(ValueError, match="x column"):
        validate_plots(bad)


def test_validate_plots_rejects_unknown_y_column():
    from iaq_hfis.reporting.exports import INDEX_TIMESERIES

    bad = [PlotSpec(id="x", title="x", source_csv=INDEX_TIMESERIES, plot_type="line", x="computed_ts", y=["not_a_real_column"])]
    with pytest.raises(ValueError, match="y column"):
        validate_plots(bad)


def test_write_plot_manifest_creates_valid_json(tmp_path):
    import json

    from iaq_hfis.reporting.plot_manifest import write_plot_manifest

    path = write_plot_manifest(tmp_path)
    data = json.loads(path.read_text())
    assert isinstance(data, list)
    assert len(data) > 0
