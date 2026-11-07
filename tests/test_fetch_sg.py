"""新加坡假期解析的离线测试（fixture 是 MOM 页面结构的简化版）。"""

from __future__ import annotations

from datetime import date

from scripts import fetch_sg

PAGE = """
<html><body>
<table>
  <tr><th>Date</th><th>Day</th><th>Holiday image</th><th>Holiday name</th></tr>
  <tr>
    <td>1 January 2026</td><td>Thursday</td><td></td>
    <td>New Year's Day 1 January 2026, Thursday</td>
  </tr>
  <tr>
    <td>17 February 2026 18 February 2026</td><td>Tuesday Wednesday</td><td></td>
    <td>Chinese New Year 17 February 2026 - 18 February 2026, Tuesday - Wednesday</td>
  </tr>
  <tr>
    <td>31 May 2026</td><td>Sunday</td><td></td>
    <td>Vesak Day 31 May 2026, Sunday</td>
  </tr>
</table>
</body></html>
"""


def test_parse_page_reads_names_and_multi_day_holidays() -> None:
    parsed = fetch_sg.parse_page(PAGE)
    assert list(parsed) == [2026]
    days = parsed[2026]
    assert days[0] == {"date": date(2026, 1, 1), "name": "New Year's Day"}
    assert [item["date"] for item in days[1:3]] == [date(2026, 2, 17), date(2026, 2, 18)]
    assert {item["name"] for item in days[1:3]} == {"Chinese New Year"}


def test_sunday_holiday_moves_to_monday() -> None:
    days = fetch_sg.build_year_days(fetch_sg.parse_page(PAGE)[2026])
    by_date = {item["date"]: item for item in days}
    assert by_date["2026-05-31"]["type"] == "holiday"
    observed = by_date["2026-06-01"]
    assert observed["type"] == "observed"
    assert observed["name"] == "Vesak Day"
