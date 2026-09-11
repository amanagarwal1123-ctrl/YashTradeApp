"""Shared PDF fixture validation, media checks, and dry-run reconciliation utility tests."""

import io
import sys
from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageChops, ImageOps

from shared.pdf_parser import CatalogError, analyze_page, thumbnail
sys.path.insert(0, "/app/backend")
from tools.reconcile_identities import report


FIX = Path("/app/backend/fixtures/catalog-v1")


def _mean_abs_diff(a: Image.Image, b: Image.Image) -> float:
    diff = ImageChops.difference(a, b)
    hist = diff.histogram()
    total = 0
    pixels = a.size[0] * a.size[1] * 3
    for i, n in enumerate(hist):
        total += (i % 256) * n
    return total / pixels


@pytest.mark.asyncio
async def test_upload_image_rejects_non_image(api_client, login_helper):
    admin = (await login_helper("9999813334"))["token"]
    data = b"not-an-image"
    files = {"file": ("bad.txt", io.BytesIO(data), "text/plain")}
    r = await api_client.post("/api/products/upload-image", files=files, headers={"Authorization": f"Bearer {admin}"})
    assert r.status_code == 422


def test_sample_pdf_exact_product_codes_and_guide_pages():
    sample = FIX / "sample.pdf"
    rows = []
    rows.extend(analyze_page(str(sample), 0, "template_v1"))
    rows.extend(analyze_page(str(sample), 1, "template_v1"))
    rows.extend(analyze_page(str(sample), 2, "template_v1"))
    rows.extend(analyze_page(str(sample), 3, "template_v1"))

    codes = sorted(r["fields"]["product_code"] for r in rows)
    for row in rows:
        assert Image.open(io.BytesIO(thumbnail(row["image"]))).size == (320, 320)
    assert codes == ["SAMPLE-DIAMOND-001", "SAMPLE-GOLD-001", "SAMPLE-SILVER-001"]
    assert analyze_page(str(sample), 0, "template_v1") == []
    assert analyze_page(str(sample), 3, "template_v1") == []


def test_sample_pdf_crop_pixel_similarity_to_fixture_jpegs():
    sample = FIX / "sample.pdf"
    rows = []
    rows.extend(analyze_page(str(sample), 1, "template_v1"))
    rows.extend(analyze_page(str(sample), 2, "template_v1"))
    by_code = {r["fields"]["product_code"]: r for r in rows}

    mapping = {
        "SAMPLE-SILVER-001": "silver.jpg",
        "SAMPLE-GOLD-001": "gold.jpg",
        "SAMPLE-DIAMOND-001": "diamond.jpg",
    }
    for code, jpg_name in mapping.items():
        parsed = Image.open(io.BytesIO(by_code[code]["image"]))
        source = Image.open(FIX / jpg_name).convert("RGB")
        expected = ImageOps.pad(source, (1024, 1024), color=(245, 245, 245), centering=(0.5, 0.5))
        assert parsed.size == (1024, 1024)
        # Render pipeline may introduce minimal anti-aliasing; keep strict threshold.
        assert _mean_abs_diff(parsed.convert("RGB"), expected) < 8.0


def test_pdf_cropbox_rejected_and_blank_layout_rejected(tmp_path: Path):
    # cropbox unsupported case
    crop_pdf = tmp_path / "cropbox.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.set_cropbox(fitz.Rect(10, 10, 500, 800))
    doc.save(crop_pdf)
    doc.close()
    with pytest.raises(CatalogError):
        analyze_page(str(crop_pdf), 0, "template_v1")

    # blank/unknown layout case
    blank_pdf = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(blank_pdf)
    doc.close()
    with pytest.raises(CatalogError):
        analyze_page(str(blank_pdf), 0, "template_v1")


def test_reconcile_identity_dry_run_contract_owner_admin():
    app_rows = [{"id": "app-owner", "phone": "9999813334", "role": "customer", "account_status": "active"}]
    web_rows = [{"collection": "staff_users", "record_id": "web-1", "phone": "9999813334", "role": "admin"}]
    out = report(app_rows, web_rows, approved_mapping={})
    assert out["dry_run"] is True
    assert out["production_modified"] is False
    proposal = out["proposals"][0]
    assert proposal["canonical_user_id"] == "app-owner"
    assert proposal["target_role"] == "admin"
    assert proposal["apply_allowed"] is False
