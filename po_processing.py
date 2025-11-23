#!/usr/bin/env python3
# po_processing.py

import tempfile
import os
import re
import pandas as pd
import pdfplumber


# ---------- Helpers for PDF ----------

def _make_unique_headers(headers):
    """Make header names unique and non-empty."""
    headers = [str(h).strip() if h else "" for h in headers]
    seen = {}
    new = []
    for h in headers:
        if h == "":
            h = "Extra"
        if h in seen:
            seen[h] += 1
            new.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 1
            new.append(h)
    return new


def _read_pdf_to_df(uploaded_file) -> pd.DataFrame:
    """Read a PDF upload into a single DataFrame of tables."""
    # Save to a temp path for pdfplumber
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    all_tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for t in tables:
                if not t:
                    continue
                df = pd.DataFrame(t)

                # header row = first non-empty row
                header_row = None
                for i, row in df.iterrows():
                    if any(str(x).strip() for x in row):
                        header_row = i
                        break
                if header_row is None:
                    continue

                headers = _make_unique_headers(df.iloc[header_row].tolist())
                df = df.iloc[header_row + 1 :].reset_index(drop=True)
                df.columns = headers
                all_tables.append(df)

    if not all_tables:
        return pd.DataFrame()

    df = pd.concat(all_tables, ignore_index=True)

    # normalise core column names so later code can rely on them
    rename = {}
    for col in df.columns:
        c = col.strip().lower()
        if "sku" in c:
            rename[col] = "Sku"
        elif "product" in c:
            rename[col] = "Product"
        elif "cost" in c:
            rename[col] = "Cost_Price"
        elif "barcode" in c:
            rename[col] = "Barcode"
        elif "location" in c:
            rename[col] = "Location"
        elif "outstanding" in c:
            rename[col] = "Outstanding"
        elif "receiving" in c:
            rename[col] = "Receiving"

    df = df.rename(columns=rename)
    return df


# ---------- Generic file reader ----------

def read_po_file(uploaded_file) -> pd.DataFrame:
    """
    Read an uploaded PO file (CSV / XLSX / PDF) and return a raw DataFrame.
    """
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)

    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(uploaded_file)

    if name.endswith(".pdf"):
        return _read_pdf_to_df(uploaded_file)

    raise ValueError(f"Unsupported file type: {name}")


# ---------- Parsing + cleaning ----------

def _split_flavour_strength(inside: str):
    """
    Take the text inside brackets like 'Blue Razz / 20mg'
    and split into flavour + strength. Strength is any token
    containing e.g. 'mg'. Everything else is flavour.
    """
    tokens = [t.strip() for t in re.split(r"[/\-\|;]", inside) if t.strip()]
    flavour_tokens = []
    strength = ""

    for tok in tokens:
        low = tok.lower()
        if re.search(r"\b\d+\s*mg\b", low):
            strength = tok
        else:
            flavour_tokens.append(tok)

    flavour = " ".join(flavour_tokens).strip()
    return flavour, strength


def _extract_product_flavour_strength(p: str):
    """
    Smarter extraction:

    1) Normalise whitespace.
    2) If [ ... ] exists anywhere, use that for flavour/strength.
    3) If no brackets, try to detect strength like '20mg' and
       treat trailing part of the name as flavour (after 'Pods', comma or dash).
    """
    p = str(p or "")
    # collapse all whitespace (including newlines) to single spaces
    p = re.sub(r"\s+", " ", p).strip()

    if not p:
        return "", "", ""

    # --- Case 1: brackets exist somewhere in the string ---
    m = re.search(r"\[(.+?)\]", p)
    if m:
        inside = m.group(1).strip()
        # remove the whole bracketed bit from the product text
        p_clean = (p[:m.start()] + p[m.end():]).strip()

        flavour, strength = _split_flavour_strength(inside)
        return p_clean, flavour, strength

    # --- Case 2: no brackets, try to detect strength like '20mg' ---
    strength = ""
    p_wo_strength = p

    m2 = re.search(r"(\d+\s*mg)\b", p, flags=re.IGNORECASE)
    if m2:
        strength = m2.group(1).strip()
        p_wo_strength = (p[:m2.start()] + p[m2.end():]).strip()

    # Try to guess flavour from what's left:
    #  - text after 'Pods' (common in your data)
    #  - else text after last comma / dash
    flavour = ""
    p_clean = p_wo_strength

    m3 = re.search(r"pods\s+(.+)$", p_wo_strength, flags=re.IGNORECASE)
    if m3:
        flavour = m3.group(1).strip()
        p_clean = p_wo_strength[:m3.start()].strip()
    else:
        m4 = re.search(r"[,|-]\s*([^,|-]+)$", p_wo_strength)
        if m4:
            flavour = m4.group(1).strip()
            p_clean = p_wo_strength[:m4.start()].strip()

    return p_clean, flavour, strength


def parse_product_flavour_strength(df: pd.DataFrame) -> pd.DataFrame:
    """
    From Product text, derive clean Product, Flavour and Strength.
    Works with:
      - '... [Blueberry Ice / 20mg]'
      - '... Pods Blueberry Ice 20mg'
      - multi-line / messy whitespace.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    for c in ["Product", "Flavour", "Strength"]:
        if c not in df.columns:
            df[c] = ""

    parsed = df.apply(
        lambda row: _extract_product_flavour_strength(row.get("Product", "")),
        axis=1,
        result_type="expand",
    )
    parsed.columns = ["_prod_clean", "_flavour_ex", "_strength_ex"]

    df["_prod_clean"] = parsed["_prod_clean"]
    df["_flavour_ex"] = parsed["_flavour_ex"]
    df["_strength_ex"] = parsed["_strength_ex"]

    df["Product"] = df["_prod_clean"].where(
        df["_prod_clean"].notna() & (df["_prod_clean"] != ""),
        df["Product"],
    )
    df["Flavour"] = df["_flavour_ex"].where(
        df["_flavour_ex"].notna() & (df["_flavour_ex"] != ""),
        df["Flavour"],
    )
    df["Strength"] = df["_strength_ex"].where(
        df["_strength_ex"].notna() & (df["_strength_ex"] != ""),
        df["Strength"],
    )

    df = df.drop(columns=["_prod_clean", "_flavour_ex", "_strength_ex"])
    return df


def clean_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop fully empty rows and rows without both Sku and Product.
    """
    df = df.replace(r"^\s*$", pd.NA, regex=True)
    df = df.dropna(how="all")
    if "Product" in df.columns and "Sku" in df.columns:
        df = df[df["Product"].notna() | df["Sku"].notna()]
    return df.reset_index(drop=True)


def build_po_table(uploaded_file) -> pd.DataFrame:
    """
    High-level helper:
      uploaded file -> raw df -> parsed -> cleaned -> standardised table
    """
    df = read_po_file(uploaded_file)
    if df is None or df.empty:
        return pd.DataFrame()

    df = parse_product_flavour_strength(df)
    df = clean_rows(df)

    # ensure required columns
    for c in ["Sku", "Product", "Flavour", "Strength", "Outstanding", "Case_Size"]:
        if c not in df.columns:
            df[c] = ""

    # keep only columns we care about for label workflow
    df = df[["Sku", "Product", "Flavour", "Strength", "Outstanding", "Case_Size"]]

    # numeric conversions
    df["Outstanding"] = (
        df["Outstanding"]
        .astype(str)
        .str.replace(",", "", regex=False)
    )
    df["Outstanding"] = pd.to_numeric(df["Outstanding"], errors="coerce").fillna(0)
    df["Case_Size"] = pd.to_numeric(df["Case_Size"], errors="coerce")

    return df