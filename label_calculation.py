#!/usr/bin/env python3
# label_calculation.py

import math
import pandas as pd


def apply_default_case_size(df: pd.DataFrame, default_case_size: int) -> pd.DataFrame:
    """
    If Case_Size is missing or NaN, fill with a default value.
    """
    df = df.copy()
    if "Case_Size" not in df.columns:
        df["Case_Size"] = pd.NA
    df["Case_Size"] = pd.to_numeric(df["Case_Size"], errors="coerce")
    if default_case_size and default_case_size > 0:
        df["Case_Size"] = df["Case_Size"].fillna(default_case_size)
    return df


def compute_final_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Final_Labels = ceil(Outstanding / Case_Size) when both > 0, else 0.
    """
    df = df.copy()
    df["Outstanding"] = pd.to_numeric(df.get("Outstanding", 0), errors="coerce").fillna(0)
    df["Case_Size"] = pd.to_numeric(df.get("Case_Size", None), errors="coerce")

    def calc(row):
        out = row.get("Outstanding", 0)
        cs = row.get("Case_Size", None)
        if pd.notna(cs) and cs > 0 and out > 0:
            return int(math.ceil(out / cs))
        return 0

    df["Final_Labels"] = df.apply(calc, axis=1)
    return df