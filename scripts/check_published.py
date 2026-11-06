"""校验 GitHub Pages / jsDelivr / raw 实际返回的数据。

可以发现 Pages 配置错误或只部署了一半的 manifest。部署后运行，或定时运行：

    python -m scripts.check_published --base-url https://<user>.github.io/holiday-data/v1
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urljoin

from . import validate
from .common import ValidationError, http_get, sha256_bytes


def check(base_url: str) -> None:
    base_url = base_url.rstrip("/") + "/"
    manifest_url = urljoin(base_url, "manifest.json")
    manifest = json.loads(http_get(manifest_url))
    validate.validate_manifest(manifest, root=None)  # type: ignore[arg-type]

    for relative, entry in sorted(manifest["files"].items()):
        url = urljoin(base_url, relative)
        content = http_get(url)
        digest = sha256_bytes(content)
        if digest != entry["sha256"]:
            raise ValidationError(
                f"{relative}: sha256 mismatch (manifest {entry['sha256']}, got {digest})"
            )
        document = json.loads(content)
        if relative.startswith("jp/"):
            validate.validate_jp(document)
        elif relative.startswith("cn/"):
            validate.validate_cn(document)
        else:
            raise ValidationError(f"unexpected remote file: {relative}")

    print(
        f"OK: {manifest_url} dataVersion={manifest['dataVersion']} "
        f"files={len(manifest['files'])}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    try:
        check(args.base_url)
    except (ValidationError, OSError, ValueError) as error:
        print(f"SMOKE TEST FAILED: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
