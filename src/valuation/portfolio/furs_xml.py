"""Generate FURS eDavki XML forms: Doh-KDVP, Doh-Div, Doh-Obr.

Flex Query configuration instructions adapted from the ib-edavki project
(https://github.com/ib-edavki/ib-edavki), which was the prior tool used for
Slovenian FURS tax reporting from IBKR data.
"""

from __future__ import annotations

import os
from datetime import date

from valuation.portfolio.ibkr import IbkrDividend
from valuation.portfolio.ibkr_flex import FlexInterest, FlexLot

_IBKR_IE_PAYER_ID = "657406"
_IBKR_IE_NAME = "Interactive Brokers Ireland Limited"
_IBKR_IE_ADDRESS = "10 Earlsfort Terrace, Dublin 2 D02 T380"
_IBKR_IE_COUNTRY = "IE"

KNOWN_PAYERS: dict[str, dict] = {
    "GOOGL": {
        "identification_number": "61-1767919",
        "name": "Alphabet Inc.",
        "address": "1600 Amphitheatre Parkway, Mountain View, CA 94043",
        "country": "US",
        "source_country": "US",
        "relief_statement": "10/01, 2b odstavek 10. člena",
    },
    "BNP": {
        "identification_number": "FR7666204244",
        "name": "BNP Paribas S.A.",
        "address": "16, boulevard des Italiens, 75009 Paris, France",
        "country": "FR",
        "source_country": "FR",
        "relief_statement": "4/05, 2a odstavek 10. člena",
    },
    "PAH3": {
        "identification_number": "-",
        "name": "Porsche Automobil Holding SE",
        "address": "Porscheplatz 1, 70435 Stuttgart, Germany",
        "country": "DE",
        "source_country": "DE",
        "relief_statement": "22/06, 2b odstavek 10. člena",
    },
    "PAH3d": {
        "identification_number": "-",
        "name": "Porsche Automobil Holding SE",
        "address": "Porscheplatz 1, 70435 Stuttgart, Germany",
        "country": "DE",
        "source_country": "DE",
        "relief_statement": "22/06, 2b odstavek 10. člena",
    },
    "DNQ": {
        "identification_number": "923609016",
        "name": "Equinor ASA",
        "address": "Forusbeen 50, 4035 Stavanger, Norway",
        "country": "NO",
        "source_country": "NO",
        "relief_statement": "7/09, 2c odstavek 10. člena",
    },
    "NESM": {
        "identification_number": "CHE116281710",
        "name": "Nestlé S.A. (Sponsored ADRs)",
        "address": "Avenue Nestlé 55, 1800 Vevey, Switzerland",
        "country": "CH",
        "source_country": "CH",
        "relief_statement": "15/97, 5/137, 2. odstavek 10. člena",
    },
    "BABA": {
        "identification_number": "5493001NTNQJ",
        "name": "Alibaba Group Holding Limited",
        "address": "One Capital Place, P.O. Box 847, George Town, Grand Cayman",
        "country": "KY",
        "source_country": "KY",
        "relief_statement": "",
    },
    "ASML": {
        "identification_number": "NL803441526B",
        "name": "ASML Holding N.V.",
        "address": "De Run 6501 5504 DR, Veldhoven, Noord-Brabant",
        "country": "NL",
        "source_country": "NL",
        "relief_statement": "4/05, 2b odstavek 10. člena",
    },
    "TSM": {
        "identification_number": "-",
        "name": "Taiwan Semiconductor Manufacturing Company Limited",
        "address": "Hsinchu Science Park No. 8, Li-Hsin Road 6 Hsinchu 300-78",
        "country": "TW",
        "source_country": "TW",
        "relief_statement": "",
    },
    "PYPL": {
        "identification_number": "47-2989869",
        "name": "Paypal Holdings, Inc.",
        "address": "2211 North First Street, San Jose, CA 95131",
        "country": "US",
        "source_country": "US",
        "relief_statement": "10/01, 2b odstavek 10. člena",
    },
}


def load_taxpayer_from_env() -> dict:
    """Load taxpayer personal details from FURS_* environment variables."""
    return {
        "tax_number": os.environ.get("FURS_TAX_NUMBER", ""),
        "name": os.environ.get("FURS_NAME", ""),
        "address": os.environ.get("FURS_ADDRESS", ""),
        "city": os.environ.get("FURS_CITY", ""),
        "post_number": os.environ.get("FURS_POST_NUMBER", ""),
        "post_name": os.environ.get("FURS_POST_NAME", ""),
        "email": os.environ.get("FURS_EMAIL", ""),
        "phone": os.environ.get("FURS_PHONE", ""),
    }


def lot_fx_pairs(lots: list[FlexLot]) -> list[tuple[str, date]]:
    """Collect (currency, date) pairs from FlexLots for ECB FX lookup.

    Includes both acquired dates (for F4 buy price) and sold dates (for F9 sell
    price) for all non-EUR lots.
    """
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, date]] = []
    for lot in lots:
        if lot.currency == "EUR":
            continue
        for d in (lot.acquired, lot.sold):
            key = (lot.currency, d.isoformat())
            if key not in seen:
                seen.add(key)
                result.append((lot.currency, d))
    return result


def build_kdvp_xml(
    lots: list[FlexLot],
    year: int,
    taxpayer: dict,
    fx_rates: dict | None = None,
) -> str:
    """Build Doh-KDVP XML for the given tax year.

    Groups lots by ISIN/symbol, emits per-security buy/sell rows with running
    F8 balance. F4 (buy) and F9 (sell) are per-share EUR prices with
    commissions included (F5=0), per FURS requirement.
    """
    year_lots = [l for l in lots if l.sold.year == year]

    by_security: dict[str, dict] = {}
    for lot in year_lots:
        key = lot.isin if lot.isin else lot.symbol
        if key not in by_security:
            by_security[key] = {
                "symbol": lot.symbol,
                "isin": lot.isin,
                "description": lot.description or lot.symbol,
                "lots": [],
            }
        by_security[key]["lots"].append(lot)

    out: list[str] = []
    out.append("<?xml version='1.0' encoding='utf-8'?>")
    out.append(
        '<Envelope xmlns="http://edavki.durs.si/Documents/Schemas/Doh_KDVP_9.xsd"'
        ' xmlns:edp="http://edavki.durs.si/Documents/Schemas/EDP-Common-1.xsd">'
    )
    _taxpayer_header(out, taxpayer, indent=1)
    out.append("\t<edp:AttachmentList />")
    out.append("\t<edp:Signatures />")
    out.append("\t<body>")
    out.append("\t\t<edp:bodyContent />")
    out.append("\t\t<Doh_KDVP>")
    out.append("\t\t\t<KDVP>")
    out.append("\t\t\t\t<DocumentWorkflowID>O</DocumentWorkflowID>")
    out.append(f"\t\t\t\t<Year>{year}</Year>")
    out.append(f"\t\t\t\t<PeriodStart>{year}-01-01</PeriodStart>")
    out.append(f"\t\t\t\t<PeriodEnd>{year}-12-31</PeriodEnd>")
    out.append("\t\t\t\t<IsResident>true</IsResident>")
    out.append(f"\t\t\t\t<TelephoneNumber>{taxpayer.get('phone', '')}</TelephoneNumber>")
    out.append(f"\t\t\t\t<SecurityCount>{len(by_security)}</SecurityCount>")
    out.append("\t\t\t\t<SecurityShortCount>0</SecurityShortCount>")
    out.append("\t\t\t\t<SecurityWithContractCount>0</SecurityWithContractCount>")
    out.append("\t\t\t\t<SecurityWithContractShortCount>0</SecurityWithContractShortCount>")
    out.append("\t\t\t\t<ShareCount>0</ShareCount>")
    out.append(f"\t\t\t\t<Email>{taxpayer.get('email', '')}</Email>")
    out.append("\t\t\t</KDVP>")

    for sec_data in by_security.values():
        _kdvp_item(out, sec_data, fx_rates)

    out.append("\t\t</Doh_KDVP>")
    out.append("\t</body>")
    out.append("</Envelope>")
    return "\n".join(out)


def build_div_xml(
    dividends: list[IbkrDividend],
    year: int,
    taxpayer: dict,
    fx_rates: dict,
) -> str:
    """Build Doh-Div XML for the given tax year.

    Payer details are looked up from KNOWN_PAYERS by IBKR symbol.
    Dividends without an FX rate are skipped with a warning.
    """
    year_divs = [d for d in dividends if d.payment_date.year == year]

    out: list[str] = []
    out.append("<?xml version='1.0' encoding='utf-8'?>")
    out.append(
        '<Envelope xmlns="http://edavki.durs.si/Documents/Schemas/Doh_Div_3.xsd"'
        ' xmlns:edp="http://edavki.durs.si/Documents/Schemas/EDP-Common-1.xsd">'
    )
    _taxpayer_header_with_workflow(out, taxpayer, indent=1)
    out.append("\t<edp:AttachmentList/>")
    out.append("\t<edp:Signatures/>")
    out.append("\t<body>")
    out.append("\t\t<Doh_Div>")
    out.append(f"\t\t\t<Period>{year}</Period>")
    out.append(f"\t\t\t<EmailAddress>{taxpayer.get('email', '')}</EmailAddress>")
    out.append(f"\t\t\t<PhoneNumber>{taxpayer.get('phone', '')}</PhoneNumber>")
    out.append("\t\t\t<ResidentCountry>SI</ResidentCountry>")
    out.append("\t\t\t<IsResident>true</IsResident>")
    out.append("\t\t</Doh_Div>")

    for div in year_divs:
        eur_rate = (
            1.0
            if div.currency == "EUR"
            else fx_rates.get((div.currency, div.payment_date.isoformat()))
        )
        if eur_rate is None:
            continue
        gross_eur = round(div.amount * eur_rate, 2)
        wht_eur = round(div.withholding_tax * eur_rate, 2)
        payer = KNOWN_PAYERS.get(div.symbol, {})
        source_country = payer.get("source_country") or div.issuer_country or ""

        out.append("\t\t<Dividend>")
        out.append(f"\t\t\t<Date>{div.payment_date.isoformat()}</Date>")
        out.append(
            f"\t\t\t<PayerIdentificationNumber>"
            f"{payer.get('identification_number', '')}"
            f"</PayerIdentificationNumber>"
        )
        out.append(f"\t\t\t<PayerName>{_xe(payer.get('name', div.symbol))}</PayerName>")
        out.append(f"\t\t\t<PayerAddress>{_xe(payer.get('address', ''))}</PayerAddress>")
        out.append(f"\t\t\t<PayerCountry>{payer.get('country', source_country)}</PayerCountry>")
        out.append("\t\t\t<Type>1</Type>")
        out.append(f"\t\t\t<Value>{gross_eur}</Value>")
        out.append(f"\t\t\t<ForeignTax>{wht_eur}</ForeignTax>")
        out.append(f"\t\t\t<SourceCountry>{source_country}</SourceCountry>")
        relief = _xe(payer.get("relief_statement", ""))
        if relief:
            out.append(f"\t\t\t<ReliefStatement>{relief}</ReliefStatement>")
        else:
            out.append("\t\t\t<ReliefStatement/>")
        out.append("\t\t</Dividend>")

    out.append("\t</body>")
    out.append("</Envelope>")
    return "\n".join(out)


def build_obr_xml(
    interest: list[FlexInterest],
    year: int,
    taxpayer: dict,
    fx_rates: dict,
) -> str:
    """Build Doh-Obr XML for the given tax year.

    Payer is always IBKR Ireland Limited (hardcoded). Interest without an FX
    rate is skipped.
    """
    year_interest = [r for r in interest if r.payment_date.year == year]

    out: list[str] = []
    out.append("<?xml version='1.0' encoding='utf-8'?>")
    out.append(
        '<Envelope xmlns="http://edavki.durs.si/Documents/Schemas/Doh_Obr_2.xsd"'
        ' xmlns:edp="http://edavki.durs.si/Documents/Schemas/EDP-Common-1.xsd">'
    )
    _taxpayer_header(out, taxpayer, indent=1)
    out.append("\t<edp:AttachmentList/>")
    out.append("\t<edp:Signatures/>")
    out.append("\t<body>")
    out.append("\t\t<edp:bodyContent/>")
    out.append("\t\t<Doh_Obr>")
    out.append(f"\t\t\t<Period>{year}</Period>")
    out.append("\t\t\t<DocumentWorkflowID>O</DocumentWorkflowID>")
    out.append(f"\t\t\t<Email>{taxpayer.get('email', '')}</Email>")
    out.append(f"\t\t\t<TelephoneNumber>{taxpayer.get('phone', '')}</TelephoneNumber>")
    out.append("\t\t\t<ResidentOfRepublicOfSlovenia>true</ResidentOfRepublicOfSlovenia>")
    out.append("\t\t\t<Country>SI</Country>")

    for row in year_interest:
        eur_rate = (
            1.0
            if row.currency == "EUR"
            else fx_rates.get((row.currency, row.payment_date.isoformat()))
        )
        if eur_rate is None:
            continue
        gross_eur = round(row.amount * eur_rate, 2)
        wht_eur = round(row.withholding_tax * eur_rate, 2)

        out.append("\t\t\t<Interest>")
        out.append(f"\t\t\t\t<Date>{row.payment_date.isoformat()}</Date>")
        out.append(f"\t\t\t\t<IdentificationNumber>{_IBKR_IE_PAYER_ID}</IdentificationNumber>")
        out.append(f"\t\t\t\t<Name>{_IBKR_IE_NAME}</Name>")
        out.append(f"\t\t\t\t<Address>{_IBKR_IE_ADDRESS}</Address>")
        out.append(f"\t\t\t\t<Country>{_IBKR_IE_COUNTRY}</Country>")
        out.append("\t\t\t\t<Type>2</Type>")
        out.append(f"\t\t\t\t<Value>{gross_eur}</Value>")
        out.append(f"\t\t\t\t<ForeignTax>{wht_eur}</ForeignTax>")
        out.append(f"\t\t\t\t<Country2>{_IBKR_IE_COUNTRY}</Country2>")
        out.append("\t\t\t</Interest>")

    out.append("\t\t</Doh_Obr>")
    out.append("\t</body>")
    out.append("</Envelope>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _kdvp_item(out: list[str], sec_data: dict, fx_rates: dict | None) -> None:
    lots = sec_data["lots"]
    desc = _xe(sec_data["description"])

    out.append("\t\t\t<KDVPItem>")
    out.append("\t\t\t\t<InventoryListType>PLVP</InventoryListType>")
    out.append(f"\t\t\t\t<Name>{desc}</Name>")
    out.append("\t\t\t\t<HasForeignTax>false</HasForeignTax>")
    out.append("\t\t\t\t<HasLossTransfer>false</HasLossTransfer>")
    out.append("\t\t\t\t<ForeignTransfer>false</ForeignTransfer>")
    out.append("\t\t\t\t<TaxDecreaseConformance>false</TaxDecreaseConformance>")
    out.append("\t\t\t\t<Securities>")
    out.append(f"\t\t\t\t\t<ISIN>{sec_data['isin']}</ISIN>")
    out.append(f"\t\t\t\t\t<Code>{sec_data['symbol']}</Code>")
    out.append(f"\t\t\t\t\t<Name>{desc}</Name>")
    out.append("\t\t\t\t\t<IsFond>false</IsFond>")

    buy_events: dict[date, list[FlexLot]] = {}
    sell_events: dict[date, list[FlexLot]] = {}
    for lot in lots:
        buy_events.setdefault(lot.acquired, []).append(lot)
        sell_events.setdefault(lot.sold, []).append(lot)

    # Chronological: buy before sell on same date
    all_events = sorted(
        [(d, "buy") for d in buy_events] + [(d, "sell") for d in sell_events],
        key=lambda x: (x[0], 0 if x[1] == "buy" else 1),
    )

    running_balance = 0.0
    row_id = 0
    for event_date, event_type in all_events:
        out.append("\t\t\t\t\t<Row>")
        out.append(f"\t\t\t\t\t\t<ID>{row_id}</ID>")

        if event_type == "buy":
            ev_lots = buy_events[event_date]
            total_qty = sum(l.quantity for l in ev_lots)
            total_cost = sum(abs(l.cost_native) for l in ev_lots)
            f4 = _eur_per_share(total_cost, total_qty, ev_lots[0].currency, event_date, fx_rates)
            running_balance += total_qty
            out.append("\t\t\t\t\t\t<Purchase>")
            out.append(f"\t\t\t\t\t\t\t<F1>{event_date.isoformat()}</F1>")
            out.append("\t\t\t\t\t\t\t<F2>B</F2>")
            out.append(f"\t\t\t\t\t\t\t<F3>{total_qty:.4f}</F3>")
            out.append(f"\t\t\t\t\t\t\t<F4>{_fmtp(f4)}</F4>")
            out.append("\t\t\t\t\t\t\t<F5>0</F5>")
            out.append("\t\t\t\t\t\t</Purchase>")
        else:
            ev_lots = sell_events[event_date]
            total_qty = sum(l.quantity for l in ev_lots)
            total_proceeds = sum(abs(l.proceeds_native) for l in ev_lots)
            f9 = _eur_per_share(total_proceeds, total_qty, ev_lots[0].currency, event_date, fx_rates)
            running_balance -= total_qty
            out.append("\t\t\t\t\t\t<Sale>")
            out.append(f"\t\t\t\t\t\t\t<F6>{event_date.isoformat()}</F6>")
            out.append(f"\t\t\t\t\t\t\t<F7>{total_qty:.4f}</F7>")
            out.append(f"\t\t\t\t\t\t\t<F9>{_fmtp(f9)}</F9>")
            out.append("\t\t\t\t\t\t</Sale>")

        out.append(f"\t\t\t\t\t\t<F8>{running_balance:.4f}</F8>")
        out.append("\t\t\t\t\t</Row>")
        row_id += 1

    out.append("\t\t\t\t</Securities>")
    out.append("\t\t\t</KDVPItem>")


def _taxpayer_header(out: list[str], taxpayer: dict, indent: int) -> None:
    t = "\t" * indent
    out.append(f"{t}<edp:Header>")
    out.append(f"{t}\t<edp:taxpayer>")
    out.append(f"{t}\t\t<edp:taxNumber>{taxpayer.get('tax_number', '')}</edp:taxNumber>")
    out.append(f"{t}\t\t<edp:taxpayerType>FO</edp:taxpayerType>")
    out.append(f"{t}\t\t<edp:name>{_xe(taxpayer.get('name', ''))}</edp:name>")
    out.append(f"{t}\t\t<edp:address1>{_xe(taxpayer.get('address', ''))}</edp:address1>")
    out.append(f"{t}\t\t<edp:city>{_xe(taxpayer.get('city', ''))}</edp:city>")
    out.append(f"{t}\t\t<edp:postNumber>{taxpayer.get('post_number', '')}</edp:postNumber>")
    out.append(f"{t}\t\t<edp:postName>{_xe(taxpayer.get('post_name', ''))}</edp:postName>")
    out.append(f"{t}\t</edp:taxpayer>")
    out.append(f"{t}</edp:Header>")


def _taxpayer_header_with_workflow(out: list[str], taxpayer: dict, indent: int) -> None:
    t = "\t" * indent
    out.append(f"{t}<edp:Header>")
    out.append(f"{t}\t<edp:taxpayer>")
    out.append(f"{t}\t\t<edp:taxNumber>{taxpayer.get('tax_number', '')}</edp:taxNumber>")
    out.append(f"{t}\t\t<edp:taxpayerType>FO</edp:taxpayerType>")
    out.append(f"{t}\t\t<edp:name>{_xe(taxpayer.get('name', ''))}</edp:name>")
    out.append(f"{t}\t\t<edp:address1>{_xe(taxpayer.get('address', ''))}</edp:address1>")
    out.append(f"{t}\t\t<edp:city>{_xe(taxpayer.get('city', ''))}</edp:city>")
    out.append(f"{t}\t\t<edp:postNumber>{taxpayer.get('post_number', '')}</edp:postNumber>")
    out.append(f"{t}\t\t<edp:postName>{_xe(taxpayer.get('post_name', ''))}</edp:postName>")
    out.append(f"{t}\t</edp:taxpayer>")
    out.append(f"{t}\t<edp:Workflow>")
    out.append(f"{t}\t\t<edp:DocumentWorkflowID>O</edp:DocumentWorkflowID>")
    out.append(f"{t}\t</edp:Workflow>")
    out.append(f"{t}</edp:Header>")


def _eur_per_share(
    total_native: float,
    qty: float,
    currency: str,
    on: date,
    fx_rates: dict | None,
) -> float | None:
    per_share = total_native / qty if qty > 0 else 0.0
    if currency == "EUR":
        return per_share
    if not fx_rates:
        return None
    rate = fx_rates.get((currency, on.isoformat()))
    return per_share * rate if rate is not None else None


def _fmtp(v: float | None) -> str:
    return f"{v:.4f}" if v is not None else "0.0000"


def _xe(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
