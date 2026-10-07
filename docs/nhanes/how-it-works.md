# How It Works

When you read NHANES data, you will find its documentation in the pandas DataFrame, under `df.attrs`. It comes
from the official CDC codebook directly. For examples, start with the [NHANES guide](getting-started.md).

## Downloading

`download_nhanes_data` is the main entry point: it downloads data and codebooks
together by default. Use `with_docs=False` for data only. The lower-level
`downloader.download_and_extract_docs` helper saves one codebook CSV without
downloading data; it is only needed for documentation-only downloads.

`downloader.py` reads CDC's dataset listings, filters by component and cycle,
and saves XPT files under `<output_dir>/<cycle>/<year>/<component>/`.
Existing data files are skipped. With `with_docs=True`, each codebook is saved as `<dataset>_variables.csv`,
with `variable_name`, `label`, `description`, `value_meanings`, and `link`. Codebooks are refreshed even if the XPT already exists. A documentation download failure logs a warning and does not stop the remaining downloads.

## Reading and Documentation

`reader.py` reads the XPT with pandas and loads its variables CSV. SAS labels
become snake_case column names; repeated labels get numbered suffixes.
Original codes, descriptions, meanings, and links are attached under
`df.attrs["documentation"]` and `df.attrs["documentation_df"]`.

`get_column_doc` retrieves a column's metadata by its current name or original
NHANES code. If the codebook is missing or unreadable, the reader returns the
data with its original names and logs a warning.

## Categorical Data

The parser reads codes and meanings from separate HTML table cells. Counts
and skip instructions are not labels. Meanings are stored as JSON pairs such
as `{"code": "1", "meaning": "Male"}`.

With `decode_categories=True`, the reader maps discrete numeric codes to labels and creates pandas categoricals. Missing observations remain missing,
unknown codes stay visible, and range-based variables stay numeric. Decoding
is off by default and works independently of column renaming and metadata.

## Search

`search.py` owns variable search and local file inventory. `search_variables`
reads CDC's variable catalogue by default. Passing `search_dir` switches to
offline search of downloaded variables CSVs. Both return a pandas DataFrame
and support component and cycle/year filters.

`search_nhanes_local_data` lists local files and infers cycle, year, and
component from their folders. Its printed inventory uses `rich` when installed,
otherwise plain pandas text. Existing imports from `reader` still work.

## Limits

CDC page changes can require parser updates. Downloads have no automatic
retry or integrity check. Folder metadata is inferred, not verified against
the codebook. DataFrame attributes do not survive CSV export. Labels do not
harmonize variables across cycles or account for survey weights.
