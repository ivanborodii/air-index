# Membership function audit

PM10 Degraded category shape: **triangular** (a=62.500, b=87.500, c=87.500, d=112.500, plateau_width=0.0).

This is the actual, effective shape given the config's real (possibly auto-widened) transition width -- reported as-is, not silently changed to match manuscript terminology if it turns out to differ.

## Breakpoint ordering / range coverage / gaps / overlaps

```
channel             breakpoints  breakpoints_strictly_increasing gaps_found unintended_overlaps_found
  pm2_5      [15.0, 25.0, 50.0]                             True       none                      none
   pm10     [45.0, 75.0, 100.0]                             True       none                      none
    co2 [800.0, 1000.0, 1500.0]                             True       none                      none
 output      [25.0, 50.0, 75.0]                             True       none                      none
```

## Full shape audit (every channel/class/side)

See membership_function_audit.csv for the full machine-readable table. Summary:
```
                                     channel class_name               shape_kind        side       a       b       c       d  plateau_width  shape_type  max_membership_degree                                                                    transition_width_source
                                       pm2_5 Favourable monotonic_right_shoulder         NaN    -inf    -inf   12.50   17.50            NaN    shoulder                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                       pm2_5 Acceptable monotonic_right_shoulder         NaN   12.50   17.50   22.50   27.50            5.0 trapezoidal                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                       pm2_5   Degraded monotonic_right_shoulder         NaN   22.50   27.50   47.50   52.50           20.0 trapezoidal                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                       pm2_5   Critical monotonic_right_shoulder         NaN   47.50   52.50     inf     inf            NaN    shoulder                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                        pm10 Favourable monotonic_right_shoulder         NaN    -inf    -inf   32.50   57.50            NaN    shoulder                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                        pm10 Acceptable monotonic_right_shoulder         NaN   32.50   57.50   62.50   87.50            5.0 trapezoidal                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                        pm10   Degraded monotonic_right_shoulder         NaN   62.50   87.50   87.50  112.50            0.0  triangular                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                        pm10   Critical monotonic_right_shoulder         NaN   87.50  112.50     inf     inf            NaN    shoulder                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                         co2 Favourable monotonic_right_shoulder         NaN    -inf    -inf  765.00  835.00            NaN    shoulder                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                         co2 Acceptable monotonic_right_shoulder         NaN  765.00  835.00  965.00 1035.00          130.0 trapezoidal                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                         co2   Degraded monotonic_right_shoulder         NaN  965.00 1035.00 1465.00 1535.00          430.0 trapezoidal                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                         co2   Critical monotonic_right_shoulder         NaN 1465.00 1535.00     inf     inf            NaN    shoulder                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                      output Favourable monotonic_right_shoulder         NaN    -inf    -inf   24.00   26.00            NaN    shoulder                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                      output Acceptable monotonic_right_shoulder         NaN   24.00   26.00   49.00   51.00           23.0 trapezoidal                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                      output   Degraded monotonic_right_shoulder         NaN   49.00   51.00   74.00   76.00           23.0 trapezoidal                    1.0                           ctx.static_shapes (real effective config used at inference time)
                                      output   Critical monotonic_right_shoulder         NaN   74.00   76.00     inf     inf            NaN    shoulder                    1.0                           ctx.static_shapes (real effective config used at inference time)
                           relative_humidity Favourable                two_sided single_band   28.50   31.50   48.50   51.50           17.0 trapezoidal                    1.0                                                  ctx.static_shapes (real effective config)
                           relative_humidity Acceptable                two_sided         low   23.50   26.50   28.50   31.50            2.0 trapezoidal                    1.0                                                  ctx.static_shapes (real effective config)
                           relative_humidity Acceptable                two_sided        high   48.50   51.50   58.50   61.50            7.0 trapezoidal                    1.0                                                  ctx.static_shapes (real effective config)
                           relative_humidity   Degraded                two_sided         low   18.50   21.50   23.50   26.50            2.0 trapezoidal                    1.0                                                  ctx.static_shapes (real effective config)
                           relative_humidity   Degraded                two_sided        high   58.50   61.50   68.50   71.50            7.0 trapezoidal                    1.0                                                  ctx.static_shapes (real effective config)
                           relative_humidity   Critical                two_sided         low    -inf    -inf   18.50   21.50            NaN    shoulder                    1.0                                                  ctx.static_shapes (real effective config)
                           relative_humidity   Critical                two_sided        high   68.50   71.50     inf     inf            NaN    shoulder                    1.0                                                  ctx.static_shapes (real effective config)
            temperature[kitchen/cold_period] Favourable                two_sided single_band   17.75   18.25   20.75   21.25            2.5 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/cold_period] (real effective config)
            temperature[kitchen/cold_period] Acceptable                two_sided         low   16.25   16.75   17.75   18.25            1.0 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/cold_period] (real effective config)
            temperature[kitchen/cold_period] Acceptable                two_sided        high   20.75   21.25   22.25   22.75            1.0 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/cold_period] (real effective config)
            temperature[kitchen/cold_period]   Degraded                two_sided         low   15.25   15.75   16.25   16.75            0.5 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/cold_period] (real effective config)
            temperature[kitchen/cold_period]   Degraded                two_sided        high   22.25   22.75   23.25   23.75            0.5 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/cold_period] (real effective config)
            temperature[kitchen/cold_period]   Critical                two_sided         low    -inf    -inf   15.25   15.75            NaN    shoulder                    1.0             ctx.temperature_shapes_by_profile[kitchen/cold_period] (real effective config)
            temperature[kitchen/cold_period]   Critical                two_sided        high   23.25   23.75     inf     inf            NaN    shoulder                    1.0             ctx.temperature_shapes_by_profile[kitchen/cold_period] (real effective config)
temperature[general_residential/warm_period] Favourable                two_sided single_band   23.25   23.75   25.25   25.75            1.5 trapezoidal                    1.0 ctx.temperature_shapes_by_profile[general_residential/warm_period] (real effective config)
temperature[general_residential/warm_period] Acceptable                two_sided         low   22.75   23.25   23.25   23.75            0.0  triangular                    1.0 ctx.temperature_shapes_by_profile[general_residential/warm_period] (real effective config)
temperature[general_residential/warm_period] Acceptable                two_sided        high   25.25   25.75   25.75   26.25            0.0  triangular                    1.0 ctx.temperature_shapes_by_profile[general_residential/warm_period] (real effective config)
temperature[general_residential/warm_period]   Degraded                two_sided         low   21.75   22.25   22.75   23.25            0.5 trapezoidal                    1.0 ctx.temperature_shapes_by_profile[general_residential/warm_period] (real effective config)
temperature[general_residential/warm_period]   Degraded                two_sided        high   25.75   26.25   26.75   27.25            0.5 trapezoidal                    1.0 ctx.temperature_shapes_by_profile[general_residential/warm_period] (real effective config)
temperature[general_residential/warm_period]   Critical                two_sided         low    -inf    -inf   21.75   22.25            NaN    shoulder                    1.0 ctx.temperature_shapes_by_profile[general_residential/warm_period] (real effective config)
temperature[general_residential/warm_period]   Critical                two_sided        high   26.75   27.25     inf     inf            NaN    shoulder                    1.0 ctx.temperature_shapes_by_profile[general_residential/warm_period] (real effective config)
            temperature[kitchen/warm_period] Favourable                two_sided single_band   20.75   21.25   25.25   25.75            4.0 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/warm_period] (real effective config)
            temperature[kitchen/warm_period] Acceptable                two_sided         low   19.75   20.25   20.75   21.25            0.5 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/warm_period] (real effective config)
            temperature[kitchen/warm_period] Acceptable                two_sided        high   25.25   25.75   25.75   26.25            0.0  triangular                    1.0             ctx.temperature_shapes_by_profile[kitchen/warm_period] (real effective config)
            temperature[kitchen/warm_period]   Degraded                two_sided         low   17.75   18.25   19.75   20.25            1.5 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/warm_period] (real effective config)
            temperature[kitchen/warm_period]   Degraded                two_sided        high   25.75   26.25   26.75   27.25            0.5 trapezoidal                    1.0             ctx.temperature_shapes_by_profile[kitchen/warm_period] (real effective config)
            temperature[kitchen/warm_period]   Critical                two_sided         low    -inf    -inf   17.75   18.25            NaN    shoulder                    1.0             ctx.temperature_shapes_by_profile[kitchen/warm_period] (real effective config)
            temperature[kitchen/warm_period]   Critical                two_sided        high   26.75   27.25     inf     inf            NaN    shoulder                    1.0             ctx.temperature_shapes_by_profile[kitchen/warm_period] (real effective config)
```

## Reachable output ranges (empirical, sampled through the real engine)

```json
{
  "A": {
    "empirical_min_crisp_score": 12.444029850746269,
    "empirical_max_crisp_score": 87.55597014925372,
    "n_samples": 256,
    "method": "sampled own real input domain through ctx.engine.infer_component"
  },
  "V": {
    "empirical_min_crisp_score": 12.444029850746269,
    "empirical_max_crisp_score": 87.55597014925372,
    "n_samples": 61,
    "method": "sampled own real input domain through ctx.engine.infer_component"
  },
  "M": {
    "kitchen/cold_period": {
      "empirical_min_crisp_score": 12.444029850746269,
      "empirical_max_crisp_score": 87.55597014925372,
      "n_samples": 961
    },
    "general_residential/warm_period": {
      "empirical_min_crisp_score": 12.444029850746269,
      "empirical_max_crisp_score": 87.55597014925372,
      "n_samples": 961
    },
    "kitchen/warm_period": {
      "empirical_min_crisp_score": 12.444029850746269,
      "empirical_max_crisp_score": 87.55597014925372,
      "n_samples": 961
    }
  },
  "final_index": {
    "note": "evaluation_multi_component_grid not available (DB busy or missing): IO Error: Could not set lock on file \"/home/ivan/python_scripts/air_ml/data/iaq_hfis/iaq_hfis.duckdb\": Conflicting lock is held in /usr/bin/python3.13 (PID 17325) by user ivan. See also https://duckdb.org/docs/stable/connect/concurrency"
  }
}
```