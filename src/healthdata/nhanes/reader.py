import logging
import os
import re
import json
from typing import Any, Dict, Optional

import pandas as pd

from .utils import resolve_local_file
from .downloader import download_nhanes_data
from .search import search_nhanes_local_data as search_nhanes_local_data, search_variables as search_variables

logger = logging.getLogger(__name__)


def snake_case(s: str) -> str:
	s = s.strip().lower()
	s = re.sub(r"[^\w\s]", " ", s)
	s = re.sub(r"\s+", "_", s)
	s = re.sub(r"_+", "_", s).strip("_")
	return s or "unnamed"


def _categorical_labels(series: pd.Series, meaning_list: Any) -> pd.Series:
	"""Translate discrete numeric codes in a pandas Series into categorical labels based on the provided meaning list.
	
	Args:
		series (pd.Series): The pandas Series containing discrete numeric codes.
		meaning_list (Any): A list of dictionaries mapping 'code' to 'meaning'.

	Returns:
		pd.Series: A pandas Series with categorical labels applied where applicable.
	"""
	if not isinstance(meaning_list, list) or not meaning_list:
		return series
	labels = {}
	for entry in meaning_list:
		if not isinstance(entry, dict) or "code" not in entry or "meaning" not in entry:
			return series
		code = str(entry["code"]).strip()
		if code == ".":
			continue
		try:
			key = float(code)
		except ValueError:
			return series
		labels[key] = str(entry["meaning"])
	if not labels:
		return series
	translated = series.map(lambda value: labels.get(value, value) if pd.notna(value) else value)
	categories = list(dict.fromkeys(labels.values()))
	for value in translated.dropna().unique():
		if value not in categories:
			categories.append(value)
	return pd.Series(pd.Categorical(translated, categories=categories), index=series.index, name=series.name)


def read_nhanes_data(
	file_path: str,
	use_csv_for_labels: bool = True,
	local_doc_csv_dir: Optional[str] = None,
	allow_download_prompt: bool = True,
	attach_documentation: bool = True,
	add_documentation_column: bool = False,
	decode_categories: bool = False,
) -> pd.DataFrame:
	"""
	Read an NHANES XPT file and optionally rename columns using <dataset>_variables.csv.

	use_csv_for_labels: If True, attempts to find a corresponding <dataset>_variables.csv file
		and uses it to rename columns based on the 'label' field.
		These can be downloaded using the `download_nhanes_data` function with `with_docs=True`
	attach_documentation: If True, attach per-column documentation metadata under
		df.attrs['documentation'] and a docs table under df.attrs['documentation_df'].
	add_documentation_column: If True, add a 'documentation' column where each row
		contains the same per-column documentation dictionary.
	decode_categories: If True, translate discrete numeric codes into pandas categoricals.
		Continuous variables and unknown codes are preserved. Missing values aren't modified.
	"""
	file_path = resolve_local_file(file_path)
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
						file_path = resolve_local_file(file_path)
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

	if use_csv_for_labels or attach_documentation or decode_categories:
		base_name = os.path.splitext(os.path.basename(file_path))[0]
		doc_csv_name = f"{base_name}_variables.csv"

		search_dirs = [os.path.dirname(file_path)]
		if local_doc_csv_dir:
			search_dirs.insert(0, local_doc_csv_dir)

		doc_csv_path = None
		for d in search_dirs:
			candidate = resolve_local_file(os.path.join(d, doc_csv_name))
			if os.path.exists(candidate):
				doc_csv_path = candidate
				break

		if not doc_csv_path and allow_download_prompt:
			parts = file_path.split(os.sep)
			if len(parts) >= 4:
				component_candidate = parts[-2]
				cycle_candidate = parts[-4]
				if re.match(r"\d{4}-\d{4}", cycle_candidate):
					print(
						"Documentation CSV not found. "
						f"Try downloading docs for Component='{component_candidate}', Cycle='{cycle_candidate}'?"
					)
					response = input("Download docs now? [y/N] ").lower().strip()
					if response == "y":
						output_dir = os.sep.join(parts[:-4])
						if not output_dir:
							output_dir = "."
						try:
							download_nhanes_data(
								components=[component_candidate],
								output_dir=output_dir,
								years=[cycle_candidate],
								with_docs=True,
							)
						except Exception as e:
							logger.warning("Failed to download docs for %s: %s", file_path, e)

						for d in search_dirs:
							candidate = resolve_local_file(os.path.join(d, doc_csv_name))
							if os.path.exists(candidate):
								doc_csv_path = candidate
								break

		if not doc_csv_path:
			logger.warning(
				"Variables CSV not found for %s. Returning DataFrame with original column names.",
				base_name,
			)
			if attach_documentation:
				df.attrs["documentation"] = {}
				df.attrs["documentation_df"] = pd.DataFrame(
					columns=["variable_name", "label", "description", "value_meanings", "link"]
				)
				if add_documentation_column:
					df["documentation"] = [df.attrs["documentation"] for _ in range(len(df))]
			return df
		try:
			doc_df = pd.read_csv(doc_csv_path)
		except Exception as e:
			logger.warning(
				"Failed to read variables CSV for documentation %s: %s",
				doc_csv_path,
				e,
			)
			if attach_documentation:
				df.attrs["documentation"] = {}
				df.attrs["documentation_df"] = pd.DataFrame(
					columns=["variable_name", "label", "description", "value_meanings", "link"]
				)
				if add_documentation_column:
					df["documentation"] = [df.attrs["documentation"] for _ in range(len(df))]
			return df

		if "variable_name" not in doc_df.columns or "label" not in doc_df.columns:
			logger.warning(
				"Variables CSV for documentation %s missing 'variable_name' or 'label' columns.",
				doc_csv_path,
			)
			if attach_documentation:
				df.attrs["documentation"] = {}
				df.attrs["documentation_df"] = pd.DataFrame(
					columns=["variable_name", "label", "description", "value_meanings", "link"]
				)
				if add_documentation_column:
					df["documentation"] = [df.attrs["documentation"] for _ in range(len(df))]
			return df

		label_map = doc_df.dropna(subset=["variable_name", "label"]).set_index("variable_name")[
			"label"
		].to_dict()

		doc_records = {}
		for _, row in doc_df.iterrows():
			var = str(row.get("variable_name", "") or "").strip()
			if not var:
				continue

			raw_value_meanings = row.get("value_meanings", "")
			value_meanings: Any = None
			if isinstance(raw_value_meanings, str) and raw_value_meanings.strip():
				try:
					value_meanings = json.loads(raw_value_meanings)
				except Exception:
					value_meanings = raw_value_meanings.strip()

			doc_records[var] = {
				"variable_name": var,
				"label": None if pd.isna(row.get("label")) else str(row.get("label")),
				"description": None if pd.isna(row.get("description")) else str(row.get("description")),
				"value_meanings": value_meanings,
				"link": None if pd.isna(row.get("link")) else str(row.get("link")),
			}

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

		if decode_categories:
			for column in df.columns:
				df[column] = _categorical_labels(df[column], doc_records.get(column, {}).get("value_meanings"))

		if use_csv_for_labels:
			df = df.rename(columns=rename_map)

		if attach_documentation:
			documentation: Dict[str, Dict[str, Any]] = {}
			for original_col in rename_map:
				final_col = rename_map[original_col] if use_csv_for_labels else original_col
				rec = doc_records.get(original_col, {})
				documentation[final_col] = {
					"variable_name": original_col,
					"label": rec.get("label"),
					"description": rec.get("description"),
					"value_meanings": rec.get("value_meanings"),
					"link": rec.get("link"),
				}

			df.attrs["documentation"] = documentation
			df.attrs["documentation_df"] = pd.DataFrame(list(documentation.values()))

			if add_documentation_column:
				df["documentation"] = [documentation for _ in range(len(df))]
	return df


def get_column_doc(df: pd.DataFrame, column_name: str) -> Optional[Dict[str, Any]]:
	"""Return documentation metadata for a column from df.attrs['documentation']."""
	docs = df.attrs.get("documentation")
	if isinstance(docs, dict):
		entry = docs.get(column_name)
		if isinstance(entry, dict):
			return entry

	# Fallback to variable_name lookup in case docs are keyed differently.
	if isinstance(docs, dict):
		for _, entry in docs.items():
			if isinstance(entry, dict) and entry.get("variable_name") == column_name:
				return entry

	return None
