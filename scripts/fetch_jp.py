"""从内閣府抓取并规范化日本国民の祝日。

每次运行都从官方页面解析 CSV 链接，因为链接历史上变过。CSV 为 CP932
（Shift_JIS），覆盖 1955 年至下一年。
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import ValidationError, http_get, http_get_text

PAGE_URL = "https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html"
SOURCE_NAME = "内閣府"
SCHEMA_VERSION = 1

# 现代的振替休日规则（周日祝日之后的第一个非休日）从 2007 年开始适用。
# 更早年份需要不同的规则，因此本管道只生成 2007 年以后的数据。
MIN_YEAR = 2007


def find_csv_url(page_url: str = PAGE_URL) -> str:
    """在官方页面上找到节假日 CSV 链接。"""
    html = http_get_text(page_url)
    soup = BeautifulSoup(html, "html.parser")
    candidates = [
        urljoin(page_url, anchor["href"])
        for anchor in soup.find_all("a", href=True)
        if anchor["href"].lower().endswith(".csv")
    ]
    if not candidates:
        raise RuntimeError(f"no CSV link found on {page_url}")
    # 页面上可能有多个 CSV；优先选文件名里带 syukujitsu/shukujitsu 的那个。
    for url in candidates:
        if "syukujitsu" in url.lower() or "shukujitsu" in url.lower():
            return url
    return candidates[0]


def parse_csv(text: str) -> dict[date, str]:
    """把 CP932 解码后的 CSV 解析为 {日期: 官方名称}。"""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as error:
        raise ValidationError("Japanese CSV is empty") from error

    if len(header) < 2:
        raise ValidationError(f"unexpected Japanese CSV header: {header!r}")

    days: dict[date, str] = {}
    for row in reader:
        if not row or not row[0].strip():
            continue
        if len(row) < 2:
            raise ValidationError(f"unexpected Japanese CSV row: {row!r}")
        year, month, day = (int(part) for part in row[0].split("/"))
        name = row[1].strip()
        if not name:
            raise ValidationError(f"empty holiday name for {row[0]}")
        key = date(year, month, day)
        if key in days:
            raise ValidationError(f"duplicate Japanese holiday date: {key}")
        days[key] = name
    if not days:
        raise ValidationError("Japanese CSV contains no holidays")
    return days


def _classify_rest_day(
    day: date, year_days: dict[date, str], regular_holidays: set[date]
) -> str:
    """把 CSV 中名称为「休日」的行分类为振替休日或国民の休日。

    - 振替休日：周日祝日之后的第一个非休日。向前走过连续的休日，
      一定会遇到那个周日的祝日。
    - 国民の休日：夹在两个祝日之间的非休日工作日。
    """
    cursor = day - timedelta(days=1)
    chain: list[date] = []
    while cursor in regular_holidays:
        chain.append(cursor)
        cursor -= timedelta(days=1)

    if any(item.weekday() == 6 for item in chain):
        return "substitute"
    if (day - timedelta(days=1)) in regular_holidays and (
        day + timedelta(days=1)
    ) in regular_holidays:
        return "bridge"
    raise ValidationError(
        f"cannot classify Japanese rest day {day}: "
        f"previous holidays={chain}, name={year_days[day]!r}"
    )


def build_year_days(year: int, all_days: dict[date, str]) -> list[dict]:
    """构建某一年的规范化数据。"""
    year_days = {day: name for day, name in all_days.items() if day.year == year}
    if not year_days:
        raise ValidationError(f"no Japanese holidays for {year}")

    if year_days.get(date(year, 1, 1)) != "元日":
        raise ValidationError(f"Japanese {year} does not start with 元日 on 1/1")

    regular_holidays = {day for day, name in year_days.items() if name != "休日"}

    normalized: list[dict] = []
    for day in sorted(year_days):
        name = year_days[day]
        if name != "休日":
            kind = "holiday"
        else:
            kind = _classify_rest_day(day, year_days, regular_holidays)
        normalized.append({"date": day.isoformat(), "name": name, "type": kind})

    return normalized


def build_docs(
    min_year: int = MIN_YEAR,
    max_year: int | None = None,
    *,
    page_url: str = PAGE_URL,
) -> list[dict]:
    """抓取官方 CSV，返回每年一个文档。"""
    csv_url = find_csv_url(page_url)
    csv_bytes = http_get(csv_url)
    try:
        csv_text = csv_bytes.decode("cp932")
    except UnicodeDecodeError as error:
        raise ValidationError(
            f"Japanese CSV is not valid CP932: {csv_url}"
        ) from error

    all_days = parse_csv(csv_text)
    available_years = sorted({day.year for day in all_days})
    years = [
        year
        for year in available_years
        if year >= min_year and (max_year is None or year <= max_year)
    ]
    if not years:
        raise ValidationError(
            f"no Japanese holidays in requested range {min_year}..{max_year}"
        )

    documents = []
    for year in years:
        documents.append(
            {
                "schemaVersion": SCHEMA_VERSION,
                "country": "JP",
                "year": year,
                "source": SOURCE_NAME,
                "sourceUrl": page_url,
                "csvUrl": csv_url,
                "days": build_year_days(year, all_days),
            }
        )
    return documents


def main() -> None:  # pragma: no cover - 手动调试
    csv_url = find_csv_url()
    print(f"CSV: {csv_url}")
    for document in build_docs():
        print(document["year"], len(document["days"]))


if __name__ == "__main__":  # pragma: no cover
    main()
