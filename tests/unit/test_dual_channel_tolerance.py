from iaq_hfis.schema import dual_channel_tolerance


def test_dual_channel_tolerance_sums_primary_and_secondary(base_settings, sensor_specs):
    temp_tolerance = dual_channel_tolerance("temperature", base_settings.schema_mapping, sensor_specs)
    expected = sensor_specs.channels["bme_temp"].declared_uncertainty + sensor_specs.channels["scd_temp"].declared_uncertainty
    assert temp_tolerance == expected


def test_dual_channel_tolerance_humidity(base_settings, sensor_specs):
    rh_tolerance = dual_channel_tolerance("humidity", base_settings.schema_mapping, sensor_specs)
    expected = sensor_specs.channels["bme_humidity"].declared_uncertainty + sensor_specs.channels["scd_humidity"].declared_uncertainty
    assert rh_tolerance == expected


def test_dual_channel_tolerance_zero_without_secondary_column(base_settings, sensor_specs):
    # co2 has no secondary_column configured
    tolerance = dual_channel_tolerance("co2", base_settings.schema_mapping, sensor_specs)
    assert tolerance == sensor_specs.channels["co2"].declared_uncertainty  # primary only, secondary contributes 0
