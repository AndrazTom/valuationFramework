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
