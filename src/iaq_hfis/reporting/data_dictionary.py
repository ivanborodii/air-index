"""``output_data_dictionary.csv``: one row per column of every graph-ready
CSV file, built directly from :data:`iaq_hfis.reporting.exports.COLUMNS` --
the same registry ``exports.py`` uses to write the files, so the dictionary
can never drift out of sync with what's actually exported.

Documents the full, stable schema of every possible export, not just the
files a particular run happened to produce (a data dictionary is a
reference for interpreting any export, not a report of one run's data
availability).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iaq_hfis.reporting.exports import COLUMNS

OUTPUT_DATA_DICTIONARY = "output_data_dictionary.csv"


def build_data_dictionary() -> pd.DataFrame:
    rows = [
        {"file": filename, "column": col.name, "dtype": col.dtype, "unit": col.unit, "description": col.description}
        for filename, columns in COLUMNS.items()
        for col in columns
    ]
    return pd.DataFrame(rows, columns=["file", "column", "dtype", "unit", "description"])


def write_data_dictionary(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / OUTPUT_DATA_DICTIONARY
    build_data_dictionary().to_csv(path, index=False)
    return path
