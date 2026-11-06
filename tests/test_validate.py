from datetime import date
from pathlib import Path

import pytest

from scripts import build, fetch_cn, fetch_jp, validate
from scripts.common import ValidationError, read_json, write_json_atomic

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


def test_valid_jp_document(official_days: dict[date, str]) -> None:
    validate.validate_jp(jp_document(2026, official_days))


def test_jp_requires_new_year_day(official_days: dict[date, str]) -> None:
    document = jp_document(2026, official_days)
    document["days"] = [item for item in document["days"] if item["date"] != "2026-01-01"]
    with pytest.raises(ValidationError, match="1/1 must be 元日"):
        validate.validate_jp(document)


def test_jp_rejects_duplicate_dates(official_days: dict[date, str]) -> None:
    document = jp_document(2026, official_days)
    document["days"].append(dict(document["days"][0]))
    with pytest.raises(ValidationError, match="duplicate date"):
        validate.validate_jp(document)


def test_jp_rejects_unknown_type(official_days: dict[date, str]) -> None:
    document = jp_document(2026, official_days)
    document["days"][0]["type"] = "unknown"
    with pytest.raises(ValidationError, match="invalid type"):
        validate.validate_jp(document)


def test_manifest_round_trip(tmp_path: Path, official_days: dict[date, str]) -> None:
    write_json_atomic(tmp_path / "jp" / "2026.json", jp_document(2026, official_days))
    write_json_atomic(tmp_path / "cn" / "2027.json", fetch_cn.build_pending(2027))

    manifest = build.build_manifest(tmp_path, None)
    write_json_atomic(tmp_path / "manifest.json", manifest)
    validate.validate_dir(tmp_path)


def test_manifest_detects_tampering(tmp_path: Path, official_days: dict[date, str]) -> None:
    write_json_atomic(tmp_path / "jp" / "2026.json", jp_document(2026, official_days))
    write_json_atomic(tmp_path / "cn" / "2027.json", fetch_cn.build_pending(2027))
    manifest = build.build_manifest(tmp_path, None)
    write_json_atomic(tmp_path / "manifest.json", manifest)

    path = tmp_path / "jp" / "2026.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValidationError, match="sha256 mismatch"):
        validate.validate_dir(tmp_path)


def test_manifest_detects_unlisted_file(
    tmp_path: Path, official_days: dict[date, str]
) -> None:
    write_json_atomic(tmp_path / "jp" / "2026.json", jp_document(2026, official_days))
    write_json_atomic(tmp_path / "cn" / "2027.json", fetch_cn.build_pending(2027))
    manifest = build.build_manifest(tmp_path, None)
    write_json_atomic(tmp_path / "manifest.json", manifest)

    write_json_atomic(tmp_path / "jp" / "2027.json", jp_document(2027, official_days))
    with pytest.raises(ValidationError, match="file list mismatch"):
        validate.validate_dir(tmp_path)


def test_manifest_hashes_match_files(
    tmp_path: Path, official_days: dict[date, str]
) -> None:
    write_json_atomic(tmp_path / "jp" / "2026.json", jp_document(2026, official_days))
    manifest = build.build_manifest(tmp_path, None)
    validate.validate_manifest(manifest, tmp_path)
    assert read_json(tmp_path / "jp" / "2026.json")["year"] == 2026


def test_large_decrease_is_rejected(
    tmp_path: Path, official_days: dict[date, str]
) -> None:
    old = jp_document(2026, official_days)
    write_json_atomic(tmp_path / "jp" / "2026.json", old)

    new = jp_document(2026, official_days)
    new["days"] = new["days"][:5]
    with pytest.raises(ValidationError, match="day count dropped"):
        validate.check_no_large_decrease([new], tmp_path)


def test_small_decrease_is_allowed(
    tmp_path: Path, official_days: dict[date, str]
) -> None:
    old = jp_document(2026, official_days)
    write_json_atomic(tmp_path / "jp" / "2026.json", old)

    new = jp_document(2026, official_days)
    new["days"] = new["days"][:-3]
    validate.check_no_large_decrease([new], tmp_path)
