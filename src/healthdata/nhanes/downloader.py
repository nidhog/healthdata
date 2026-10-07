import csv
import logging
import os
import re
import json
from typing import List, Optional, Union
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from .settings import DEFAULT_BASE_DOMAIN, DEFAULT_BASE_SEARCH_URL, DEFAULT_COMPONENTS

logger = logging.getLogger(__name__)


def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)


def extract_date_from_url(url: str) -> str:
    """
    Extract NHANES cycle or year from url patterns.
    The patterns we look for are either "YYYY-YYYY" or "/YYYY/".
    Returns 'nodate' if none found.
    """
    match = re.search(r"\d{4}-\d{4}", url)
    if match:
        return match.group(0)
    match = re.search(r"/(19|20)\d{2}/", url)
    if match:
        return match.group(0).strip("/")
    return "nodate"


def download_file(url: str, out_path: str):
    """Download an XPT file"""
    r = requests.get(url, stream=True)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))

    with open(out_path, "wb") as f, tqdm(
        desc=os.path.basename(out_path),
        total=total if total > 0 else None,
        unit="B",
        unit_scale=True,
    ) as bar:
        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                continue
            f.write(chunk)
            if total > 0:
                bar.update(len(chunk))


def parse_nhanes_doc_variables(doc_html: str, doc_url: str):
    """
    Parse NHANES doc HTML into: variable_name, label, description, value_meanings, link.

    This extracts metadata that is not available in the XPT files.

    TODO: add patterns as config instead?
    """
    soup = BeautifulSoup(doc_html, "html.parser")
    value_tables = {}
    for table in soup.find_all("table"):
        headers = [cell.get_text(" ", strip=True).lower() for cell in table.select("tr th")]
        if "code or value" not in headers or "value description" not in headers:
            continue
        preceding = table.find_previous(string=re.compile(r"Variable Name:"))
        if preceding is None:
            continue
        variable_text = preceding.parent.get_text(" ", strip=True)
        if not re.search(r"Variable Name:\s*[A-Za-z0-9_]+", variable_text):
            variable_text += " " + preceding.parent.find_next().get_text(" ", strip=True)
        variable_match = re.search(r"Variable Name:\s*([A-Za-z0-9_]+)", variable_text)
        if not variable_match:
            continue
        meanings = []
        for table_row in table.select("tr"):
            cells = table_row.find_all("td", recursive=False)
            if len(cells) < len(headers):
                continue
            meanings.append({
                "code": cells[headers.index("code or value")].get_text(" ", strip=True),
                "meaning": cells[headers.index("value description")].get_text(" ", strip=True),
            })
        value_tables[variable_match.group(1)] = meanings
        table.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\r", "", text)
    text = re.sub(r"[ \t]+", " ", text)

    rows = []
    chunks = re.split(r"(?=\bVariable Name:\s*[A-Za-z0-9_]+)", text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("Variable Name:"):
            continue

        var_match = re.search(r"Variable Name:\s*(?P<var>[A-Za-z0-9_]+)", chunk)
        if not var_match:
            continue
        var = var_match.group("var").strip()

        label_match = re.search(
            r"SAS Label:\s*(?P<label>.*?)(?=\n\s*English Text:|\n\s*English Instructions:|\n\s*Target:|\n\s*Code or Value|\Z)",
            chunk,
            re.DOTALL,
        )
        desc_match = re.search(
            r"English Text:\s*(?P<desc>.*?)(?=\n\s*English Instructions:|\n\s*Target:|\n\s*Code or Value|\Z)",
            chunk,
            re.DOTALL,
        )

        label = re.sub(r"\s+", " ", label_match.group("label")).strip() if label_match else ""
        desc = re.sub(r"\s+", " ", desc_match.group("desc")).strip() if desc_match else ""

        value_meanings = value_tables.get(var, [])
        value_section = re.search(
            r"Code or Value\s*(?P<section>.*?)(?=\n\s*Variable Name:|\Z)",
            chunk,
            re.DOTALL,
        )
        if value_section:
            section_text = value_section.group("section")
            # Common NHANES rows are represented as: code whitespace value-description.
            for line in [ln.strip() for ln in section_text.splitlines() if ln.strip()]:
                if line.lower() in {
                    "value description",
                    "unweighted count",
                    "weighted percent",
                    "weighted frequency",
                    "cumulative",
                    "skip to item",
                }:
                    continue
                m = re.match(r"^(?P<code>[-+A-Za-z0-9\.]+)\s{1,}(?P<meaning>.+)$", line)
                if not m:
                    continue
                value_meanings.append(
                    {
                        "code": m.group("code").strip(),
                        "meaning": re.sub(r"\s+", " ", m.group("meaning")).strip(),
                    }
                )

        rows.append(
            {
                "variable_name": var,
                "label": label,
                "description": desc,
                "value_meanings": json.dumps(value_meanings, ensure_ascii=False) if value_meanings else "",
                "link": doc_url,
            }
        )
    return rows


def download_and_extract_docs(doc_url: str, out_dir: str):
    """Save one CDC codebook as a variables CSV; does not download XPT data.

    Use download_nhanes_data for the usual data-and-documentation download.
    """
    r = requests.get(doc_url)
    r.raise_for_status()
    rows = parse_nhanes_doc_variables(r.text, doc_url)

    doc_base = os.path.basename(urlparse(doc_url).path)
    csv_name = os.path.splitext(doc_base)[0] + "_variables.csv"
    out_csv = os.path.join(out_dir, csv_name)

    
    ensure_dir(os.path.dirname(out_csv))
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["variable_name", "label", "description", "value_meanings", "link"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"> [SAVED] Docs CSV saved: {out_csv}")


def get_file_links_for_component(
    component: str,
    years: Optional[List[Union[int, str]]] = None,
    base_search_url: str = DEFAULT_BASE_SEARCH_URL,
    base_domain: str = DEFAULT_BASE_DOMAIN,
):
    """Return dataset links for an NHANES component, filtered by years if provided.
        This is where most of the logic for parsing the website is defined.
        TODO: perhaps this can be provided as a function to the downloader
        in case the website changes its structure in the future?
    """
    params = {"Component": component}
    print(f"> [FETCH] Fetching data page for Component = {component} ...")
    resp = requests.get(base_search_url, params=params)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tr")
    out = []

    years_set = set()
    if years:
        for y in years:
            years_set.add(str(y))

    for tr_field in rows:
        td_fields = tr_field.find_all("td")
        if not td_fields:
            continue

        cycle_str = td_fields[0].get_text(strip=True) if len(td_fields) >= 1 else "unknown"

        if years:
            cycle_parts = re.findall(r"\d{4}", cycle_str)
            is_match = False
            for part in cycle_parts:
                if part in years_set:
                    is_match = True
                    break
            if cycle_str in years_set:
                is_match = True

            if not is_match:
                continue

        doc_url = None
        xpt_url = None
        data_file_name = None

        for a in tr_field.select("a[href]"):
            href = a.get("href", "").strip()
            if not href:
                continue

            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = base_domain + href
            else:
                full_url = base_domain + "/" + href.lstrip("/")

            if href.lower().endswith(".htm"):
                doc_url = full_url
            elif href.lower().endswith(".xpt"):
                xpt_url = full_url
                data_file_name = a.get_text(strip=True) or None

        if xpt_url and doc_url:
            out.append(
                {
                    "years": cycle_str,
                    "xpt_url": xpt_url,
                    "doc_url": doc_url,
                    "data_file_name": data_file_name,
                }
            )

    return out


def download_nhanes_data(
    output_dir: str,
    components: Optional[List[str]] = DEFAULT_COMPONENTS,
    years: Optional[List[Union[int, str]]] = None,
    with_docs: bool = True,
    base_search_url: str = DEFAULT_BASE_SEARCH_URL,
    base_domain: str = DEFAULT_BASE_DOMAIN,
):
    """Download NHANES XPT files and their codebooks for components and years.

    Documentation is included by default. Set with_docs=False for data only.
    """
    ensure_dir(output_dir)

    for comp in components:
        entries = get_file_links_for_component(
            comp,
            years=years,
            base_search_url=base_search_url,
            base_domain=base_domain,
        )
        print(f"> [FOUND] Found {len(entries)} datasets for component '{comp}' (matching years: {years})")

        for e in entries:
            xpt_url = e["xpt_url"]
            doc_url = e["doc_url"]
            cycle = e["years"] or "unknown"

            date = extract_date_from_url(doc_url)

            out_subdir = os.path.join(output_dir, cycle, date, comp)
            ensure_dir(out_subdir)

            filename = xpt_url.split("/")[-1]
            out_path = os.path.join(out_subdir, filename)

            if os.path.exists(out_path):
                print(f"> [CHECK] Already downloaded: {cycle}/{filename}")
            else:
                print(f"> [.....] Downloading {cycle}/{filename}")
                download_file(xpt_url, out_path)

            if with_docs:
                try:
                    download_and_extract_docs(doc_url, out_subdir)
                except Exception as err:
                    logger.warning("Failed to extract docs for %s (%s)", doc_url, err)
