import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

sys.path.insert(0, "/app/backend")
from shared.pdf_parser import analyze_page


FIX = Path("/app/backend/fixtures/catalog-v1")


def mean_abs_diff(a: Image.Image, b: Image.Image) -> float:
    diff = ImageChops.difference(a, b)
    hist = diff.histogram()
    total = 0
    pixels = a.size[0] * a.size[1] * 3
    for i, n in enumerate(hist):
        total += (i % 256) * n
    return total / pixels


def main():
    sample = FIX / "sample.pdf"
    evidence_dir = Path("/app/test_reports/pdf_crops")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    rows.extend(analyze_page(str(sample), 1, "template_v1"))
    rows.extend(analyze_page(str(sample), 2, "template_v1"))
    by_code = {r["fields"]["product_code"]: r for r in rows}

    mapping = {
        "SAMPLE-SILVER-001": "silver.jpg",
        "SAMPLE-GOLD-001": "gold.jpg",
        "SAMPLE-DIAMOND-001": "diamond.jpg",
    }

    out = []
    for code, jpg in mapping.items():
        parsed = Image.open(io.BytesIO(by_code[code]["image"])).convert("RGB")
        source = Image.open(FIX / jpg).convert("RGB")
        expected = ImageOps.pad(source, (1024, 1024), color=(245, 245, 245), centering=(0.5, 0.5))
        out.append(
            {
                "code": code,
                "parsed_size": list(parsed.size),
                "expected_size": list(expected.size),
                "mean_abs_diff": round(mean_abs_diff(parsed, expected), 4),
                "parsed_crop": str((evidence_dir / f"{code}-parsed.png").resolve()),
                "expected_crop": str((evidence_dir / f"{code}-expected.png").resolve()),
            }
        )
        parsed.save(evidence_dir / f"{code}-parsed.png")
        expected.save(evidence_dir / f"{code}-expected.png")

    print(json.dumps({"rows": out}, indent=2))


if __name__ == "__main__":
    main()
