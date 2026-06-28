# Health Data Downloader Package
The Health Data Downloader is a Python package that makes it easy to download and read real world health data.

At this stage, the only data available is data from NHANES (National Health and Nutrition Examination Survey), more will be available soon.
## The NHANES Submodule
[NHANES](https://www.cdc.gov/nchs/nhanes/about/) is the National Health and Nutrition Examination Survey which collects data about the health of adults and children in the United States.

_Note: This is not an official repository from the NHANES project nor the CDC_

Downloading, reading data from NHANES, and even trying to make it match the docs can take a lot of time. This project provides a `healthdata` package for health dataset workflows, with NHANES support as a dedicated submodule to help:
- discover and download datasets from NHANES by component (meaning what type of data like Laboratory data, examination etc.) and by cycle (years)
- extract NHANES variable documentation into CSV files
- read the XPT files into pandas DataFrames
- rename raw NHANES variable codes into human-readable snake_case column names
- search and summarize local files if they are already downloaded

It is designed for fast local workflows and is structured so additional health-data sources can be added beside NHANES over time.

### Downloading longitudinal health data from NHANES
The `healthdata.nhanes` submodule enables you to:
- fetch dataset links from the CDC NHANES search page by component
- supports cycle filtering by year (`2017`) or full cycle (`"2017-2018"`)
- downloads XPT files
- downloads and parses NHANES HTML codebook pages
- writes parsed variable metadata to `*_variables.csv`

### Reader features

- reads `.xpt` files with pandas (`pd.read_sas`)
- optionally renames columns using `*_variables.csv` labels
- applies safe snake_case normalization for column names
- supports local file discovery with metadata summary (`search_nhanes_local_data`)
- can prompt the user to download missing files when a target XPT path does not exist

## Typical output layout

By default (based on current logic), data is saved in this structure:

```text
<output_dir>/
  <cycle>/
    <date_or_year>/
      <component>/
        <DATASET>.XPT
        <DATASET>_variables.csv
```

Example:

```text
nhanes_data/
  2017-2018/
    2017/
      Demographics/
        DEMO_J.XPT
        DEMO_J_variables.csv
```

## Quick start
In thie quick start we will:
1. Create and activate a Python environment.
2. Install required packages.
3. Run a download.
4. Read and inspect data.

```bash
pip install healthdata
```

```python
from healthdata.nhanes.downloader import download_nhanes_data

download_nhanes_data(
    components=["Demographics", "Examination"],
    output_dir="nhanes_data",
    years=["2017-2018"],
)
```

```python
from healthdata.nhanes.reader import read_nhanes_data, search_nhanes_local_data

df = read_nhanes_data("nhanes_data/2017-2018/2017/Demographics/DEMO_J.XPT")
print(df.head())

inventory = search_nhanes_local_data(search_dir="nhanes_data")
print(inventory.head())
```
Simple as that!

## Docs

- NHANES module behavior and internal flow: `docs/nhanes/how-it-works.md`
- Setup and first run walkthrough: `docs/nhanes/getting-started.md`

## Current caveats
- HTML codebook parsing depends on current NHANES page text patterns; CDC page structure changes may require parser updates.
- Network errors and partial downloads are not retried automatically.

## License
This project is open source and free for personal, academic, and non-commercial use.

For commercial use, you must contact the author first to obtain permission.

## Author
[Ismail Elouafiq](https://ismail.bio)

Contact: contact@ismail.bio
