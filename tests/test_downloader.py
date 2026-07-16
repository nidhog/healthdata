from healthdata.nhanes.downloader import (
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
    assert rows[0]["link"] == "https://example.org/doc.htm"


def test_get_file_links_for_component_filters_years(monkeypatch):
    # On NHANES website, the files are linked in this format:
    html = """
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
        return _DummyResponse(html)

    monkeypatch.setattr("healthdata.nhanes.downloader.requests.get", _fake_get)

    links = get_file_links_for_component("Demographics", years=["2017-2018"])

    assert len(links) == 1
    assert links[0]["years"] == "2017-2018"
    assert links[0]["doc_url"].endswith("/P_DEMO.htm")
    assert links[0]["xpt_url"].endswith("/P_DEMO.xpt")
