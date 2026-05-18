from valuation.data.providers.sec import SecClient, SecCompany


def test_fetch_submissions_uses_persistent_cache(tmp_path):
    client = SecClient(cache_root=tmp_path)
    calls = {"count": 0}

    def fake_fetch_json(url):
        calls["count"] += 1
        return {"filings": {"recent": {"form": ["10-K"]}}}

    client._fetch_json_uncached = fake_fetch_json

    first = client.fetch_submissions("1067983")
    second = client.fetch_submissions("1067983")

    assert first == second
    assert calls["count"] == 1


def test_fetch_submissions_refresh_cache_bypasses_cached_payload(tmp_path):
    first = SecClient(cache_root=tmp_path)
    first._fetch_json_uncached = lambda url: {"version": 1}
    assert first.fetch_submissions("1067983") == {"version": 1}

    refreshed = SecClient(cache_root=tmp_path, refresh_cache=True)
    refreshed._fetch_json_uncached = lambda url: {"version": 2}

    assert refreshed.fetch_submissions("1067983") == {"version": 2}


def test_fetch_submissions_refresh_cache_env_bypasses_cached_payload(tmp_path, monkeypatch):
    first = SecClient(cache_root=tmp_path)
    first._fetch_json_uncached = lambda url: {"version": 1}
    assert first.fetch_submissions("1067983") == {"version": 1}

    monkeypatch.setenv("VALUATION_REFRESH_CACHE", "1")
    refreshed = SecClient(cache_root=tmp_path)
    refreshed._fetch_json_uncached = lambda url: {"version": 2}

    assert refreshed.fetch_submissions("1067983") == {"version": 2}


def test_fetch_submissions_ignores_expired_cache(tmp_path, monkeypatch):
    client = SecClient(cache_root=tmp_path)
    monkeypatch.setattr("valuation.data.providers.sec.SEC_SUBMISSIONS_TTL_SECONDS", 0)
    calls = {"count": 0}

    def fake_fetch_json(url):
        calls["count"] += 1
        return {"version": calls["count"]}

    client._fetch_json_uncached = fake_fetch_json

    assert client.fetch_submissions("1067983") == {"version": 1}
    assert client.fetch_submissions("1067983") == {"version": 2}


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
    client = SecClient(use_cache=False)
    calls = {"count": 0}

    def fake_fetch_json(url):
        calls["count"] += 1
        return {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"]],
        }

    monkeypatch.setattr(client, "_fetch_json_uncached", fake_fetch_json)

    first = client.fetch_company_tickers()
    second = client.fetch_company_tickers()

    assert calls["count"] == 1
    assert first[0].ticker == second[0].ticker


def test_lookup_company_by_cik(monkeypatch):
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

    company = client.lookup_company_by_cik("1067983")

    assert company.ticker == "BRK-B"


def test_fetch_report_table_parses_sec_html_without_lxml(monkeypatch):
    client = SecClient()
    html = """
    <html>
      <body>
        <table class="report">
          <tr>
            <th colspan="2" rowspan="2">Business segment data</th>
            <th colspan="2">3 Months Ended</th>
          </tr>
          <tr>
            <th>Sep. 30, 2025</th>
            <th>Sep. 30, 2024</th>
          </tr>
          <tr>
            <td>BNSF [Member]</td>
            <td></td>
            <td></td>
            <td></td>
          </tr>
          <tr>
            <td>Revenues</td>
            <td></td>
            <td>23,441</td>
            <td>23,490</td>
          </tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(client, "fetch_filing_text", lambda cik, accession_number, filename: html)

    frame = client.fetch_report_table("0001067983", "0001", "R1.htm")

    assert list(frame.columns) == [
        "Business segment data",
        "Business segment data",
        "3 Months Ended Sep. 30, 2025",
        "3 Months Ended Sep. 30, 2024",
    ]
    assert frame.iloc[0, 0] == "BNSF [Member]"
    assert frame.iloc[1, 2] == "23,441"
