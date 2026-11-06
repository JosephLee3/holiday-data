from datetime import date
from pathlib import Path

import pytest

from scripts import fetch_jp

FIXTURE = Path(__file__).parent / "fixtures" / "jp_sample.csv"


@pytest.fixture(scope="module")
def all_days() -> dict[date, str]:
    return fetch_jp.parse_csv(FIXTURE.read_text(encoding="utf-8"))


def test_find_csv_url_resolves_relative_link(monkeypatch: pytest.MonkeyPatch) -> None:
    html = '<html><body><a href="syukujitsu.csv">CSV</a></body></html>'
    monkeypatch.setattr(fetch_jp, "http_get_text", lambda url: html)
    assert (
        fetch_jp.find_csv_url("https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html")
        == "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
    )


def test_parse_csv(all_days: dict[date, str]) -> None:
    assert len(all_days) == 372
    assert all_days[date(2026, 1, 1)] == "元日"
    assert all_days[date(2026, 5, 6)] == "休日"
    assert all_days[date(2019, 5, 1)] == "休日（祝日扱い）"


def test_year_counts(all_days: dict[date, str]) -> None:
    expected = {2007: 19, 2011: 15, 2019: 22, 2026: 18, 2027: 17}
    for year, count in expected.items():
        assert len(fetch_jp.build_year_days(year, all_days)) == count


def test_rest_day_classification(all_days: dict[date, str]) -> None:
    days_2026 = {item["date"]: item for item in fetch_jp.build_year_days(2026, all_days)}
    assert days_2026["2026-05-06"]["type"] == "substitute"
    assert days_2026["2026-09-22"]["type"] == "bridge"

    days_2027 = {item["date"]: item for item in fetch_jp.build_year_days(2027, all_days)}
    assert days_2027["2027-03-22"]["type"] == "substitute"


def test_every_rest_day_since_2007_is_classified(all_days: dict[date, str]) -> None:
    for year in range(2007, 2028):
        # build_year_days raises ValidationError for an unclassifiable 休日.
        fetch_jp.build_year_days(year, all_days)


def test_one_off_holiday_names(all_days: dict[date, str]) -> None:
    days_2019 = {item["date"]: item for item in fetch_jp.build_year_days(2019, all_days)}
    assert days_2019["2019-04-30"]["type"] == "bridge"
    assert days_2019["2019-05-01"]["name"] == "休日（祝日扱い）"
    assert days_2019["2019-05-02"]["type"] == "bridge"
    assert days_2019["2019-10-22"]["name"] == "休日（祝日扱い）"
