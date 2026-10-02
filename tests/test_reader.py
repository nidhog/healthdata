from pathlib import Path

import pandas as pd

from healthdata.nhanes.reader import get_column_doc, read_nhanes_data, search_nhanes_local_data, snake_case


def test_snake_case_handles_spacing_and_symbols():
    assert snake_case(". Heart Rate (BPM)") == "heart_rate_bpm"
    assert snake_case("___") == "unnamed"


def test_read_nhanes_data_renames_columns_from_variables_csv(tmp_path, monkeypatch):
    xpt_path = tmp_path / "P_DEMO.xpt"
    xpt_path.write_bytes(b"placeholder")
    # we create a csv file similar to what we have
    csv_path = tmp_path / "P_DEMO_variables.csv"
    csv_path.write_text(
        "variable_name,label\n"
        "SEQN,Participant ID\n"
        "RIDAGEYR,Age\n"
        "DUPCOL,Age\n",
        encoding="utf-8",
    )

    source_df = pd.DataFrame({"SEQN": [1], "RIDAGEYR": [30], "DUPCOL": [31]})
    monkeypatch.setattr("healthdata.nhanes.reader.pd.read_sas", lambda _: source_df)

    result = read_nhanes_data(str(xpt_path), use_csv_for_labels=True)

    assert list(result.columns) == ["participant_id", "age", "age_2"]
    assert "documentation" in result.attrs
    assert result.attrs["documentation"]["participant_id"]["variable_name"] == "SEQN"


def test_read_nhanes_data_attaches_documentation_without_renaming(tmp_path, monkeypatch):
    xpt_path = tmp_path / "P_DEMO.xpt"
    xpt_path.write_bytes(b"placeholder")
    csv_path = tmp_path / "P_DEMO_variables.csv"
    csv_path.write_text(
        "variable_name,label,description,value_meanings,link\n"
        "SEQN,Participant ID,Unique id,\"[{\"\"code\"\": \"\"1\"\", \"\"meaning\"\": \"\"Yes\"\"}]\",https://example.org/doc.htm\n",
        encoding="utf-8",
    )

    source_df = pd.DataFrame({"SEQN": [1]})
    monkeypatch.setattr("healthdata.nhanes.reader.pd.read_sas", lambda _: source_df)

    result = read_nhanes_data(
        str(xpt_path),
        use_csv_for_labels=False,
        attach_documentation=True,
    )

    assert list(result.columns) == ["SEQN"]
    assert "documentation" in result.attrs
    assert result.attrs["documentation"]["SEQN"]["description"] == "Unique id"
    assert result.attrs["documentation"]["SEQN"]["value_meanings"] == [{"code": "1", "meaning": "Yes"}]
    assert get_column_doc(result, "SEQN")["label"] == "Participant ID"
    assert get_column_doc(result, "MISSING") is None


def test_search_nhanes_local_data_returns_expected_inventory(tmp_path):
    base = tmp_path / "2017-2020" / "2017" / "Demographics"
    base.mkdir(parents=True)

    (base / "P_DEMO.xpt").write_bytes(b"xpt")
    (base / "P_DEMO_variables.csv").write_text("variable_name,label\nSEQN,Participant ID\n", encoding="utf-8")
    (tmp_path / "random.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    result = search_nhanes_local_data(str(tmp_path), print_results=False)

    assert len(result) == 2
    assert set(result["type"]) == {"data-xpt", "doc-variables-csv"}
    assert set(result["cycle"]) == {"2017-2020"}
    assert set(result["component"]) == {"Demographics"}


def test_search_nhanes_local_data_invalid_dir_raises(tmp_path):
    missing = tmp_path / "does-not-exist"

    try:
        search_nhanes_local_data(str(missing), print_results=False)
    except NotADirectoryError as exc:
        assert "not a valid directory" in str(exc)
    else:
        raise AssertionError("Expected NotADirectoryError")
