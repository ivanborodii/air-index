from iaq_hfis.completeness import completeness_status, component_availability
from iaq_hfis.models import CoverageResult

OK_COV = CoverageResult(n_expected=30, n_usable=30, ratio=1.0, ok=True)
BAD_COV = CoverageResult(n_expected=30, n_usable=10, ratio=0.33, ok=False)


def test_all_available_gives_ok():
    coverage = {"pm2_5": OK_COV, "pm10": OK_COV, "co2": OK_COV, "temperature": OK_COV, "humidity": OK_COV}
    result = completeness_status(coverage)
    assert result.status == "OK"
    assert result.missing_components == []


def test_one_missing_component_gives_partial():
    coverage = {"pm2_5": OK_COV, "pm10": OK_COV, "co2": OK_COV, "temperature": BAD_COV, "humidity": OK_COV}
    result = completeness_status(coverage)
    assert result.status == "PARTIAL"
    assert result.missing_components == ["M"]


def test_two_missing_components_gives_failed():
    coverage = {"pm2_5": BAD_COV, "pm10": OK_COV, "co2": BAD_COV, "temperature": OK_COV, "humidity": OK_COV}
    result = completeness_status(coverage)
    assert result.status == "FAILED"
    assert set(result.missing_components) == {"A", "V"}


def test_pm_component_requires_both_pm2_5_and_pm10():
    coverage = {"pm2_5": OK_COV, "pm10": BAD_COV, "co2": OK_COV, "temperature": OK_COV, "humidity": OK_COV}
    availability = component_availability(coverage)
    assert availability["A"] is False


def test_microclimate_requires_both_temperature_and_humidity():
    coverage = {"pm2_5": OK_COV, "pm10": OK_COV, "co2": OK_COV, "temperature": OK_COV, "humidity": BAD_COV}
    availability = component_availability(coverage)
    assert availability["M"] is False


def test_missing_channel_entirely_counts_as_unavailable():
    coverage = {"pm2_5": OK_COV, "pm10": OK_COV, "co2": OK_COV}  # temperature/humidity absent entirely
    availability = component_availability(coverage)
    assert availability["M"] is False
