from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from scripts import build, fetch_cn, fetch_jp
from scripts.common import ValidationError, write_json_atomic

FIXTURE = Path(__file__).parent / "fixtures" / "jp_sample.csv"


@pytest.fixture(scope="module")
def official_days() -> dict[date, str]:
    return fetch_jp.parse_csv(FIXTURE.read_text(encoding="utf-8"))


def jp_document(year: int, official_days: dict[date, str]) -> dict:
    return {
        "schemaVersion": 1,
        "country": "JP",
        "year": year,
        "source": "内閣府",
        "sourceUrl": "https://example.com/gaiyou.html",
        "days": fetch_jp.build_year_days(year, official_days),
    }


def test_manifest_is_stable_without_content_changes(
    tmp_path: Path, official_days: dict[date, str]
) -> None:
    write_json_atomic(tmp_path / "jp" / "2026.json", jp_document(2026, official_days))
    write_json_atomic(tmp_path / "cn" / "2027.json", fetch_cn.build_pending(2027))

    first = build.build_manifest(tmp_path, None)
    second = build.build_manifest(tmp_path, first)

    assert second["dataVersion"] == first["dataVersion"]
    assert second["generatedAt"] == first["generatedAt"]
    assert (
        second["files"]["jp/2026.json"]["updatedAt"]
        == first["files"]["jp/2026.json"]["updatedAt"]
    )


def test_manifest_version_increases_after_change(
    tmp_path: Path, official_days: dict[date, str]
) -> None:
    write_json_atomic(tmp_path / "jp" / "2026.json", jp_document(2026, official_days))
    first = build.build_manifest(tmp_path, None)

    document = jp_document(2026, official_days)
    document["days"].append(
        {"date": "2026-12-31", "name": "test", "type": "holiday"}
    )
    write_json_atomic(tmp_path / "jp" / "2026.json", document)
    second = build.build_manifest(tmp_path, first)

    assert second["dataVersion"] > first["dataVersion"]
    assert second["generatedAt"] >= first["generatedAt"]


def test_manifest_lists_years(tmp_path: Path, official_days: dict[date, str]) -> None:
    write_json_atomic(tmp_path / "jp" / "2026.json", jp_document(2026, official_days))
    write_json_atomic(tmp_path / "jp" / "2027.json", jp_document(2027, official_days))
    write_json_atomic(tmp_path / "cn" / "2027.json", fetch_cn.build_pending(2027))

    manifest = build.build_manifest(tmp_path, None)
    assert manifest["years"]["jp"] == [2026, 2027]
    assert manifest["years"]["cn"] == [2027]


def test_jp_update_window() -> None:
    march = datetime(2027, 3, 1, 0, 0, tzinfo=timezone.utc)  # 09:00 JST
    build.check_update_windows(jp_years=[2028], now=march)
    with pytest.raises(ValidationError, match="missing after March 1"):
        build.check_update_windows(jp_years=[2027], now=march)

    february = datetime(2027, 2, 28, 0, 0, tzinfo=timezone.utc)
    build.check_update_windows(jp_years=[2027], now=february)


def test_cn_update_window() -> None:
    december = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)  # 08:00 CST
    with pytest.raises(ValidationError, match="missing after December 1"):
        build.check_update_windows(
            cn_documents=[{"year": 2027, "status": "pending"}], now=december
        )
    build.check_update_windows(
        cn_documents=[{"year": 2027, "status": "published"}], now=december
    )

    november = datetime(2026, 11, 30, 0, 0, tzinfo=timezone.utc)
    build.check_update_windows(
        cn_documents=[{"year": 2027, "status": "pending"}], now=november
    )
