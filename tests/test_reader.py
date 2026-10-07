import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from healthdata.nhanes.reader import get_column_doc, read_nhanes_data, snake_case
from healthdata.nhanes.search import search_nhanes_local_data, search_variables


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


@pytest.mark.parametrize("rename,attach", [(True, True), (False, False)])
def test_reader_decodes_discrete_values_and_resolves_filename_case(tmp_path, monkeypatch, rename, attach):
    xpt_path = tmp_path / "DEMO_J.xpt"
    xpt_path.write_bytes(b"placeholder")
    pd.DataFrame([
        {"variable_name": "RIAGENDR", "label": "Gender", "value_meanings": json.dumps([
            {"code": "1", "meaning": "Male"}, {"code": "2", "meaning": "Female"},
            {"code": ".", "meaning": "Missing"}])},
        {"variable_name": "RIDAGEYR", "label": "Age", "value_meanings": json.dumps([
            {"code": "0 to 80", "meaning": "Range of Values"},
            {"code": ".", "meaning": "Missing"}])},
    ]).to_csv(tmp_path / "demo_j_variables.csv", index=False)
    def read_sas(path):
        assert Path(path).name == "DEMO_J.xpt"
        return pd.DataFrame({"RIAGENDR": [1.0, 2.0, float("nan"), 9.0], "RIDAGEYR": [30, 40, 50, 60]})
    monkeypatch.setattr("healthdata.nhanes.reader.pd.read_sas", read_sas)
    result = read_nhanes_data(str(tmp_path / "DEMO_J.XPT"), allow_download_prompt=False,
        use_csv_for_labels=rename, attach_documentation=attach, decode_categories=True)
    gender = result["gender" if rename else "RIAGENDR"]
    assert isinstance(gender.dtype, pd.CategoricalDtype)
    assert gender.iloc[:2].tolist() == ["Male", "Female"]
    assert pd.isna(gender.iloc[2])
    assert gender.iloc[3] == 9.0
    assert result["age" if rename else "RIDAGEYR"].tolist() == [30, 40, 50, 60]
    numeric = read_nhanes_data(str(xpt_path), allow_download_prompt=False)
    assert numeric["gender"].iloc[0] == 1.0


def test_search_variables_finds_files_and_cycles(tmp_path):
    for cycle, dataset in [("2015-2016", "BPX_I"), ("2017-2018", "BPX_J")]:
        folder = tmp_path / cycle / cycle[:4] / "Examination"
        folder.mkdir(parents=True)
        (folder / (dataset + ".XPT")).write_bytes(b"placeholder")
        pd.DataFrame([{"variable_name": "BPXSY1", "label": "Systolic blood pressure",
            "description": "First reading"}]).to_csv(folder / (dataset + "_variables.csv"), index=False)
    result = search_variables("BLOOD PRESSURE", str(tmp_path))
    assert set(result["dataset"]) == {"BPX_I", "BPX_J"}
    assert set(result["cycle"]) == {"2015-2016", "2017-2018"}
    assert all(Path(path).is_file() for path in result["data_path"])
    assert len(search_variables("BPXSY1", str(tmp_path))) == 2
    assert len(search_variables("first reading", str(tmp_path))) == 2
    assert search_variables("[", str(tmp_path)).empty
    with pytest.raises(ValueError, match="non-empty"):
        search_variables(" ", str(tmp_path))


def test_search_variables_uses_cdc_catalogue_and_filters(monkeypatch):
    html = """<table><tr><th>Variable Name</th><th>Variable Description</th>
    <th>Data File Name</th><th>Data File Description</th><th>Begin Year</th>
    <th>EndYear</th><th>Component</th><th>Use Constraints</th></tr>
    <tr><td>BPXSY1</td><td>Systolic reading</td><td>BPX_J</td><td>Blood Pressure</td>
    <td>2017</td><td>2018</td><td>Examination</td><td>None</td></tr>
    <tr><td>BPXSY1</td><td>Systolic reading</td><td>BPX_I</td><td>Blood Pressure</td>
    <td>2015</td><td>2016</td><td>Examination</td><td>None</td></tr></table>"""
    class Response:
        text = html
        def raise_for_status(self):
            pass
    def get(url, params, timeout):
        assert url.endswith("/search/variablelist.aspx")
        assert params == {"Component": "Examination"}
        assert timeout == 60
        return Response()
    monkeypatch.setattr("healthdata.nhanes.search.requests.get", get)
    result = search_variables("blood pressure", component="Examination", years=["2018"])
    assert result["dataset"].tolist() == ["BPX_J"]
    assert result["cycle"].tolist() == ["2017-2018"]
    assert result["link"].iloc[0].endswith("/2017/DataFiles/BPX_J.htm")
    assert search_variables("no match", component="Examination").empty
    Response.text = "<html>Service unavailable</html>"
    with pytest.raises(ValueError, match="catalogue table not found"):
        search_variables("blood pressure", component="Examination")


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


@pytest.mark.parametrize("plain_text", [False, True])
def test_search_inventory_options_and_printing(tmp_path, capsys, monkeypatch, plain_text):
    folder = tmp_path / "2017-2018" / "Examination"
    folder.mkdir(parents=True)
    (folder / "BPX_J.XPT").write_bytes(b"xpt")
    (folder / "merged.csv").write_text("value\n1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("notes", encoding="utf-8")
    (tmp_path / "random.csv").write_text("value\n1\n", encoding="utf-8")

    if plain_text:
        monkeypatch.setitem(sys.modules, "rich.console", None)
    inventory = search_nhanes_local_data(str(tmp_path))
    assert set(inventory["file"]) == {"BPX_J.XPT", "merged.csv"}
    assert inventory["component"].eq("Examination").all()
    assert inventory["year"].isna().all()
    output = capsys.readouterr().out
    if plain_text:
        assert "BPX_J.XPT" in output
    assert "Summary:" in output
    assert "data-xpt=1" in output
    assert "csv=1" in output

    inventory = search_nhanes_local_data(str(tmp_path), recursive=False,
        include_extensions=[".CSV", "txt"], only_nhanes_like=False, print_results=False)
    assert set(inventory["file"]) == {"notes.txt", "random.csv"}
    assert set(inventory["type"]) == {"other", "csv"}


def test_search_empty_results_keep_columns_with_filters(tmp_path):
    result = search_variables("missing", str(tmp_path), component="Examination", years=["2017"])
    assert result.empty
    assert "variable_name" in result.columns
    assert "cycle" in result.columns
