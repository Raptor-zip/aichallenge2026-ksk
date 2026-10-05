#!/usr/bin/env python3
"""Check Markdown image URLs by downloading and decoding the actual image body.

Usage: python3 check_image_urls.py path/to/*.md --report image-check.json
Requires Pillow. HEAD responses alone do not verify image contents.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image


def image_urls(markdown):
    return set(re.findall(r'!\[[^\]]*\]\((https?://[^\s)]+)', markdown)
               + re.findall(r'<img\b[^>]*\bsrc=["\'](https?://[^"\']+)', markdown))


def check(url):
    row = {"url": url, "ok": False}
    try:
        req = Request(url, headers={"User-Agent": "ArticleImageChecker/1.0"})
        with urlopen(req, timeout=20) as response:
            row["status"] = response.status
            row["content_type"] = response.headers.get("Content-Type", "")
            body = response.read(8_000_001)
        row["bytes"] = len(body)
        if len(body) > 8_000_000:
            raise ValueError("Image exceeds the 8 MB article limit")
        if not row["content_type"].split(";")[0].startswith("image/"):
            raise ValueError("Response is not an image: " + body[:160].decode(errors="replace"))
        with Image.open(BytesIO(body)) as im:
            row.update(format=im.format, width=im.width, height=im.height,
                       frames=getattr(im, "n_frames", 1))
            # Decode every frame, including GIFs, rather than trusting just the header.
            for frame in range(row["frames"]):
                im.seek(frame)
                im.load()
        row["ok"] = True
    except HTTPError as exc:
        row.update(status=exc.code, error=exc.read(500).decode(errors="replace"))
    except Exception as exc:
        row["error"] = str(exc)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    owners = {}
    for path in args.files:
        for url in image_urls(path.read_text()):
            owners.setdefault(url, []).append(path.name)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(check, url) for url in sorted(owners)]
        for future in as_completed(futures):
            row = future.result()
            row["articles"] = sorted(owners[row["url"]])
            results.append(row)
            if not row["ok"]:
                print("FAIL", row["url"], row.get("status"), row.get("error"), flush=True)
            if len(results) % 20 == 0:
                print(f"Checked {len(results)}/{len(owners)} images", flush=True)
    # Preserve the first failure and record one concurrent retry for transient errors.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"results": results, "retry_pending": True},
                                     ensure_ascii=False, indent=2) + "\n")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        retries = {pool.submit(check, row["url"]): row for row in results if not row["ok"]}
        for future in as_completed(retries):
            retries[future]["retry"] = future.result()
    failures = [r for r in results if not r["ok"] and not r.get("retry", {}).get("ok")]
    report = {"images": len(results), "initial_failures": sum(not r["ok"] for r in results),
              "remaining_failures": len(failures), "results": sorted(results, key=lambda r: r["url"])}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Images={len(results)}, initial failures={report['initial_failures']}, remaining failures={len(failures)}")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
