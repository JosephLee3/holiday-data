"""从 gov.cn 抓取并规范化中国法定节假日安排。

通知正文的解析复用 NateScarlet/holiday-cn（MIT）；本模块负责年份分区、
跨年日期和「尚未公布」状态。
"""

from __future__ import annotations

import sys
import warnings
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import holiday_cn_parser as cn_parser
from .common import ValidationError

SCHEMA_VERSION = 1
SOURCE_NAME = "国务院办公厅"
CHINA_TZ = timezone(timedelta(hours=8))
# 2008 年是现代法定节日组合的第一年（清明、端午、中秋从 2008 年起成为
# 法定假日）。2007 年通知里的名称格式不同（「五一」「十一」）。
MIN_YEAR = 2008


def china_today() -> date:
    return datetime.now(CHINA_TZ).date()


def _empty_year(year: int) -> dict[str, Any]:
    return {"year": year, "papers": [], "days": []}


def _fetch_year(year: int, current_year: int) -> dict[str, Any] | None:
    """抓取一年；历史链接失效时容忍，当前年份缺失时失败。"""
    try:
        return cn_parser.fetch_holiday(year)
    except Exception as error:  # noqa: BLE001 - 网络/解析失败是预期情况
        if year > current_year:
            # 明年的通知本来就还没发布。
            return _empty_year(year)
        if year == current_year:
            raise
        warnings.warn(
            f"skipping historical Chinese year {year}: {error}",
            stacklevel=2,
        )
        return None


def build_year(
    year: int,
    year_data: dict[str, Any],
    next_year_data: dict[str, Any],
) -> dict[str, Any] | None:
    """由 Y 年和 Y+1 年的通知构建 cn/{Y}.json。

    Y 年的通知可能包含 Y-1 年 12 月的日期（例如 2023 年通知从 2022-12-31
    开始）。因此同时读 Y 和 Y+1，但只保留日历年份为 Y 的日期，使发布文件
    严格按日历年归档。
    """
    days: dict[date, dict[str, Any]] = {}
    papers: set[str] = set()

    for data in (year_data, next_year_data):
        contributed = False
        for item in data.get("days", []):
            day = item["date"]
            if day.year != year:
                continue
            if day in days:
                # 同一天被两个通知提到时，优先保留 Y 年自己的通知。
                continue
            days[day] = {
                "date": day.isoformat(),
                "name": item["name"],
                "isOffDay": bool(item["isOffDay"]),
            }
            contributed = True
        if contributed:
            papers.update(data.get("papers", []))

    if not days:
        return None

    return {
        "schemaVersion": SCHEMA_VERSION,
        "country": "CN",
        "year": year,
        "status": "published",
        "source": SOURCE_NAME,
        "papers": sorted(papers),
        "days": [days[day] for day in sorted(days)],
    }


def build_pending(year: int) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "country": "CN",
        "year": year,
        "status": "pending",
        "source": SOURCE_NAME,
        "papers": [],
        "days": [],
    }


def build_docs(
    min_year: int = MIN_YEAR,
    max_year: int | None = None,
    *,
    years: list[int] | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """抓取通知，返回每个日历年一个文档。

    `years` 为空时抓取 min_year..max_year 全部年份（首次运行/回填）；
    传入年份列表时只抓这些年份（日常运行只抓当年、次年、以及缺失的年份）。
    """
    current = today or china_today()
    if max_year is None:
        max_year = current.year + 1
    if max_year < min_year:
        raise ValidationError(f"invalid Chinese year range {min_year}..{max_year}")

    if years is None:
        target_years = list(range(min_year, max_year + 1))
    else:
        target_years = sorted({year for year in years if min_year <= year <= max_year})

    cache: dict[int, dict[str, Any] | None] = {}

    def get(year: int) -> dict[str, Any] | None:
        if year not in cache:
            print(f"CN: fetching {year}", flush=True)
            cache[year] = _fetch_year(year, current.year)
        return cache[year]

    documents: list[dict[str, Any]] = []
    for year in target_years:
        year_data = get(year)
        if year_data is None:
            continue
        if not year_data.get("days"):
            if year > current.year:
                documents.append(build_pending(year))
            elif year == current.year:
                raise ValidationError(
                    f"Chinese {year} notice is missing but the year has started"
                )
            else:
                warnings.warn(
                    f"no Chinese data for historical year {year}, keeping old file",
                    stacklevel=2,
                )
            continue

        next_year_data = get(year + 1) or _empty_year(year + 1)
        document = build_year(year, year_data, next_year_data)
        if document is None:
            if year > current.year:
                documents.append(build_pending(year))
            else:
                warnings.warn(
                    f"Chinese {year} produced no calendar-year days, keeping old file",
                    stacklevel=2,
                )
            continue
        documents.append(document)

    return documents


def main() -> None:  # pragma: no cover - 手动调试
    for document in build_docs():
        print(
            document["year"],
            document["status"],
            len(document["days"]),
            len(document["papers"]),
            file=sys.stdout,
        )


if __name__ == "__main__":  # pragma: no cover
    main()
