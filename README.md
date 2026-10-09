# Health Data Downloader Package
The Health Data Downloader is a Python package that makes it easy to download and read real world health data.

Current data sources supported:
* **NHANES** National Health and Nutrition Examination Survey (CDC)

It enables you to search, download and read data that also includes the meaning of codes and values, as well as storing categorical data with meaning such as Female/Male instead of 1/0.
## The NHANES Submodule
If you want to download health data from NHANES this module can help you not only download the data but also add documentation from the official NHANES website, and read this data into a pandas dataframe.

[NHANES](https://www.cdc.gov/nchs/nhanes/about/) is the National Health and Nutrition Examination Survey which collects data about the health of adults and children in the United States.

_Note: This is not an official repository from the NHANES project nor the CDC_

This project provides workflows that enable you to:
- discover and download datasets from NHANES by component (meaning what type of data like Laboratory data, examination etc.) and by cycle (which years)
- read the XPT files into a pandas DataFrames
- extract NHANES variable documentation into CSV files and rename variable codes into human-readable names (such as `heart_rate` instead of `LF321`)
- search and summarize local files if they are already downloaded

## Quick start
For a runnable walkthrough of variable search, downloads, DataFrame documentation,
and labeled categories, open the [NHANES download notebook](notebooks/nhanes_download.ipynb)
or [run it in Google Colab](https://colab.research.google.com/github/nidhog/healthdata/blob/main/notebooks/nhanes_download.ipynb).

For a focused laboratory example, use the [hs-CRP notebook](notebooks/nhanes_laboratory.ipynb)
or [open it in Colab](https://colab.research.google.com/github/nidhog/healthdata/blob/main/notebooks/nhanes_laboratory.ipynb).

In thie quick start we will:
1. Install required packages.
2. Run a download.
3. Read and inspect data.

```bash
pip install healthdata
```
You can choose which `components` you want to download (such as Demographics, Laboratory etc.) and which years (can be either "2017-2020" or "2016"). This will also download documentation about these fields from the NHANES website to add them when the data is read.
If the data is already downloaded in the output directory the module will log this and skip the download.
```python
from healthdata.nhanes.downloader import download_nhanes_data

download_nhanes_data(
    components=["Demographics", "Examination"],
    output_dir="nhanes_data",
    years=["2017-2018"],
)
```

You can read this data now and inspect **the official documentation directly in the dataframe**:

```python
from healthdata.nhanes import read_nhanes_data, get_column_doc

df = read_nhanes_data(
    "nhanes_data/2017-2018/2017/Demographics/DEMO_J.XPT",
    decode_categories=True,
    allow_download_prompt=False,
)
print(df["gender"].head())  # Male/Female, as a pandas categorical instead of 1/0
print(get_column_doc(df, "gender"))
print(df.attrs["documentation_df"].head())
```

You can also **search the CDC catalogue for variables like "blood pressure"** without downloading data files:

```python
from healthdata.nhanes import search_variables

matches = search_variables("blood pressure", component="Examination", years=["2017-2018"])
print(matches[["variable_name", "description", "dataset", "cycle"]].head())
```

Or search your downloaded codebooks offline (local data):

```python
matches = search_variables("gender", search_dir="nhanes_data")
print(matches[["variable_name", "dataset", "cycle", "data_path"]].head())
```

See the [NHANES guide here](docs/nhanes/getting-started.md) for more info on access to docs, categorical data, and search options, or [how it works](docs/nhanes/how-it-works.md)
for the data flow.

## Current caveats
- HTML codebook parsing depends on current NHANES page text patterns. CDC page structure changes may require parser updates.
- Network errors and partial downloads are not retried automatically.

## Upcoming Additions
Planned additions include NCBI GEO and other open health and biomedical datasets. The current release supports NHANES only.

## License
This project is licensed under the [MIT License](LICENSE). Commercial use is permitted under its terms. Downloaded datasets may be subject to separate terms set by their respective providers.

For paid support or consulting, contact the author at contact@ismail.bio.

## Author
[Ismail Elouafiq](https://ismail.bio)

Contact: contact@ismail.bio

## Citing healthdata
If you use healthdata in your research, please cite it. Use the "Cite this repository" button on GitHub, or:

Elouafi