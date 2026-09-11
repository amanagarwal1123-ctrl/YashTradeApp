"""Generate and benchmark a 60-product template PDF with production generator/parser."""

import json
import resource
import time
from pathlib import Path

import fitz

import sys
sys.path.insert(0, "/app/backend")

from tools.generate_catalog import generate
from shared.pdf_parser import analyze_page


FIX = Path("/app/backend/fixtures/catalog-v1")
OUT = Path("/app/test_reports")


def build_authoring(path: Path):
    photos = [
        "../backend/fixtures/catalog-v1/silver.jpg",
        "../backend/fixtures/catalog-v1/gold.jpg",
        "../backend/fixtures/catalog-v1/diamond.jpg",
    ]
    products = []
    for i in range(60):
        metal = ["silver", "gold", "diamond"][i % 3]
        code = f"BENCH-{metal[:1].upper()}-{i:03d}"
        products.append({
            "product_code": code,
            "title": f"Benchmark Product {i}",
            "metal_type": metal,
            "category": "chain" if metal != "diamond" else "ring",
            "description": "Synthetic benchmark fixture",
            "subcategory": "daily",
            "approx_weight": "10-12 g",
            "purity": "925" if metal == "silver" else "22K" if metal == "gold" else "22K",
            "base_metal": "gold" if metal == "diamond" else "",
            "selling_touch": "92.5",
            "selling_label": "Benchmark",
            "stock_status": "in_stock",
            "tags": ["bench", metal],
            "visibility": "hidden",
            "is_new_arrival": True,
            "is_trending": False,
            "is_pinned": False,
            "photo": photos[i % len(photos)],
        })
    path.write_text(json.dumps({"products": products}, indent=2))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    authoring = OUT / "benchmark_authoring_60.json"
    pdf = OUT / "benchmark_catalog_60.pdf"
    build_authoring(authoring)
    generate(authoring, pdf)

    start = time.perf_counter()
    rows = []
    with fitz.open(pdf) as doc:
        pages = len(doc)
    for page in range(pages):
        rows.extend(analyze_page(str(pdf), page, "template_v1"))
    elapsed = time.perf_counter() - start
    max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    report = {
        "pdf_path": str(pdf),
        "bytes": pdf.stat().st_size,
        "pages": pages,
        "products": len(rows),
        "elapsed_seconds": round(elapsed, 3),
        "peak_rss_kb": int(max_rss_kb),
    }
    out_json = OUT / "pdf_benchmark_iter12.json"
    out_json.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
