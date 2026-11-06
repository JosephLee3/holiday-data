"""日本祝日的本地计算参考实现。

这里镜像将来要移植到 Kotlin 的离线兜底规则。只覆盖 2007 年以后（现代
振替休日规则），并单独处理 2019 年即位和 2020/2021 奥运改期这两个特例，
以便黄金测试能和官方 CSV 在 2007–2027 逐年对比。

未来的特别立法无法预测，始终以远程数据为准。
"""

from __future__ import annotations

from datetime import date, timedelta

MIN_YEAR = 2007
MAX_YEAR = 2099


def nth_monday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (0 - first.weekday()) % 7  # 周一 == 0
    return first + timedelta(days=offset + 7 * (n - 1))


def vernal_equinox_day(year: int) -> int:
    return int(20.8431 + 0.242194 * (year - 1980) - int((year - 1980) / 4))


def autumnal_equinox_day(year: int) -> int:
    return int(23.2488 + 0.242194 * (year - 1980) - int((year - 1980) / 4))


def _emperor_birthday(year: int) -> date | None:
    if year <= 2018:
        return date(year, 12, 23)
    if year >= 2020:
        return date(year, 2, 23)
    return None  # 2019 年没有天皇誕生日


def base_holidays(year: int) -> dict[date, str]:
    """返回国民の祝日（不含振替休日和国民の休日）。"""
    holidays: dict[date, str] = {
        date(year, 1, 1): "元日",
        nth_monday(year, 1, 2): "成人の日",
        date(year, 2, 11): "建国記念の日",
        date(year, 3, vernal_equinox_day(year)): "春分の日",
        date(year, 4, 29): "昭和の日",
        date(year, 5, 3): "憲法記念日",
        date(year, 5, 4): "みどりの日",
        date(year, 5, 5): "こどもの日",
        nth_monday(year, 9, 3): "敬老の日",
        date(year, 9, autumnal_equinox_day(year)): "秋分の日",
        date(year, 11, 3): "文化の日",
        date(year, 11, 23): "勤労感謝の日",
    }

    emperor = _emperor_birthday(year)
    if emperor is not None:
        holidays[emperor] = "天皇誕生日"

    # 2020/2021 年东京奥运期间，海の日、スポーツの日、山の日被移动。
    if year == 2020:
        holidays[date(2020, 7, 23)] = "海の日"
        holidays[date(2020, 7, 24)] = "スポーツの日"
        holidays[date(2020, 8, 10)] = "山の日"
    elif year == 2021:
        holidays[date(2021, 7, 22)] = "海の日"
        holidays[date(2021, 7, 23)] = "スポーツの日"
        holidays[date(2021, 8, 8)] = "山の日"
    else:
        holidays[nth_monday(year, 7, 3)] = "海の日"
        holidays[nth_monday(year, 10, 2)] = (
            "スポーツの日" if year >= 2020 else "体育の日"
        )
        if year >= 2016:
            holidays[date(year, 8, 11)] = "山の日"

    # 2019 年即位相关的特别休日。
    if year == 2019:
        holidays[date(2019, 5, 1)] = "休日（祝日扱い）"
        holidays[date(2019, 10, 22)] = "休日（祝日扱い）"

    return holidays


def year_holidays(year: int) -> list[dict]:
    """返回某一年的完整祝日列表（含振替休日和国民の休日）。"""
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"year {year} is outside the supported range")

    base = base_holidays(year)

    bridges: dict[date, str] = {}
    cursor = date(year, 1, 1)
    while cursor.year == year:
        if (
            cursor not in base
            and cursor.weekday() != 6
            and (cursor - timedelta(days=1)) in base
            and (cursor + timedelta(days=1)) in base
        ):
            bridges[cursor] = "休日"
        cursor += timedelta(days=1)

    substitutes: dict[date, str] = {}
    occupied = set(base) | set(bridges) | set(substitutes)
    for holiday in sorted(base):
        if holiday.weekday() != 6:
            continue
        candidate = holiday + timedelta(days=1)
        while candidate in occupied:
            candidate += timedelta(days=1)
        substitutes[candidate] = "休日"
        occupied.add(candidate)

    rows: list[dict] = []
    for day in sorted(set(base) | set(bridges) | set(substitutes)):
        if day in base:
            kind = "holiday"
            name = base[day]
        elif day in substitutes:
            kind = "substitute"
            name = "休日"
        else:
            kind = "bridge"
            name = "休日"
        rows.append({"date": day.isoformat(), "name": name, "type": kind})
    return rows


def main() -> None:  # pragma: no cover - 手动调试
    import sys

    year = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    for row in year_holidays(year):
        print(row["date"], row["name"], row["type"])


if __name__ == "__main__":  # pragma: no cover
    main()
