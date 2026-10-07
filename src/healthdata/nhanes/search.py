"""Search the CDC variable catalogue and local NHANES files"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .utils import resolve_local_file
from .settings import DEFAULT_BASE_DOMAIN

logger = logging.getLogger(__name__)

SEARCH_COLUMNS = [
	"variable_name",
	"label",
	"description",
	"value_meanings",
	"link",
	"dataset",
	"dataset_description",
	"cycle",
	"year",
	"component",
	"data_path",
	"documentation_path",
]


def search_variables(
	query: str,
	search_dir: Optional[str] = None,
	*,
	component: Optional[str] = None,
	years: Optional[List[str]] = None,
) -> pd.DataFrame:
	"""Search CDC's catalogue, or local codebooks if search_dir is given.

	Matches are case-insensitive, literal text. Component and year filters
	work with either source.
	TODO: add synonym aware search because currently it only matches literal text
	"""
	if not isinstance(query, str) or not query.strip():
		raise ValueError("query must be a non-empty string")
	query = query.strip()

	if search_dir is None:
		rows = _search_catalogue(query, component)
	else:
		rows = _search_local_variables(query, search_dir)
	result = pd.DataFrame(rows, columns=SEARCH_COLUMNS)

	if component:
		result = result.loc[result["component"].eq(component)]
	if years:
		requested_years = {str(year) for year in years}
		keep = []
		for cycle in result["cycle"]:
			cycle = str(cycle)
			start_year, _, end_year = cycle.partition("-")
			keep.append(
				cycle in requested_years
				or start_year in requested_years
				or end_year in requested_years
			)
		result = result.loc[keep]
	return result.reset_index(drop=True)


def _search_catalogue(query: str, component: Optional[str]) -> List[Dict[str, Any]]:
	url = DEFAULT_BASE_DOMAIN + "/nchs/nhanes/search/variablelist.aspx"
	params = {}
	if component:
		params["Component"] = component
	response = requests.get(url, params=params, timeout=60)
	response.raise_for_status()

	soup = BeautifulSoup(response.text, "html.parser")
	required_headers = {"Variable Name", "Variable Description", "Data File Name", "Begin Year", "EndYear"}
	search_fields = ["Variable Name", "Variable Description", "Data File Description"]
	query = query.casefold()
	results = []
	found_catalogue = False

	for table in soup.find_all("table"):
		headers = [cell.get_text(" ", strip=True) for cell in table.select("tr th")]
		if not required_headers.issubset(headers):
			continue
		found_catalogue = True

		for row in table.select("tr"):
			cells = row.find_all("td", recursive=False)
			if len(cells) != len(headers):
				continue
			values = [cell.get_text(" ", strip=True) for cell in cells]
			record = dict(zip(headers, values))
			text = " ".join(record.get(field, "") for field in search_fields)
			if query not in text.casefold():
				continue

			dataset = record["Data File Name"]
			start_year = record["Begin Year"]
			end_year = record["EndYear"]
			codebook_url = f"{DEFAULT_BASE_DOMAIN}/Nchs/Data/Nhanes/Public/{start_year}/DataFiles/{dataset}.htm"
			results.append({
				"variable_name": record["Variable Name"],
				"description": record["Variable Description"],
				"dataset": dataset,
				"dataset_description": record.get("Data File Description"),
				"cycle": f"{start_year}-{end_year}",
				"year": start_year,
				"component": record.get("Component"),
				"link": codebook_url,
			})

	if not found_catalogue:
		raise ValueError("CDC variable catalogue table not found; the page format may have changed")
	return results


def _search_local_variables(query: str, search_dir: str) -> List[Dict[str, Any]]:
	inventory = search_nhanes_local_data(search_dir, print_results=False)
	results = []
	for _, entry in inventory.iterrows():
		if entry["type"] != "doc-variables-csv":
			continue
		path = Path(entry["path"])
		try:
			docs = pd.read_csv(path)
		except (OSError, ValueError) as error:
			logger.warning("Cannot search codebook %s: %s", path, error)
			continue
		if "variable_name" not in docs.columns:
			continue
		matched = pd.Series(False, index=docs.index)
		for field in ["variable_name", "label", "description"]:
			if field in docs:
				values = docs[field].astype("string")
				matched |= values.str.contains(query, case=False, regex=False, na=False)

		dataset = path.name[:-len("_variables.csv")]
		data_path = resolve_local_file(str(path.with_name(dataset + ".xpt")))
		if not Path(data_path).is_file():
			data_path = None

		for record in docs.loc[matched].to_dict("records"):
			record["dataset"] = dataset
			record["cycle"] = entry["cycle"]
			record["year"] = entry["year"]
			record["component"] = entry["component"]
			record["data_path"] = data_path
			record["documentation_path"] = str(path)
			results.append(record)
	return results


def search_nhanes_local_data(
	search_dir: str,
	*,
	recursive: bool = True,
	include_extensions: Optional[List[str]] = None,
	only_nhanes_like: bool = True,
	print_results: bool = True,
) -> pd.DataFrame:
	"""Search a local directory for NHANES-relevant files and return an inventory DataFrame."""
	root = Path(search_dir).expanduser().resolve()
	if not root.is_dir():
		raise NotADirectoryError(f"search_dir is not a valid directory: {search_dir}")

	extensions = set()
	for extension in include_extensions or ["xpt", "csv"]:
		extensions.add("." + extension.lower().lstrip("."))

	if recursive:
		files = root.rglob("*")
	else:
		files = root.glob("*")

	rows = []
	for path in files:
		if not path.is_file() or path.suffix.lower() not in extensions:
			continue

		if path.suffix.lower() == ".xpt":
			kind = "data-xpt"
		elif path.name.lower().endswith("_variables.csv"):
			kind = "doc-variables-csv"
		elif path.suffix.lower() == ".csv":
			kind = "csv"
		else:
			kind = "other"

		metadata = _folder_info(path)
		if only_nhanes_like and kind == "other":
			continue
		if only_nhanes_like and kind == "csv" and not metadata["cycle"]:
			continue

		try:
			stats = path.stat()
			size_kb = round(stats.st_size / 1024, 1)
			modified = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
		except OSError:
			size_kb = None
			modified = None

		rows.append({
			"type": kind,
			"cycle": metadata["cycle"],
			"year": metadata["year"],
			"component": metadata["component"],
			"file": path.name,
			"stem": path.stem,
			"ext": path.suffix.lower().lstrip("."),
			"size_kb": size_kb,
			"modified": modified,
			"path": str(path),
		})

	df = pd.DataFrame(rows)
	if df.empty:
		if print_results:
			print(f"No NHANES-like files found in: {root}")
		return df

	sort_cols = ["cycle", "component", "year", "type", "file"]
	df = df.sort_values(sort_cols, na_position="last").reset_index(drop=True)

	if print_results:
		_print_nhanes_search_results(df, root=str(root))

	return df


def _folder_info(path: Path) -> Dict[str, Optional[str]]:
	metadata = {"cycle": None, "year": None, "component": None}
	for index, folder in enumerate(path.parts):
		if not re.fullmatch(r"\d{4}-\d{4}", folder):
			continue
		metadata["cycle"] = folder
		remaining = path.parts[index + 1:]
		if remaining and re.fullmatch(r"\d{4}", remaining[0]):
			metadata["year"] = remaining[0]
			remaining = remaining[1:]
		if remaining:
			metadata["component"] = remaining[0]
		break
	return metadata


def _print_nhanes_search_results(df: pd.DataFrame, root: str) -> None:
	title = f"NHANES local files found in: {root}  (n={len(df)})"
	columns = ["type", "cycle", "year", "component", "file", "size_kb", "modified", "path"]
	display = df[columns].fillna("")
	counts = df["type"].value_counts(dropna=False)
	summary = ", ".join(f"{kind}={count}" for kind, count in counts.items())

	try:
		from rich.console import Console
		from rich.table import Table

		console = Console()
		table = Table(title=title, show_lines=False, header_style="bold")
		table.add_column("Type", style="cyan", no_wrap=True)
		table.add_column("Cycle", style="magenta", no_wrap=True)
		table.add_column("Year", style="magenta", no_wrap=True)
		table.add_column("Component", style="green")
		table.add_column("File", style="white")
		table.add_column("Size KB", justify="right")
		table.add_column("Modified", style="dim", no_wrap=True)
		table.add_column("Path", style="dim")

		for row in display.itertuples(index=False, name=None):
			table.add_row(*[str(value) for value in row])

		console.print(table)
		console.print(f"Summary: {summary}", style="bold", markup=False)
		return
	except Exception:
		pass

	print(title)
	with pd.option_context("display.max_rows", 200, "display.max_colwidth", 120, "display.width", 200):
		print(display.to_string(index=False))
	print(f"Summary: {summary}")