import csv
import json
import pytest

from healthdata.nhanes.downloader import (
    download_and_extract_docs,
    download_nhanes_data,
    download_nhanes_dataset,
    extract_date_from_url,
    get_file_links_for_component,
    parse_nhanes_doc_variables,
)


class _DummyResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_extract_date_from_url_cycle_and_year_and_fallback():
    # We expect the function to extract the cycle or year based on the URL similar to below
    assert extract_date_from_url("https://example.org/2017-2018/doc.htm") == "2017-2018"
    assert extract_date_from_url("https://example.org/data/2019/file.xpt") == "2019"
    assert extract_date_from_url("https://example.org/no-date") == "nodate"


def test_parse_nhanes_doc_variables_extracts_basic_fields():
    # this is currently what we expect to find in the HTML
    html = """
    <html><body>
    Variable Name: SEQN
    SAS Label: Respondent sequence number
    English Text: Unique participant identifier
    Target: Both males and females
    </body></html>
    """

    rows = parse_nhanes_doc_variables(html, "https://example.org/doc.htm")

    assert len(rows) == 1
    assert rows[0]["variable_name"] == "SEQN"
    assert rows[0]["label"] == "Respondent sequence number"
    assert rows[0]["description"] == "Unique participant identifier"
    assert "value_meanings" in rows[0]
    assert rows[0]["link"] == "https://example.org/doc.htm"


def test_parse_value_table_keeps_codes_and_labels_not_counts():
    html = """
    <div><dl><dt>Variable Name:</dt><dd>RIAGENDR</dd>
    <dt>SAS Label:</dt><dd>Gender</dd>
    <dt>English Text:</dt><dd>Gender of the participant.</dd></dl>
    <table><thead><tr><th>Code or Value</th><th>Value Description</th>
    <th>Count</th><th>Cumulative</th><th>Skip to Item</th></tr></thead>
    <tbody><tr><td>1</td><td>Male</td><td>4611</td><td>4611</td><td></td></tr>
    <tr><td>2</td><td>Female</td><td>4643</td><td>9254</td><td></td></tr>
    <tr><td>.</td><td>Missing</td><td>0</td><td>9254</td><td></td></tr></tbody></table></div>
    """
    rows = parse_nhanes_doc_variables(html, "https://example.org/DEMO_J.htm")
    assert rows[0]["label"] == "Gender"
    assert json.loads(rows[0]["value_meanings"]) == [
        {"code": "1", "meaning": "Male"},
        {"code": "2", "meaning": "Female"},
        {"code": ".", "meaning": "Missing"},
    ]


def test_get_file_links_for_component_filters_years(monkeypatch):
    # On NHANES website, the files are linked in this format:
    expected_html = """
    <table>
      <tr>
        <td>2017-2018</td>
        <td><a href="/nchs/nhanes/2017-2018/P_DEMO.htm">P_DEMO</a></td>
        <td><a href="/nchs/nhanes/2017-2018/P_DEMO.xpt">P_DEMO</a></td>
      </tr>
      <tr>
        <td>2015-2016</td>
        <td><a href="/nchs/nhanes/2015-2016/OLD_DEMO.htm">OLD_DEMO</a></td>
        <td><a href="/nchs/nhanes/2015-2016/OLD_DEMO.xpt">OLD_DEMO</a></td>
      </tr>
    </table>
    """

    def _fake_get(url, params=None):
        assert params == {"Component": "Demographics"}
        return _DummyResponse(expected_html)

    monkeypatch.setattr("healthdata.nhanes.downloader.requests.get", _fake_get)

    links = get_file_links_for_component("Demographics", years=["2017-2018"])

    assert len(links) == 1
    assert links[0]["years"] == "2017-2018"
    assert links[0]["doc_url"].endswith("/P_DEMO.htm")
    assert links[0]["xpt_url"].endswith("/P_DEMO.xpt")


def test_download_includes_codebooks_by_default(tmp_path, monkeypatch):
    entry = {
        "years": "2017-2018",
        "xpt_url": "https://example.org/2017/DEMO_J.xpt",
        "doc_url": "https://example.org/2017/DEMO_J.htm",
    }
    monkeypatch.setattr("healthdata.nhanes.downloader.get_file_links_for_component",
        lambda *args, **kwargs: [entry])
    data_downloads = []
    doc_downloads = []
    monkeypatch.setattr("healthdata.nhanes.downloader.download_file",
        lambda url, path: data_downloads.append((url, path)))
    monkeypatch.setattr("healthdata.nhanes.downloader.download_and_extract_docs",
        lambda url, folder: doc_downloads.append((url, folder)))

    download_nhanes_data(str(tmp_path), components=["Demographics"], years=["2017-2018"])

    folder = tmp_path / "2017-2018" / "2017" / "Demographics"
    assert data_downloads == [(entry["xpt_url"], str(folder / "DEMO_J.xpt"))]
    assert doc_downloads == [(entry["doc_url"], str(folder))]

    doc_downloads.clear()
    download_nhanes_data(str(tmp_path), components=["Demographics"],
        years=["2017-2018"], with_docs=False)
    assert len(data_downloads) == 2
    assert doc_downloads == []


def test_download_specific_dataset_downloads_data_and_docs(tmp_path, monkeypatch):
    entry = {
        "years": "2017-2018",
        "xpt_url": "https://example.org/2017/DEMO_J.XPT",
        "doc_url": "https://example.org/2017/DEMO_J.htm",
    }
    lookup_calls = []
    data_downloads = []
    doc_downloads = []

    def fake_get_links(component, **kwargs):
        lookup_calls.append((component, kwargs))
        return [entry]

    monkeypatch.setattr("healthdata.nhanes.downloader.get_file_links_for_component", fake_get_links)
    monkeypatch.setattr(
        "healthdata.nhanes.downloader.download_file",
        lambda url, path: data_downloads.append((url, path)),
    )
    monkeypatch.setattr(
        "healthdata.nhanes.downloader.download_and_extract_docs",
        lambda url, folder: doc_downloads.append((url, folder)),
    )

    path = download_nhanes_dataset(
        dataset="demo_j",
        component="Demographics",
        cycle="2017-2018",
        output_dir=str(tmp_path),
    )

    expected_path = tmp_path / "2017-2018" / "2017" / "Demographics" / "DEMO_J.XPT"
    assert path == expected_path
    assert lookup_calls[0][0] == "Demographics"
    assert lookup_calls[0][1]["years"] == ["2017-2018"]
    assert data_downloads == [(entry["xpt_url"], str(expected_path))]
    assert doc_downloads == [(entry["doc_url"], str(expected_path.parent))]


def test_download_specific_dataset_can_skip_docs(tmp_path, monkeypatch):
    entry = {
        "years": "2017-2018",
        "xpt_url": "https://example.org/2017/DEMO_J.XPT",
        "doc_url": "https://example.org/2017/DEMO_J.htm",
    }
    doc_downloads = []
    monkeypatch.setattr(
        "healthdata.nhanes.downloader.get_file_links_for_component",
        lambda *args, **kwargs: [entry],
    )
    monkeypatch.setattr("healthdata.nhanes.downloader.download_file", lambda *args: None)
    monkeypatch.setattr(
        "healthdata.nhanes.downloader.download_and_extract_docs",
        lambda *args: doc_downloads.append(args),
    )

    download_nhanes_dataset(
        dataset="DEMO_J",
        component="Demographics",
        cycle="2017-2018",
        output_dir=str(tmp_path),
        with_docs=False,
    )

    assert doc_downloads == []


def test_download_specific_dataset_raises_for_unknown_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "healthdata.nhanes.downloader.get_file_links_for_component",
        lambda *args, **kwargs: [],
    )

    with pytest.raises(LookupError, match="UNKNOWN.*Laboratory / 2017-2018"):
        download_nhanes_dataset(
            dataset="UNKNOWN",
            component="Laboratory",
            cycle="2017-2018",
            output_dir=str(tmp_path),
        )


def test_codebook_helper_saves_only_documentation(tmp_path, monkeypatch):
    html = """Variable Name: RIAGENDR
    SAS Label: Gender
    English Text: Gender of the participant.
    Target: Both males and females
    """
    monkeypatch.setattr("healthdata.nhanes.downloader.requests.get",
        lambda url: _DummyResponse(html))

    download_and_extract_docs("https://example.org/2017/DEMO_J.htm", str(tmp_path))

    assert [path.name for path in tmp_path.iterdir()] == ["DEMO_J_variables.csv"]
    with (tmp_path / "DEMO_J_variables.csv").open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert rows[0]["variable_name"] == "RIAGENDR"
    assert rows[0]["label"] == "Gender"
