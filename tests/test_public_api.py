import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

import healthdata.nhanes as nhanes
from healthdata.nhanes import downloader, reader, search


def test_nhanes_public_api_exports_main_functions():
    assert callable(nhanes.download_nhanes_data)
    assert callable(nhanes.get_file_links_for_component)
    assert callable(nhanes.read_nhanes_data)
    assert callable(nhanes.get_column_doc)
    assert callable(nhanes.search_nhanes_local_data)
    assert callable(nhanes.search_variables)


def test_codebook_helper_stays_available_for_existing_imports():
    assert nhanes.download_and_extract_docs is downloader.download_and_extract_docs
    assert "download_and_extract_docs" not in nhanes.__all__
    assert "download_nhanes_data" in nhanes.__all__


def test_search_exports_preserve_reader_imports():
    assert nhanes.search_variables is search.search_variables
    assert reader.search_variables is search.search_variables
    assert nhanes.search_nhanes_local_data is search.search_nhanes_local_data
    assert reader.search_nhanes_local_data is search.search_nhanes_local_data


@pytest.mark.skipif(os.environ.get("HEALTHDATA_LIVE_SMOKE") != "1", reason="Opt-in live CDC smoke test")
def test_readme_quick_start_with_installed_package(tmp_path):
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    examples = re.findall(r"```python\n(.*?)```", readme, flags=re.DOTALL)
    assert len(examples) == 4
    examples[2] += "\nassert not matches.empty\nassert matches['cycle'].eq('2017-2018').all()\n"
    checks = """
import pandas as pd
assert len(df) > 0
assert isinstance(df['gender'].dtype, pd.CategoricalDtype)
assert df['gender'].cat.categories.tolist() == ['Male', 'Female']
assert get_column_doc(df, 'gender')['value_meanings'] == [
    {'code': '1', 'meaning': 'Male'}, {'code': '2', 'meaning': 'Female'},
    {'code': '.', 'meaning': 'Missing'}]
assert 'RIAGENDR' in matches['variable_name'].tolist()
assert matches['dataset'].eq('DEMO_J').all()
assert matches['cycle'].eq('2017-2018').all()
assert all(Path(path).is_file() for path in matches['data_path'])
print('README smoke passed:', len(df), 'participants')
"""
    script = "from pathlib import Path\n" + "\n".join(examples) + checks
    result = subprocess.run([sys.executable, "-I", "-c", script], cwd=tmp_path,
        capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
