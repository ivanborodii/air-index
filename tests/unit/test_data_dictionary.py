from iaq_hfis.reporting.data_dictionary import build_data_dictionary
from iaq_hfis.reporting.exports import COLUMNS


def test_every_export_column_has_exactly_one_dictionary_row():
    df = build_data_dictionary()
    expected = {(filename, col.name) for filename, columns in COLUMNS.items() for col in columns}
    actual = set(zip(df["file"], df["column"]))
    assert actual == expected  # no orphans in either direction


def test_no_duplicate_rows():
    df = build_data_dictionary()
    assert not df.duplicated(subset=["file", "column"]).any()


def test_every_row_has_a_nonempty_description():
    df = build_data_dictionary()
    assert (df["description"].str.len() > 0).all()


def test_write_data_dictionary_creates_file(tmp_path):
    from iaq_hfis.reporting.data_dictionary import write_data_dictionary

    path = write_data_dictionary(tmp_path)
    assert path.is_file()
    assert path.name == "output_data_dictionary.csv"
