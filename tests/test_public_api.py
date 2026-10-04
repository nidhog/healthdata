import healthdata.nhanes as nhanes


def test_nhanes_public_api_exports_main_functions():
    assert callable(nhanes.download_nhanes_data)
    assert callable(nhanes.download_and_extract_docs)
    assert callable(nhanes.get_file_links_for_component)
    assert callable(nhanes.read_nhanes_data)
    assert callable(nhanes.get_column_doc)
    assert callable(nhanes.search_nhanes_local_data)
