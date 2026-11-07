"""从官方源构建 docs/v1。

构建是事务性的：先在临时目录生成并校验，通过后才复制到发布目录。
校验失败时上一版数据保持不变。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import fetch_cn, fetch_jp, fetch_sg, validate
from .common import (
    ValidationError,
    iso_utc,
    read_json,
    sha256_file,
    utc_now,
    write_json_atomic,
)

SCHEMA_VERSION = 1
JST = timezone(timedelta(hours=9))
CST = timezone(timedelta(hours=8))


def check_update_windows(
    jp_years: list[int] | None = None,
    cn_documents: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> None:
    """预期的年度更新缺失时让构建失败。

    两个来源都有年度节奏：日本在 2 月追加下一年，中国在 10–11 月公布次年
    通知。没有这个检查，管道可能在数据已经过期时仍然看起来正常。
    """
    now = now or utc_now()

    if jp_years:
        today = now.astimezone(JST).date()
        if today.month >= 3 and max(jp_years) < today.year + 1:
            raise ValidationError(
                f"JP: {today.year + 1} data is missing after March 1 "
                f"(latest year: {max(jp_years)})"
            )

    if cn_documents is not None:
        today = now.astimezone(CST).date()
        if today.month >= 12:
            target = today.year + 1
            document = next(
                (item for item in cn_documents if item.get("year") == target),
                None,
            )
            if document is None or document.get("status") != "published":
                raise ValidationError(
                    f"CN: {target} notice is missing after December 1"
                )



def _data_path(document: dict[str, Any]) -> str:
    country = document["country"].lower()
    return f"{country}/{document['year']}.json"


def _collect_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for country in ("jp", "cn", "sg"):
        directory = root / country
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            files[path.relative_to(root).as_posix()] = path
    return files


def build_manifest(root: Path, old_manifest: dict[str, Any] | None) -> dict[str, Any]:
    now = utc_now()
    old_files = (old_manifest or {}).get("files", {})
    files: dict[str, dict[str, Any]] = {}
    changed = old_manifest is None

    for relative, path in sorted(_collect_files(root).items()):
        digest = sha256_file(path)
        old_entry = old_files.get(relative)
        if old_entry and old_entry.get("sha256") == digest:
            updated_at = old_entry.get("updatedAt") or iso_utc(now)
        else:
            updated_at = iso_utc(now)
            changed = True
        files[relative] = {
            "sha256": digest,
            "updatedAt": updated_at,
            "bytes": path.stat().st_size,
        }

    if set(files) != set(old_files):
        changed = True

    old_version = (old_manifest or {}).get("dataVersion", 0)
    if not isinstance(old_version, int):
        old_version = 0
    if changed:
        candidate = int(now.strftime("%Y%m%d%H%M%S"))
        data_version = max(candidate, old_version + 1)
        generated_at = iso_utc(now)
    else:
        data_version = old_version
        generated_at = (old_manifest or {}).get("generatedAt") or iso_utc(now)

    years = {
        "jp": sorted(
            int(Path(relative).stem)
            for relative in files
            if relative.startswith("jp/")
        ),
        "cn": sorted(
            int(Path(relative).stem)
            for relative in files
            if relative.startswith("cn/")
        ),
        "sg": sorted(
            int(Path(relative).stem)
            for relative in files
            if relative.startswith("sg/")
        ),
    }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "dataVersion": data_version,
        "generatedAt": generated_at,
        "years": years,
        "files": files,
    }


def build(
    output: Path,
    *,
    jp_min_year: int = fetch_jp.MIN_YEAR,
    cn_min_year: int = fetch_cn.MIN_YEAR,
    cn_max_year: int | None = None,
    skip_jp: bool = False,
    skip_cn: bool = False,
    skip_sg: bool = False,
    check_windows: bool = True,
    all_cn_years: bool = False,
) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    jp_documents: list[dict[str, Any]] = []
    cn_documents: list[dict[str, Any]] = []

    if not skip_jp:
        jp_documents = fetch_jp.build_docs(min_year=jp_min_year)
        for document in jp_documents:
            validate.validate_jp(document)
        documents.extend(jp_documents)
        print(f"JP: {len(jp_documents)} years fetched")

    cn_years: list[int] | None = None
    if not skip_cn and not all_cn_years:
        existing_cn_years = (
            {
                int(path.stem)
                for path in (output / "cn").glob("*.json")
                if path.stem.isdigit()
            }
            if (output / "cn").is_dir()
            else set()
        )
        if existing_cn_years:
            current_cn_year = fetch_cn.china_today().year
            upper = cn_max_year or current_cn_year + 1
            wanted = {current_cn_year, current_cn_year + 1}
            wanted |= set(range(cn_min_year, upper + 1)) - existing_cn_years
            cn_years = sorted(
                year for year in wanted if cn_min_year <= year <= upper
            )

    sg_documents: list[dict[str, Any]] = []
    if not skip_sg:
        sg_documents = fetch_sg.build_docs(min_year=fetch_sg.MIN_YEAR)
        for document in sg_documents:
            validate.validate_sg(document)
        documents.extend(sg_documents)
        print(
            "SG: "
            + ", ".join(f"{document['year']}={len(document['days'])}天"
                        for document in sg_documents)
        )

    if not skip_cn:
        cn_documents = fetch_cn.build_docs(
            min_year=cn_min_year, max_year=cn_max_year, years=cn_years
        )
        for document in cn_documents:
            validate.validate_cn(document)
        documents.extend(cn_documents)
        print(
            "CN: "
            + ", ".join(
                f"{document['year']}={document['status']}"
                for document in cn_documents
            )
        )

    if not documents:
        raise ValidationError("nothing to build")

    if check_windows:
        check_update_windows(
            [document["year"] for document in jp_documents] if not skip_jp else None,
            cn_documents if not skip_cn else None,
        )

    validate.check_no_large_decrease(documents, output)

    old_manifest = None
    if (output / "manifest.json").is_file():
        old_manifest = read_json(output / "manifest.json")

    with tempfile.TemporaryDirectory(prefix="cnjp-holiday-") as temporary:
        stage = Path(temporary)
        if output.is_dir():
            shutil.copytree(output, stage, dirs_exist_ok=True)

        for document in documents:
            write_json_atomic(stage / _data_path(document), document)

        manifest = build_manifest(stage, old_manifest)
        write_json_atomic(stage / "manifest.json", manifest)

        # 在改动真实输出目录之前，先校验完整的临时目录。
        validate.validate_dir(stage)

        output.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, output, dirs_exist_ok=True)

    print(
        f"published: JP {len(manifest['years']['jp'])} years, "
        f"CN {len(manifest['years']['cn'])} years, "
        f"SG {len(manifest['years']['sg'])} years, "
        f"dataVersion={manifest['dataVersion']}"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/v1"))
    parser.add_argument("--jp-min-year", type=int, default=fetch_jp.MIN_YEAR)
    parser.add_argument("--cn-min-year", type=int, default=fetch_cn.MIN_YEAR)
    parser.add_argument("--cn-max-year", type=int, default=None)
    parser.add_argument("--skip-jp", action="store_true")
    parser.add_argument("--skip-cn", action="store_true")
    parser.add_argument("--skip-sg", action="store_true")
    parser.add_argument("--skip-window-check", action="store_true")
    parser.add_argument(
        "--all-cn-years",
        action="store_true",
        help="重新抓取全部中国年份（默认只抓当年、次年、缺失年份）",
    )
    args = parser.parse_args()

    try:
        build(
            args.output,
            jp_min_year=args.jp_min_year,
            cn_min_year=args.cn_min_year,
            cn_max_year=args.cn_max_year,
            skip_jp=args.skip_jp,
            skip_cn=args.skip_cn,
            skip_sg=args.skip_sg,
            check_windows=not args.skip_window_check,
            all_cn_years=args.all_cn_years,
        )
    except ValidationError as error:
        print(f"BUILD FAILED: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
