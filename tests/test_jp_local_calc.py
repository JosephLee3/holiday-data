from datetime import date
from pathlib import Path

import pytest

from scripts import fetch_jp, jp_local_calc

FIXTURE = Path(__file__).parent / "fixtures" / "jp_sample.csv"


@pytest.fixture(scope="module")
def official_days() -> dict[date, str]:
    return fetch_jp.parse_csv(FIXTURE.read_text(encoding="utf-8"))


def test_matches_official_csv_for_2007_2027(official_days: dict[date, str]) -> None:
    failures = []
    for year in range(2007, 2028):
        official = {
            (item["date"], item["type"])
            for item in fetch_jp.build_year_days(year, official_days)
        }
        local = {(item["date"], item["type"]) for item in jp_local_calc.year_holidays(year)}
        if official != local:
            failures.append(
                (
                    year,
                    sorted(official - local),
                    sorted(local - official),
                )
            )
    assert not failures, failures


def test_2027_equinox_dates() -> None:
    assert jp_local_calc.vernal_equinox_day(2027) == 21
    assert jp_local_calc.autumnal_equinox_day(2027) == 23


def test_2026_rest_days() -> None:
    by_date = {item["date"]: item["type"] for item in jp_local_calc.year_holidays(2026)}
    assert by_date["2026-05-06"] == "substitute"
    assert by_date["2026-09-22"] == "bridge"


def test_2021_olympic_move_and_substitute() -> None:
    by_date = {item["date"]: item for item in jp_local_calc.year_holidays(2021)}
    assert by_date["2021-07-22"]["name"] == "海の日"
    assert by_date["2021-07-23"]["name"] == "スポーツの日"
    assert by_date["2021-08-08"]["name"] == "山の日"
    assert by_date["2021-08-09"]["type"] == "substitute"


def test_2019_imperial_transition() -> None:
    by_date = {item["date"]: item["type"] for item in jp_local_calc.year_holidays(2019)}
    assert by_date["2019-04-30"] == "bridge"
    assert by_date["2019-05-01"] == "holiday"
    assert by_date["2019-05-02"] == "bridge"
    assert by_date["2019-10-22"] == "holiday"
