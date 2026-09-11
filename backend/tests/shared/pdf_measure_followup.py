"""Offline follow-up PDF measurements for sample masters/thumbs and compression estimates."""

from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

import sys

sys.path.insert(0, "/app/backend")
from shared.pdf_parser import analyze_page, thumbnail


FIX = Path("/app/backend/fixtures/catalog-v1")
OUT = Path("/app/test_reports/followup_pdf_measurements.json")


def _mae(a: Image.Image, b: Image.Image) -> float:
    diff = ImageChops.difference(a, b)
    hist = diff.histogram()
    total = 0
    pixels = a.size[0] * a.size[1] * 3
    for i, n in enumerate(hist):
        total += (i % 256) * n
    return total / pixels


def _compressed_size(image: Image.Image, fmt: str, **kwargs) -> int:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **kwargs)
    return len(buffer.getvalue())


def main():
    sample = FIX / "sample.pdf"
    rows = analyze_page(str(sample), 1, "template_v1") + analyze_page(str(sample), 2, "template_v1")
    mapping = {
        "SAMPLE-SILVER-001": "silver.jpg",
        "SAMPLE-GOLD-001": "gold.jpg",
        "SAMPLE-DIAMOND-001": "diamond.jpg",
    }

    per_row = []
    masters_png_total = 0
    thumbs_png_total = 0
    masters_jpeg92_total = 0
    masters_webp92_total = 0
    thumbs_jpeg92_total = 0
    thumbs_webp92_total = 0
    maes = []

    for row in rows:
        code = row["fields"]["product_code"]
        parsed = Image.open(io.BytesIO(row["image"])).convert("RGB")
        thumb_img = Image.open(io.BytesIO(thumbnail(row["image"]))).convert("RGB")
        source = Image.open(FIX / mapping[code]).convert("RGB")
        expected = ImageOps.pad(source, (1024, 1024), color=(245, 245, 245), centering=(0.5, 0.5))
        mae = _mae(parsed, expected)
        maes.append(mae)

        master_png_bytes = len(row["image"])
        thumb_png_bytes = len(thumbnail(row["image"]))
        master_jpeg92 = _compressed_size(parsed, "JPEG", quality=92)
        master_webp92 = _compressed_size(parsed, "WEBP", quality=92)
        thumb_jpeg92 = _compressed_size(thumb_img, "JPEG", quality=92)
        thumb_webp92 = _compressed_size(thumb_img, "WEBP", quality=92)

        masters_png_total += master_png_bytes
        thumbs_png_total += thumb_png_bytes
        masters_jpeg92_total += master_jpeg92
        masters_webp92_total += master_webp92
        thumbs_jpeg92_total += thumb_jpeg92
        thumbs_webp92_total += thumb_webp92

        per_row.append(
            {
                "product_code": code,
                "source_fixture": str((FIX / mapping[code]).resolve()),
                "errors_count": len(row.get("errors", [])),
                "master_png_bytes": master_png_bytes,
                "thumb_png_bytes": thumb_png_bytes,
                "master_size": list(parsed.size),
                "thumb_size": list(thumb_img.size),
                "mae": round(mae, 4),
                "jpeg92_master_bytes": master_jpeg92,
                "webp92_master_bytes": master_webp92,
                "jpeg92_thumb_bytes": thumb_jpeg92,
                "webp92_thumb_bytes": thumb_webp92,
            }
        )

    report = {
        "scope": "offline-only; originals unchanged; no uploads",
        "counts": {
            "masters_png": len(rows),
            "thumbs_png": len(rows),
            "errors_total": sum(len(r.get("errors", [])) for r in rows),
            "expected_master_size": [1024, 1024],
            "expected_thumb_size": [320, 320],
        },
        "aggregate_bytes": {
            "png_masters": masters_png_total,
            "png_thumbs": thumbs_png_total,
            "png_total": masters_png_total + thumbs_png_total,
            "jpeg92_masters": masters_jpeg92_total,
            "webp92_masters": masters_webp92_total,
            "jpeg92_thumbs": thumbs_jpeg92_total,
            "webp92_thumbs": thumbs_webp92_total,
            "jpeg92_total_estimate": masters_jpeg92_total + thumbs_jpeg92_total,
            "webp92_total_estimate": masters_webp92_total + thumbs_webp92_total,
        },
        "crop_quality": {
            "mae_mean": round(sum(maes) / len(maes), 4) if maes else None,
            "mae_max": round(max(maes), 4) if maes else None,
        },
        "rows": per_row,
    }

    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps({"report": str(OUT), "rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
