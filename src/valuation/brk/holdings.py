"""Berkshire 13F holdings parsing and normalization."""

from __future__ import annotations

from typing import Mapping, Optional
import xml.etree.ElementTree as ET

import pandas as pd

INFO_TABLE_NAMESPACE = {
    "n": "http://www.sec.gov/edgar/document/thirteenf/informationtable"
}


def parse_13f_infotable(xml_text: str) -> pd.DataFrame:
    """Parse SEC 13F information-table XML into a normalized holdings frame."""
    root = ET.fromstring(xml_text)
    rows = []
    for info_table in root.findall("n:infoTable", INFO_TABLE_NAMESPACE):
        shares = _find_text(
            info_table,
            "n:shrsOrPrnAmt/n:sshPrnamt",
            INFO_TABLE_NAMESPACE,
        )
        value_thousands = _find_text(info_table, "n:value", INFO_TABLE_NAMESPACE)
        sole = _find_text(info_table, "n:votingAuthority/n:Sole", INFO_TABLE_NAMESPACE)
        shared = _find_text(
            info_table,
            "n:votingAuthority/n:Shared",
            INFO_TABLE_NAMESPACE,
        )
        none = _find_text(info_table, "n:votingAuthority/n:None", INFO_TABLE_NAMESPACE)
        rows.append(
            {
                "issuer": _find_text(
                    info_table,
                    "n:nameOfIssuer",
                    INFO_TABLE_NAMESPACE,
                ),
                "class_title": _find_text(
                    info_table,
                    "n:titleOfClass",
                    INFO_TABLE_NAMESPACE,
                ),
                "cusip": _find_text(info_table, "n:cusip", INFO_TABLE_NAMESPACE),
                "value_thousands": _to_int(value_thousands),
                "shares_or_principal": _to_int(shares),
                "share_type": _find_text(
                    info_table,
                    "n:shrsOrPrnAmt/n:sshPrnamtType",
                    INFO_TABLE_NAMESPACE,
                ),
                "put_call": _find_text(info_table, "n:putCall", INFO_TABLE_NAMESPACE),
                "investment_discretion": _find_text(
                    info_table,
                    "n:investmentDiscretion",
                    INFO_TABLE_NAMESPACE,
                ),
                "other_manager": _find_text(
                    info_table,
                    "n:otherManager",
                    INFO_TABLE_NAMESPACE,
                ),
                "voting_sole": _to_int(sole),
                "voting_shared": _to_int(shared),
                "voting_none": _to_int(none),
            }
        )
    return normalize_13f_holdings(pd.DataFrame(rows))


def normalize_13f_holdings(frame: pd.DataFrame) -> pd.DataFrame:
    """Enforce stable 13F columns and sort by reported value descending."""
    expected_columns = [
        "issuer",
        "class_title",
        "cusip",
        "value_thousands",
        "value_usd",
        "shares_or_principal",
        "share_type",
        "put_call",
        "investment_discretion",
        "other_manager",
        "voting_sole",
        "voting_shared",
        "voting_none",
    ]
    if frame.empty:
        return pd.DataFrame(columns=expected_columns)

    normalized = frame.copy()
    if "value_thousands" not in normalized.columns and "value_usd" in normalized.columns:
        normalized["value_thousands"] = normalized["value_usd"].apply(
            lambda value: int(value / 1000) if value is not None else None
        )
    if "value_usd" not in normalized.columns and "value_thousands" in normalized.columns:
        normalized["value_usd"] = normalized["value_thousands"].apply(
            lambda value: value * 1000 if value is not None else None
        )
    for column in expected_columns:
        if column not in normalized.columns:
            normalized[column] = None

    normalized = normalized[expected_columns]
    normalized = normalized.sort_values(
        by=["value_usd", "issuer"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    return normalized


def aggregate_13f_holdings(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate repeated line items into issuer-level holdings rows."""
    normalized = normalize_13f_holdings(frame)
    if normalized.empty:
        return normalized

    group_columns = [
        "issuer",
        "class_title",
        "cusip",
        "share_type",
        "put_call",
    ]
    aggregated = (
        normalized.groupby(group_columns, dropna=False, as_index=False)
        .agg(
            {
                "value_thousands": "sum",
                "value_usd": "sum",
                "shares_or_principal": "sum",
                "voting_sole": "sum",
                "voting_shared": "sum",
                "voting_none": "sum",
                "investment_discretion": _merge_unique_text,
                "other_manager": _merge_unique_text,
            }
        )
        .sort_values(
            by=["value_usd", "issuer"],
            ascending=[False, True],
            na_position="last",
        )
        .reset_index(drop=True)
    )
    return aggregated


def _find_text(element: ET.Element, path: str, namespace: Mapping[str, str]) -> Optional[str]:
    child = element.find(path, namespace)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _merge_unique_text(series: pd.Series) -> Optional[str]:
    values = sorted({str(value) for value in series.dropna() if str(value).strip()})
    if not values:
        return None
    return "; ".join(values)
