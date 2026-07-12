import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .downloader import download_nhanes_data

logger = logging.getLogger(__name__)


def snake_case(s: str) -> str:
	s = s.strip().lower()
	s = re.sub(r"[^\w\s]", " ", s)
	s = re.sub(r"\s+", "_", s)
	s = re.sub(r"_+", "_", s).strip("_")
	return s or "unnamed"


def read_nhanes_data(
	file_path: str,
	use_csv_for_labels: bool = True,
	local_doc_csv_dir: Optional[str] = None,
	allow_download_prompt: bool = True,
) -> pd.DataFrame:
	"""
	Read an NHANES XPT file and optionally rename columns using <dataset>_variables.csv.

	use_csv_for_labels: If True, attempts to find a corresponding <dataset>_variables.csv file
		and uses it to rename columns based on the 'label' field.
		These can be downloaded using the `download_nhanes_data` function with `with_docs=True`
	"""
	if not os.path.exists(file_path):
		if allow_download_prompt:
			parts = file_path.split(os.sep)
			if len(parts) >= 4:
				component_candidate = parts[-2]
				cycle_candidate = parts[-4]

				if re.match(r"\d{4}-\d{4}", cycle_candidate):
					print(f"File not found: {file_path}")
					print(
						"It looks like you're missing data for "
						f"Component='{component_candidate}', Cycle='{cycle_candidate}'"
					)
					response = input("Would you like to try downloading it now? [y/N] ").lower().strip()
					if response == "y":
						output_dir = os.sep.join(parts[:-4])
						if not output_dir:
							output_dir = "."

						print(f"Downloading to {output_dir}...")
						download_nhanes_data(
							components=[component_candidate],
							output_dir=output_dir,
							years=[cycle_candidate],
						)
						if not os.path.exists(file_path):
							raise FileNotFoundError(
								f"Download completed but file is still missing: {file_path}"
							)
					else:
						raise FileNotFoundError(f"File not found: {file_path}")
				else:
					raise FileNotFoundError(f"File not found: {file_path}")
			else:
				raise FileNotFoundError(f"File not found: {file_path}")
		else:
			raise FileNotFoundError(f"File not found: {file_path}")

	try:
		df = pd.read_sas(file_path)
	except Exception as e:
		raise IOError(f"Failed to read XPT file {file_path}: {e}")

	if use_csv_for_labels:
		base_name = os.path.splitext(os.path.basename(file_path))[0]
		doc_csv_name = f"{base_name}_variables.csv"

		search_dirs = [os.path.dirname(file_path)]
		if local_doc_csv_dir:
			search_dirs.insert(0, local_doc_csv_dir)

		doc_csv_path = None
		for d in search_dirs:
			candidate = os.path.join(d, doc_csv_name)
			if os.path.exists(candidate):
				doc_csv_path = candidate
				break
		if not doc_csv_path:
			logger.warning(
				"Variables CSV not found for %s. Returning DataFrame with original column names.",
				base_name,
			)
			return df
		try:
			doc_df = pd.read_csv(doc_csv_path)
		except Exception as e:
			logger.warning(
				"Failed to read variables CSV for documentation %s: %s",
				doc_csv_path,
				e,
			)
			return df

		if "variable_name" not in doc_df.columns or "label" not in doc_df.columns:
			logger.warning(
				"Variables CSV for documentation %s missing 'variable_name' or 'label' columns.",
				doc_csv_path,
			)
			return df

		label_map = doc_df.dropna(subset=["variable_name", "label"]).set_index("variable_name")[
			"label"
		].to_dict()

		rename_map = {}
		used_names = set()

		def get_unique_name(base, existing):
			if base not in existing:
				return base
			i = 2
			while f"{base}_{i}" in existing:
				i += 1
			return f"{base}_{i}"

		for col in df.columns:
			original_col = col
			if original_col in label_map and str(label_map[original_col]).strip():
				new_name = snake_case(str(label_map[original_col]))
			else:
				new_name = snake_case(original_col)

			final_name = get_unique_name(new_name, used_names)
			used_names.add(final_name)
			rename_map[original_col] = final_name

		df = df.rename(columns=rename_map)
	return df


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
	if not root.exists() or not root.is_dir():
		raise NotADirectoryError(f"search_dir is not a valid directory: {search_dir}")

	exts = include_extensions or ["xpt", "csv"]
	exts = {("." + e.lower().lstrip(".")) for e in exts}

	cycle_re = re.compile(r"^\d{4}-\d{4}$")
	year_re = re.compile(r"^\d{4}$")

	def infer_parts(p: Path) -> Dict[str, Optional[str]]:
		parts = list(p.parts)
		cycle = None
		year = None
		component = None

		cycle_idx = None
		for i, name in enumerate(parts):
			if cycle_re.match(name):
				cycle = name
				cycle_idx = i
				break

		if cycle_idx is not None:
			if cycle_idx + 1 < len(parts) and year_re.match(parts[cycle_idx + 1]):
				year = parts[cycle_idx + 1]
				if cycle_idx + 2 < len(parts):
					component = parts[cycle_idx + 2]
			else:
				if cycle_idx + 1 < len(parts):
					component = parts[cycle_idx + 1]

		return {"cycle": cycle, "year": year, "component": component}

	def classify(p: Path) -> str:
		name = p.name.lower()
		if p.suffix.lower() == ".xpt":
			return "data-xpt"
		if name.endswith("_variables.csv"):
			return "doc-variables-csv"
		if p.suffix.lower() == ".csv":
			return "csv"
		return "other"

	def nhanes_like_filter(p: Path) -> bool:
		if p.suffix.lower() == ".xpt" or p.name.lower().endswith("_variables.csv"):
			return True

		if p.suffix.lower() != ".csv":
			return False

		meta = infer_parts(p)
		if meta.get("cycle"):
			return True

		stem = p.stem
		if stem.endswith("_variables"):
			xpt_candidate = p.with_name(stem.replace("_variables", "") + ".xpt")
			if xpt_candidate.exists():
				return True

		return False

	it = root.rglob("*") if recursive else root.glob("*")

	rows: List[Dict[str, Any]] = []
	for p in it:
		if not p.is_file():
			continue
		if p.suffix.lower() not in exts:
			continue
		if only_nhanes_like and not nhanes_like_filter(p):
			continue

		meta = infer_parts(p)
		kind = classify(p)

		try:
			st = p.stat()
			size_kb = st.st_size / 1024
			mtime = datetime.fromtimestamp(st.st_mtime)
		except OSError:
			size_kb = None
			mtime = None

		rows.append(
			{
				"type": kind,
				"cycle": meta.get("cycle"),
				"year": meta.get("year"),
				"component": meta.get("component"),
				"file": p.name,
				"stem": p.stem,
				"ext": p.suffix.lower().lstrip("."),
				"size_kb": None if size_kb is None else round(size_kb, 1),
				"modified": None if mtime is None else mtime.strftime("%Y-%m-%d %H:%M"),
				"path": str(p),
			}
		)

	df = pd.DataFrame(rows)
	if df.empty:
		if print_results:
			print(f"No NHANES-like files found in: {root}")
		return df

	sort_cols = ["cycle", "component", "year", "type", "file"]
	sort_cols = [c for c in sort_cols if c in df.columns]
	df = df.sort_values(sort_cols, na_position="last").reset_index(drop=True)

	if print_results:
		_print_nhanes_search_results(df, root=str(root))

	return df


def _print_nhanes_search_results(df: pd.DataFrame, root: str) -> None:
	"""Pretty-printer using rich when available, otherwise pandas text output."""
	title = f"NHANES local files found in: {root}  (n={len(df)})"

	try:
		from rich.console import Console
		from rich.table import Table
		from rich.text import Text

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

		for _, r in df.iterrows():
			table.add_row(
				str(r.get("type") or ""),
				str(r.get("cycle") or ""),
				str(r.get("year") or ""),
				str(r.get("component") or ""),
				str(r.get("file") or ""),
				"" if pd.isna(r.get("size_kb")) else str(r.get("size_kb")),
				str(r.get("modified") or ""),
				str(r.get("path") or ""),
			)

		counts = df["type"].value_counts(dropna=False).to_dict()
		summary = ", ".join([f"{k}={v}" for k, v in counts.items()])
		console.print(table)
		console.print(Text(f"Summary: {summary}", style="bold"))

		return

	except Exception:
		pass

	# TODO: log instead of print
	print(title)
	show_cols = ["type", "cycle", "year", "component", "file", "size_kb", "modified", "path"]
	show_cols = [c for c in show_cols if c in df.columns]
	df_out = df[show_cols].copy()

	with pd.option_context("display.max_rows", 200, "display.max_colwidth", 120, "display.width", 200):
		print(df_out.to_string(index=False))

	counts = df["type"].value_counts(dropna=False).to_dict()
	summary = ", ".join([f"{k}={v}" for k, v in counts.items()])
	print(f"Summary: {summary}")
