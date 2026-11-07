"""从新加坡人力部（MOM）抓取公共假期。

页面 https://www.mom.gov.sg/employment-practices/public-holidays 上有三个
年份的表格（通常是上一年、当年、次年），每行给出日期、星期和假期名称。

公共假期落在周日时，次日周一补假（Employment Act）。表格里不单列补假日，
这里按规则推出，type 记为 observed。
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from .common import ValidationError, http_get_text

PAGE_URL = "https://www.mom.gov.sg/employment-practices/public-holidays"
SOURCE_NAME = "Ministry of Manpower, Singapore"
SCHEMA_VERSION = 1

# 页面上只挂最近三年，更早的年份没有稳定的官方页面。
MIN_YEAR = 2020

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})",
    re.IGNORECASE,
)


def parse_page(html: str) -> dict[int, list[dict]]:
    """解析页面上的年度表格，返回 {年份: [{"date": date, "name": str}]}。"""
    soup = BeautifulSoup(html, "html.parser")
    collected: dict[int, dict[date, str]] = {}

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            days = [
                date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))
                for match in DATE_PATTERN.finditer(cells[0])
            ]
            if not days:
                continue

            # 名称单元格里会再重复一遍日期，取第一个日期之前的部分。
            name = DATE_PATTERN.split(cells[-1])[0]
            name = re.sub(r"\s+", " ", name).replace("’", "'").strip(" ,-–")
            if not name:
                continue

            for day in days:
                collected.setdefault(day.year, {})[day] = name

    return {
        year: [
            {"date": day, "name": name}
            for day, name in sorted(items.items())
        ]
        for year, items in collected.items()
    }


def build_year_days(holidays: list[dict]) -> list[dict]:
    """把一年的假期补上「周日顺延到周一」，输出文档里的 days。"""
    by_date: dict[date, dict] = {
        item["date"]: {
            "date": item["date"].isoformat(),
            "name": item["name"],
            "type": "holiday",
        }
        for item in holidays
    }

    for item in list(by_date.values()):
        day = date.fromisoformat(item["date"])
        if day.weekday() != 6:  # 只在周日
            continue
        observed = day + timedelta(days=1)
        if observed.year != day.year:
            # 12 月 31 日是周日时，补假落到下一年，留给下一年的文件。
            continue
        if observed.isoformat() in by_date:
            continue
        by_date[observed] = {
            "date": observed.isoformat(),
            "name": item["name"],
            "type": "observed",
        }

    return [by_date[key] for key in sorted(by_date)]


def build_docs(
    min_year: int = MIN_YEAR,
    max_year: int | None = None,
    *,
    page_url: str = PAGE_URL,
) -> list[dict]:
    """抓取官方页面，返回每年一个文档。"""
    parsed = parse_page(http_get_text(page_url))
    years = [
        year
        for year in sorted(parsed)
        if year >= min_year and (max_year is None or year <= max_year)
    ]
    if not years:
        raise ValidationError(
            f"no Singapore holidays in requested range {min_year}..{max_year}"
        )

    documents = []
    for year in years:
        documents.append(
            {
                "schemaVersion": SCHEMA_VERSION,
                "country": "SG",
                "year": year,
                "status": "published",
                "source": SOURCE_NAME,
                "sourceUrl": page_url,
                "days": build_year_days(parsed[year]),
            }
        )
    return documents


def main() -> None:  # pragma: no cover - 手动调试
    for document in build_docs():
        print(document["year"], len(document["days"]), "days")
        for day in document["days"]:
            print(" ", day["date"], day["type"], day["name"])


if __name__ == "__main__":  # pragma: no cover
    main()
