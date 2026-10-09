# NHANES in pandas

`healthdata` includes variable documentation in your pandas DataFrame: original
codes, descriptions, value meanings, and links to CDC codebooks. **You can look
up what a column means without leaving your analysis.**

You need Python 3.11 or newer. Install the published package with
`pip install healthdata`.

## Download and Read

Use `download_nhanes_data` for the usual workflow. It downloads both data and
documentation by default; you do not need to call a separate documentation helper.
Set `with_docs=False` if you only want the XPT files.

```python
from healthdata.nhanes import download_nhanes_data, read_nhanes_data

download_nhanes_data(
    output_dir="nhanes_data",
    components=["Demographics"],
    years=["2017-2018"],
    with_docs=True,
)

path = "nhanes_data/2017-2018/2017/Demographics/DEMO_J.XPT"
df = read_nhanes_data(path, allow_download_prompt=False)
```

Components are `Demographics`, `Dietary`, `Examination`, `Laboratory`, and
`Questionnaire`. For example, pass several cycles in `years`, or a single year such as
`"2017"` to match cycles containing 2017. Omitting `years` downloads all available cycles for the components.

Data and codebooks are saved together as XPT files and `*_variables.csv`.
Existing XPT files are skipped. Codebooks (containing documentation about the xpt files) are refreshed with `with_docs=True`.
(`allow_download_prompt=False` makes missing files raise an error instead of
getting an interactive question to download them)

### Download one Dataset only

Use `download_nhanes_dataset` when you know the specific dataset, component, and full cycle you need. Unlike `download_nhanes_data`, it downloads only that dataset (and its codebook by default).

```python
from healthdata.nhanes import download_nhanes_dataset, read_nhanes_data

path = download_nhanes_dataset(
    dataset="LBXSAL",
    component="Laboratory",
    cycle="2017-2018",
    output_dir="nhanes_data",
)
df = read_nhanes_data(str(path), use_csv_for_labels=False, allow_download_prompt=False)
```

Pass the full cycle label (for example, `"2017-2018"`), not just a year that could match multiple cycles. Use `with_docs=False` to download only the XPT file (without documentation codebooks).

### Download a Codebook (data documentation and meanings) Only

If you already have an XPT file and only need its documentation, use the
lower-level helper from `downloader`:

```python
from healthdata.nhanes.downloader import download_and_extract_docs

download_and_extract_docs(
    doc_url="https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.htm",
    out_dir="nhanes_data/2017-2018/2017/Demographics",
)
```

This saves `DEMO_J_variables.csv` beside your data. It does not download an XPT
file. Existing package-level imports of this helper still work for compatibility.

## Documentation in the DataFrame

```python
from healthdata.nhanes import get_column_doc

doc = get_column_doc(df, "gender")
print(doc["variable_name"])  # RIAGENDR
print(doc["description"])    # Gender of the participant.
print(doc["value_meanings"]) # Code/meaning pairs, e.g. 1: Male, 2: Female
print(doc["link"])           # Official CDC codebook

print(df.attrs["documentation_df"].head())
```

Metadata is attached by default under `df.attrs["documentation"]`, keyed by
column name, and `df.attrs["documentation_df"]`, a table with one row per column.
Each entry contains `variable_name`, `label`, `description`, `value_meanings`,
and `link`. `get_column_doc` also accepts the original NHANES code and returns
`None` for an unknown column.

Column names come from the codebook's SAS labels, converted to snake_case.
Set `use_csv_for_labels=False` to keep codes such as `RIAGENDR`, or
`attach_documentation=False` to omit metadata. If codebooks are stored
elsewhere, pass `local_doc_csv_dir`.

Pandas attributes are in-memory metadata. CSV exports do not keep them, so
retain the variables CSV or export the documentation table separately.

## Easily handle categorical Data

```python
df = read_nhanes_data(path, decode_categories=True, allow_download_prompt=False)
print(df["gender"].cat.categories)  # Male, Female
print(df["gender"].value_counts())
```

`decode_categories=True` replaces discrete numeric codes with their documented labels and uses the pandas categorical dtype. **It is off by default so existing
analysis keeps numeric codes.**

- Responses such as `Refused` and `Don't know` remain labeled responses, not missing values.
- Unknown codes are kept as extra categories rather than silently discarded
- Without a usable codebook, values stay unchanged

This works whether you use readable names or original NHANES column codes.
## Searching for data on NHANES catalogue or locally
Wanna search for "blood pressure" data?


```python
from healthdata.nhanes.search import search_variables

matches = search_variables(
    "blood pressure", component="Examination", years=["2017-2018"]
)
print(matches[["variable_name", "description", "dataset", "cycle", "link"]].head())
```

By default, search uses CDC's variable catalogue and needs internet access.
It matches literal text, ignoring case, in variable codes, variable descriptions,
and dataset descriptions. Results show which files and cycles contain a match.
Omit `component` or `years` to search more broadly. Catalogue results do not
include value meanings; download the dataset's codebook to get those.

For offline search, point to your downloaded codebooks:

```python
matches = search_variables("gender", search_dir="nhanes_data")
print(matches[["variable_name", "dataset", "cycle", "data_path"]])
```

Offline search matches variable codes, labels, and descriptions. It returns
`documentation_path` and, if an XPT is present, `data_path`. Only codebooks
under that directory are searched. The same component and year filters work
offline. No match returns an empty DataFrame.

To list local files rather than search their variables:

```python
from healthdata.nhanes.search import search_nhanes_local_data

inventory = search_nhanes_local_data("nhanes_data", print_results=False)
print(inventory[["cycle", "component", "file", "path"]].head())
```

## Common Issues

Missing names or meanings? Check that the matching variables CSV is present. Rerun the download with `with_docs=True` to refresh older codebooks.

Downloads are not retried automatically. If a download was interrupted,
delete the incomplete XPT before retrying. CDC page changes can affect parsing;
offline codebook search does not depend on CDC being reachable.

Labels don't harmonize definitions across cycles or replace survey weights.
Check CDC's codebook before combining data. See [how it works](how-it-works.md) for the data flow.
