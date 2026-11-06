from datetime import date
from pathlib import Path

import pytest

from scripts import fetch_cn, holiday_cn_parser as cn, validate
from scripts.common import ValidationError

NOTICE = Path(__file__).parent / "fixtures" / "cn_2026_notice.txt"


def parsed_2026_days() -> list[dict]:
    text = NOTICE.read_text(encoding="utf-8")
    rules = list(cn.get_rules(text))
    assert len(rules) == 7
    days = []
    for name, description in rules:
        for item in cn.DescriptionParser(description, 2026).parse():
            days.append(
                {
                    "date": item["date"],
                    "name": name,
                    "isOffDay": item["isOffDay"],
                }
            )
    return sorted(days, key=lambda item: item["date"])


def make_document(days: list[dict], *, status: str = "published", year: int = 2026) -> dict:
    return {
        "schemaVersion": 1,
        "country": "CN",
        "year": year,
        "status": status,
        "source": "国务院办公厅",
        "papers": ["https://example.com/notice"],
        "days": [
            {
                "date": item["date"].isoformat(),
                "name": item["name"],
                "isOffDay": item["isOffDay"],
            }
            for item in days
        ],
    }


def test_parse_2026_notice() -> None:
    days = parsed_2026_days()
    assert len(days) == 39
    by_date = {item["date"]: item for item in days}

    assert by_date[date(2026, 1, 1)]["isOffDay"] is True
    assert by_date[date(2026, 1, 4)]["isOffDay"] is False
    assert by_date[date(2026, 2, 15)]["isOffDay"] is True
    assert by_date[date(2026, 2, 23)]["isOffDay"] is True
    assert by_date[date(2026, 2, 14)]["isOffDay"] is False
    assert by_date[date(2026, 2, 28)]["isOffDay"] is False
    assert by_date[date(2026, 5, 9)]["isOffDay"] is False
    assert by_date[date(2026, 9, 20)]["isOffDay"] is False
    assert by_date[date(2026, 10, 10)]["isOffDay"] is False


def test_parse_explicit_cross_year_notice() -> None:
    description = "元旦：2022年12月31日至2023年1月2日放假调休，共3天。"
    days = list(cn.DescriptionParser(description, 2023).parse())
    assert sorted(item["date"] for item in days) == [
        date(2022, 12, 31),
        date(2023, 1, 1),
        date(2023, 1, 2),
    ]


def test_build_year_partitions_cross_year_days() -> None:
    year_2022 = {
        "year": 2022,
        "papers": ["paper-2022"],
        "days": [{"name": "元旦", "date": date(2022, 1, 1), "isOffDay": True}],
    }
    year_2023 = {
        "year": 2023,
        "papers": ["paper-2023"],
        "days": [
            {"name": "元旦", "date": date(2022, 12, 31), "isOffDay": True},
            {"name": "元旦", "date": date(2023, 1, 1), "isOffDay": True},
        ],
    }

    document_2022 = fetch_cn.build_year(2022, year_2022, year_2023)
    assert document_2022 is not None
    assert [item["date"] for item in document_2022["days"]] == [
        "2022-01-01",
        "2022-12-31",
    ]
    assert document_2022["papers"] == ["paper-2022", "paper-2023"]

    document_2023 = fetch_cn.build_year(
        2023, year_2023, {"year": 2024, "papers": [], "days": []}
    )
    assert document_2023 is not None
    assert [item["date"] for item in document_2023["days"]] == ["2023-01-01"]
    assert document_2023["papers"] == ["paper-2023"]


def test_pending_document_is_valid() -> None:
    validate.validate_cn(fetch_cn.build_pending(2027))


def test_valid_2026_document_passes() -> None:
    validate.validate_cn(make_document(parsed_2026_days()))


def test_weekday_make_up_day_is_rejected() -> None:
    days = parsed_2026_days() + [
        {"date": date(2026, 1, 5), "name": "元旦", "isOffDay": False}
    ]
    with pytest.raises(ValidationError, match="not a weekend"):
        validate.validate_cn(make_document(days))


def test_missing_festival_is_rejected() -> None:
    days = [item for item in parsed_2026_days() if "春节" not in item["name"]]
    with pytest.raises(ValidationError, match="missing festival 春节"):
        validate.validate_cn(make_document(days))


def test_date_outside_year_is_rejected() -> None:
    days = parsed_2026_days()
    days[0] = {**days[0], "date": date(2027, 1, 1)}
    with pytest.raises(ValidationError, match="outside 2026"):
        validate.validate_cn(make_document(days))


def test_pending_with_days_is_rejected() -> None:
    document = make_document(parsed_2026_days(), status="pending")
    with pytest.raises(ValidationError, match="pending file must have no days"):
        validate.validate_cn(document)
