from valuation.data.providers.sec import SecClient, SecCompany


def test_lookup_company_normalizes_dot_ticker(monkeypatch):
    client = SecClient()

    monkeypatch.setattr(
        client,
        "fetch_company_tickers",
        lambda: [
            SecCompany(
                ticker="BRK-B",
                cik="0001067983",
                name="BERKSHIRE HATHAWAY INC",
                exchange="NYSE",
            )
        ],
    )

    company = client.lookup_company("BRK.B")

    assert company.ticker == "BRK-B"


def test_fetch_company_tickers_uses_cache(monkeypatch):
    client = SecClient()
    calls = {"count": 0}

    def fake_get_json(url):
        calls["count"] += 1
        return {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"]],
        }

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    first = client.fetch_company_tickers()
    second = client.fetch_company_tickers()

    assert calls["count"] == 1
    assert first[0].ticker == second[0].ticker
