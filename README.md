# Health Data Downloader Package
The Health Data Downloader is a Python package that makes it easy to download and read real world health data.

Current data sources supported:
* **NHANES** National Health and Nutrition Examination Survey (CDC)
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

You can read the data you already downloaded (you will be prompted to download it if it doesn't exist)
```python
from healthdata.nhanes.reader import read_nhanes_data, search_nhanes_local_data

df = read_nhanes_data("nhanes_data/2017-2018/2017/Demographics/DEMO_J.XPT")
print(df.head())

inventory = search_nhanes_local_data(search_dir="nhanes_data")
print(inventory.head())
```
That's all folks! Now you will see that your dataframe already includes documentation.
## Current caveats
- HTML codebook parsing depends on current NHANES page text patterns. CDC page structure changes may require parser updates.
- Network errors and partial downloads are not retried automatically.

## License
This project is open source and free for personal, academic, and non-commercial use.

For commercial use, you must contact the author first to obtain permission.

## Author
[Ismail Elouafiq](https://ismail.bio)

Contact: contact@ismail.bio
