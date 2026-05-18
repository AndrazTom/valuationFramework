import pandas as pd

from valuation.brk.holdings import (
    aggregate_13f_holdings,
    normalize_13f_holdings,
    parse_13f_infotable,
)


def test_parse_13f_infotable_returns_sorted_holdings():
    xml_text = """
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable>
        <nameOfIssuer>APPLE INC</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>037833100</cusip>
        <value>100</value>
        <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
        <investmentDiscretion>SOLE</investmentDiscretion>
        <votingAuthority><Sole>10</Sole><Shared>0</Shared><None>0</None></votingAuthority>
      </infoTable>
      <infoTable>
        <nameOfIssuer>AMERICAN EXPRESS CO</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>025816109</cusip>
        <value>250</value>
        <shrsOrPrnAmt><sshPrnamt>20</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
        <investmentDiscretion>SOLE</investmentDiscretion>
        <votingAuthority><Sole>20</Sole><Shared>0</Shared><None>0</None></votingAuthority>
      </infoTable>
    </informationTable>
    """

    frame = parse_13f_infotable(xml_text)

    assert list(frame["issuer"]) == ["AMERICAN EXPRESS CO", "APPLE INC"]
    assert frame.iloc[0]["value_usd"] == 250
    assert frame.iloc[0]["value_thousands"] == 0
    assert frame.iloc[0]["security_id"] == "cusip:025816109"


def test_normalize_13f_holdings_adds_value_usd():
    frame = pd.DataFrame(
        [
            {"issuer": "A", "value_thousands": 10},
            {"issuer": "B", "value_thousands": 20},
        ]
    )

    normalized = normalize_13f_holdings(frame)

    assert list(normalized["issuer"]) == ["B", "A"]
    assert normalized.iloc[0]["value_usd"] == 20000


def test_aggregate_13f_holdings_combines_duplicate_issuers():
    frame = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_thousands": 100,
                "shares_or_principal": 10,
                "share_type": "SH",
                "put_call": None,
                "investment_discretion": "DFND",
                "other_manager": "4",
                "voting_sole": 10,
                "voting_shared": 0,
                "voting_none": 0,
            },
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_thousands": 250,
                "shares_or_principal": 20,
                "share_type": "SH",
                "put_call": None,
                "investment_discretion": "DFND",
                "other_manager": "8",
                "voting_sole": 20,
                "voting_shared": 0,
                "voting_none": 0,
            },
        ]
    )

    aggregated = aggregate_13f_holdings(frame)

    assert aggregated.shape[0] == 1
    assert aggregated.iloc[0]["value_usd"] == 350000
    assert aggregated.iloc[0]["shares_or_principal"] == 30


def test_aggregate_13f_holdings_empty_input():
    result = aggregate_13f_holdings(pd.DataFrame())
    assert result.empty


def test_aggregate_13f_holdings_distinct_issuers_stay_separate():
    frame = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_thousands": 500,
                "shares_or_principal": 50,
                "share_type": "SH",
                "put_call": None,
                "investment_discretion": "DFND",
                "other_manager": None,
                "voting_sole": 50,
                "voting_shared": 0,
                "voting_none": 0,
            },
            {
                "security_id": "cusip:594918104",
                "issuer": "MICROSOFT CORP",
                "class_title": "COM",
                "cusip": "594918104",
                "value_thousands": 200,
                "shares_or_principal": 10,
                "share_type": "SH",
                "put_call": None,
                "investment_discretion": "DFND",
                "other_manager": None,
                "voting_sole": 10,
                "voting_shared": 0,
                "voting_none": 0,
            },
        ]
    )

    aggregated = aggregate_13f_holdings(frame)

    assert aggregated.shape[0] == 2
    # sorted by value_usd descending
    assert aggregated.iloc[0]["issuer"] == "APPLE INC"
    assert aggregated.iloc[1]["issuer"] == "MICROSOFT CORP"


def test_aggregate_13f_holdings_merges_investment_discretion_text():
    frame = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_thousands": 100,
                "shares_or_principal": 10,
                "share_type": "SH",
                "put_call": None,
                "investment_discretion": "DFND",
                "other_manager": "4",
                "voting_sole": 10,
                "voting_shared": 0,
                "voting_none": 0,
            },
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_thousands": 150,
                "shares_or_principal": 15,
                "share_type": "SH",
                "put_call": None,
                "investment_discretion": "SOLE",
                "other_manager": "8",
                "voting_sole": 15,
                "voting_shared": 0,
                "voting_none": 0,
            },
        ]
    )

    aggregated = aggregate_13f_holdings(frame)

    assert aggregated.shape[0] == 1
    row = aggregated.iloc[0]
    assert row["shares_or_principal"] == 25
    assert row["value_usd"] == 250000
    # both discretion values are merged
    assert "DFND" in str(row["investment_discretion"])
    assert "SOLE" in str(row["investment_discretion"])
    assert "4" in str(row["other_manager"])
    assert "8" in str(row["other_manager"])
