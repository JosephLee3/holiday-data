"""生成数据的校验规则。

这些检查刻意保守：失败就意味着不发布，App 继续使用上一版数据。
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .common import ValidationError, read_json, sha256_file

SCHEMA_VERSION = 1
CHINA_TZ = timezone(timedelta(hours=8))
JP_MIN_YEAR = 2007
JP_DAY_COUNT_RANGE = (14, 24)
CN_MIN_YEAR = 2008
CN_MIN_OFF_DAYS = 15
CN_MAX_OFF_DAYS = 40
CN_MAX_WORK_DAYS = 15
CN_REQUIRED_NAMES = ("元旦", "春节", "清明节", "劳动节", "端午节", "中秋节", "国庆节")
# 2020 年疫情延长假期把周一 2020-02-03 设成了上班日。
CN_WEEKDAY_WORK_ALLOWLIST = {date(2020, 2, 3)}


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _parse_day(value: object, context: str) -> date:
    _expect(isinstance(value, str) and len(value) == 10, f"{context}: invalid date")
    try:
        return date.fromisoformat(value)  # type: ignore[arg-type]
    except ValueError as error:
        raise ValidationError(f"{context}: invalid date {value!r}") from error


def _check_common_header(document: dict, country: str) -> None:
    _expect(isinstance(document, dict), f"{country}: document is not an object")
    _expect(
        document.get("schemaVersion") == SCHEMA_VERSION,
        f"{country}: unsupported schemaVersion {document.get('schemaVersion')!r}",
    )
    _expect(document.get("country") == country, f"{country}: wrong country field")
    _expect(
        isinstance(document.get("year"), int),
        f"{country}: year must be an integer",
    )
    _expect(
        isinstance(document.get("source"), str) and document["source"],
        f"{country}: missing source",
    )
    _expect(isinstance(document.get("days"), list), f"{country}: days must be a list")


def validate_jp(document: dict) -> None:
    _check_common_header(document, "JP")
    year = document["year"]
    _expect(year >= JP_MIN_YEAR, f"JP: year {year} is below {JP_MIN_YEAR}")
    _expect(
        isinstance(document.get("sourceUrl"), str) and document["sourceUrl"],
        "JP: missing sourceUrl",
    )

    days = document["days"]
    _expect(len(days) >= 1, "JP: no days")
    _expect(
        JP_DAY_COUNT_RANGE[0] <= len(days) <= JP_DAY_COUNT_RANGE[1],
        f"JP {year}: day count {len(days)} outside {JP_DAY_COUNT_RANGE}",
    )

    parsed: list[date] = []
    names: dict[date, str] = {}
    types: dict[date, str] = {}
    for index, item in enumerate(days):
        context = f"JP {year} day #{index}"
        _expect(isinstance(item, dict), f"{context}: not an object")
        day = _parse_day(item.get("date"), context)
        _expect(day.year == year, f"{context}: date {day} is outside {year}")
        _expect(
            isinstance(item.get("name"), str) and item["name"],
            f"{context}: missing name",
        )
        _expect(
            item.get("type") in {"holiday", "substitute", "bridge"},
            f"{context}: invalid type {item.get('type')!r}",
        )
        if day in names:
            raise ValidationError(f"{context}: duplicate date {day}")
        parsed.append(day)
        names[day] = item["name"]
        types[day] = item["type"]

    _expect(parsed == sorted(parsed), f"JP {year}: days are not sorted")
    _expect(names.get(date(year, 1, 1)) == "元日", f"JP {year}: 1/1 must be 元日")

    # 重新检查分类规则：bridge 两侧必须都是休日；substitute 之前的连续
    # 休日块里必须有一个周日。
    non_substitute = {day for day, kind in types.items() if kind != "substitute"}
    for day, kind in types.items():
        if kind == "bridge":
            _expect(
                (day - timedelta(days=1)) in names
                and (day + timedelta(days=1)) in names,
                f"JP {year}: bridge {day} is not between two holidays",
            )
        elif kind == "substitute":
            cursor = day - timedelta(days=1)
            block: list[date] = []
            while cursor in non_substitute:
                block.append(cursor)
                cursor -= timedelta(days=1)
            _expect(
                any(item.weekday() == 6 for item in block),
                f"JP {year}: substitute {day} does not follow a Sunday holiday",
            )


def validate_cn(document: dict) -> None:
    _check_common_header(document, "CN")
    year = document["year"]
    _expect(year >= CN_MIN_YEAR, f"CN: year {year} is below {CN_MIN_YEAR}")
    status = document.get("status", "published")
    _expect(status in {"published", "pending"}, f"CN {year}: invalid status {status!r}")

    papers = document.get("papers")
    _expect(isinstance(papers, list), f"CN {year}: papers must be a list")

    days = document["days"]
    if status == "pending":
        _expect(not days, f"CN {year}: pending file must have no days")
        _expect(not papers, f"CN {year}: pending file must have no papers")
        return

    _expect(days, f"CN {year}: published file has no days")
    _expect(papers, f"CN {year}: published file has no papers")

    parsed: list[date] = []
    names: dict[date, str] = {}
    off_days = 0
    work_days = 0
    for index, item in enumerate(days):
        context = f"CN {year} day #{index}"
        _expect(isinstance(item, dict), f"{context}: not an object")
        day = _parse_day(item.get("date"), context)
        _expect(day.year == year, f"{context}: date {day} is outside {year}")
        _expect(
            isinstance(item.get("name"), str) and item["name"],
            f"{context}: missing name",
        )
        _expect(isinstance(item.get("isOffDay"), bool), f"{context}: isOffDay must be bool")
        if day in names:
            raise ValidationError(f"{context}: duplicate date {day}")
        parsed.append(day)
        names[day] = item["name"]
        if item["isOffDay"]:
            off_days += 1
        else:
            work_days += 1
            _expect(
                day.weekday() >= 5 or day in CN_WEEKDAY_WORK_ALLOWLIST,
                f"CN {year}: make-up work day {day} is not a weekend",
            )

    _expect(parsed == sorted(parsed), f"CN {year}: days are not sorted")
    _expect(
        CN_MIN_OFF_DAYS <= off_days <= CN_MAX_OFF_DAYS,
        f"CN {year}: off-day count {off_days} outside "
        f"{CN_MIN_OFF_DAYS}..{CN_MAX_OFF_DAYS}",
    )
    _expect(
        work_days <= CN_MAX_WORK_DAYS,
        f"CN {year}: work-day count {work_days} exceeds {CN_MAX_WORK_DAYS}",
    )

    all_names = " ".join(names.values())
    for required in CN_REQUIRED_NAMES:
        _expect(required in all_names, f"CN {year}: missing festival {required}")


def validate_manifest(manifest: dict, root: Path | None = None) -> None:
    _expect(
        manifest.get("schemaVersion") == SCHEMA_VERSION,
        "manifest: unsupported schemaVersion",
    )
    _expect(
        isinstance(manifest.get("dataVersion"), int),
        "manifest: dataVersion must be an integer",
    )
    _expect(
        isinstance(manifest.get("generatedAt"), str) and manifest["generatedAt"],
        "manifest: missing generatedAt",
    )
    files = manifest.get("files")
    _expect(isinstance(files, dict), "manifest: files must be an object")

    for relative, entry in files.items():
        _expect(isinstance(entry, dict), f"manifest: {relative} entry is not an object")
        _expect(
            isinstance(entry.get("sha256"), str),
            f"manifest: {relative} missing sha256",
        )
        _expect(
            isinstance(entry.get("updatedAt"), str) and entry["updatedAt"],
            f"manifest: {relative} missing updatedAt",
        )

    if root is None:
        return

    listed = set(files)
    actual = {
        path.relative_to(root).as_posix()
        for path in (root / "jp").glob("*.json")
    } | {
        path.relative_to(root).as_posix()
        for path in (root / "cn").glob("*.json")
    }
    _expect(listed == actual, f"manifest: file list mismatch: {listed ^ actual}")

    for relative, entry in files.items():
        path = root / relative
        _expect(path.is_file(), f"manifest: missing file {relative}")
        actual_hash = sha256_file(path)
        _expect(
            actual_hash == entry["sha256"],
            f"manifest: {relative} sha256 mismatch "
            f"(expected {entry['sha256']}, got {actual_hash})",
        )


def check_no_large_decrease(documents: list[dict], output: Path) -> None:
    """新数据的条目数比已发布版本骤降时拒绝发布。

    绝对范围能挡住大部分解析错误，但挡不住“从 22 条掉到 15 条”这种仍在
    范围内、却明显是解析问题的变化。
    """
    for document in documents:
        country = document.get("country")
        year = document.get("year")
        if not isinstance(country, str) or not isinstance(year, int):
            continue
        path = output / country.lower() / f"{year}.json"
        if not path.is_file():
            continue
        old_document = read_json(path)
        old_days = len(old_document.get("days", []))
        new_days = len(document.get("days", []))
        if old_days and new_days < old_days * 0.7:
            raise ValidationError(
                f"{country} {year}: day count dropped from {old_days} to "
                f"{new_days} (>30%)"
            )


def validate_dir(root: Path) -> None:
    manifest_path = root / "manifest.json"
    _expect(manifest_path.is_file(), f"missing manifest: {manifest_path}")
    manifest = read_json(manifest_path)
    validate_manifest(manifest, root)

    jp_years: list[int] = []
    cn_years: list[int] = []
    for relative in sorted(manifest["files"]):
        document = read_json(root / relative)
        if relative.startswith("jp/"):
            validate_jp(document)
            jp_years.append(document["year"])
        elif relative.startswith("cn/"):
            validate_cn(document)
            cn_years.append(document["year"])
        else:
            raise ValidationError(f"unexpected data file: {relative}")

    for years, country in ((sorted(jp_years), "JP"), (sorted(cn_years), "CN")):
        _expect(years, f"{country}: no year files")
        expected = list(range(years[0], years[-1] + 1))
        _expect(years == expected, f"{country}: year files are not contiguous: {years}")

    current_year = datetime.now(CHINA_TZ).year
    for relative in manifest["files"]:
        if not relative.startswith("cn/"):
            continue
        document = read_json(root / relative)
        if document.get("status") == "pending":
            _expect(
                document["year"] > current_year,
                f"CN {document['year']}: pending status for a year that has started",
            )

    print(
        f"OK: {len(jp_years)} JP years ({jp_years[0]}..{jp_years[-1]}), "
        f"{len(cn_years)} CN years ({cn_years[0]}..{cn_years[-1]}), "
        f"dataVersion={manifest['dataVersion']}"
    )


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/v1")
    try:
        validate_dir(root)
    except ValidationError as error:
        print(f"VALIDATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
