"""Editable JSON -> production template PDF. No template-only parser or live publication.
Run: python tools/generate_catalog.py --input fixtures/catalog-v1/authoring.json --output fixtures/catalog-v1/sample.pdf
Photos are local paths (relative to input file); remote URLs are NOT fetched by the generator.
"""
import argparse
import io
import json
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.pdf_schema import FIELDS, MM, PAGE, SLOTS_MM, VERSION, field_box, photo_box, contract


def header(page, role):
    page.insert_text((10*MM, 9*MM), f"YASH_CATALOG_TEMPLATE_VERSION: {VERSION}", fontsize=9)
    page.insert_text((10*MM, 15*MM), f"YASH_PAGE_ROLE: {role}", fontsize=9)


def text(page, rectangle, message, size=10):
    unused = page.insert_textbox(fitz.Rect(rectangle), message, fontsize=size, lineheight=1.4)
    if unused < 0:
        raise ValueError("Text does not fit its block; shorten it or use the editable JSON template")


def guide(doc):
    page = doc.new_page(width=PAGE[0], height=PAGE[1]); header(page, "GUIDE")
    text(page, [12*MM, 25*MM, 198*MM, 284*MM],
        "YASH ORNAMENTS | CATALOG AUTHORING GUIDE\n\n"
        "Illustrative sample products only. Import analysis NEVER publishes these examples.\n\n"
        "In the app, open Products > Add Product / Create Catalogue. Fill labelled fields, choose photos, add entries and Export version 1 PDF. "
        "Advanced users may use companion authoring.json and generate_catalog.py. "
        "Do not edit or move the frame geometry in a PDF editor.\n\n"
        "Required: Product Code (unique SKU), Product Name, Product Type, Category and one valid photograph. "
        "Product Type is gold, silver or diamond for EACH block; a batch may mix all three.\n\n"
        "Product boundaries: paired YASH_PRODUCT_BEGIN:<code> and YASH_PRODUCT_END:<code> markers. "
        "Markers must match Product Code. Maximum two blocks per page; never split a block between pages. "
        "This GUIDE page, including these marker examples, is not a product.\n\n"
        "Photo: one centered, fully visible jewellery photograph on a neutral background. Recommended embedded JPG/PNG at least "
        "1024 x 1024 pixels. Rectangular/tall photos are contained with neutral padding, NEVER stretched or trimmed. "
        "Keep text, frame strokes, labels, logos and other products OUTSIDE the 80 mm square photo interior. "
        "Output master: 1024 x 1024; thumbnail: 320 x 320. Low resolution is flagged, not repaired by upscaling.\n\n"
        "Geometry: A4 210 x 297 mm. Outer blocks (x0,y0,x1,y1) = (10,22,200,151) and (10,157,200,286) mm. "
        "Photo x=16..96 mm; y=block top+20..100 mm. Text x=102..196 mm. Markers at x=12 mm, y=top+6 and top+127 mm. "
        "Gap: 6 mm. 1 mm = 72/25.4 PDF points. Crop excludes the frame stroke outside the square.\n\n"
        "Weight: metal grams, e.g. 12.5 g, 10-12 g or 25-35 g per pair; positive ascending ranges only. Stone Weight ct is a separate "
        "positive carat number, not metal weight. Diamond is a product classification, not metal purity. "
        "If specifying purity for diamond jewellery also specify Base Metal.\n\n"
        "Use template_v1 mode. Supplier/scanned PDFs require explicit legacy_pages mode and manual correction/review. "
        "No OCR is implemented. Export full A4 pages: rotations are supported but cropped page boxes are rejected. "
        "Never assume failed template parsing will silently become a page import.\n\n"
        "Next: upload > analyze > review square crops and fields > exclude/fix rows > decide Skip or Update Existing > "
        "confirm import as hidden drafts. Publishing is a separate explicit selection.", size=10)


def generate(source, destination):
    source, destination = Path(source), Path(destination)
    products = json.loads(source.read_text())["products"]
    doc = fitz.open(); guide(doc)
    manifest = {"template": contract(), "products": []}
    page = None
    for index, entry in enumerate(products):
        slot = index % 2
        if slot == 0:
            page = doc.new_page(width=PAGE[0], height=PAGE[1]); header(page, "PRODUCTS")
        _, y, _, bottom = SLOTS_MM[slot]
        code = entry["product_code"]
        page.draw_rect(fitz.Rect(10*MM, y*MM, 200*MM, bottom*MM), width=0.7, color=(0.3, 0.3, 0.3))
        page.insert_text((12*MM, (y+6)*MM), f"YASH_PRODUCT_BEGIN:{code}", fontsize=8)
        page.insert_text((12*MM, (y+127)*MM), f"YASH_PRODUCT_END:{code}", fontsize=8)
        rect = fitz.Rect(photo_box(slot))
        page.draw_rect(rect + (-1, -1, 1, 1), color=(0.4, 0.4, 0.4), width=0.5)
        page.insert_text((16*MM, (y+17)*MM), "PHOTO INTERIOR - NO TEXT OR FRAME INSIDE", fontsize=6)
        with Image.open(source.parent / entry["photo"]) as image:
            square = ImageOps.pad(image.convert("RGB"), (1024, 1024), color=(245, 245, 245), centering=(0.5, 0.5))
            data = io.BytesIO(); square.save(data, "PNG")
        page.insert_image(rect, stream=data.getvalue())
        lines = []
        for label, key in FIELDS:
            value = entry.get(key, "")
            if isinstance(value, bool):
                value = str(value).lower()
            elif isinstance(value, list):
                value = ", ".join(value)
            lines.append(f"{label}: {value}")
        text(page, field_box(slot), "\n".join(lines), size=8)
        manifest["products"].append({"product_code": code, "page": len(doc), "slot": slot,
            "crop_points": photo_box(slot), "fields": {k: v for k, v in entry.items() if k != "photo"}, "photo": entry["photo"]})
    page = doc.new_page(width=PAGE[0], height=PAGE[1]); header(page, "GUIDE")
    refs = ["FIELD REFERENCE | BLANK OPTIONAL VALUES ARE ALLOWED", ""]
    descriptions = {"product_code": "required, unique case-sensitive SKU, 1-64 letters/digits/dot/hyphen/underscore",
        "title": "required product display name", "metal_type": "required: silver, gold, diamond",
        "category": "required existing catalog category", "approx_weight": "optional metal grams: 12.5 g or 10-12 g",
        "purity": "optional silver 925 / 92.5%; gold 22K / 18K; requires base metal for diamond",
        "selling_touch": "optional numeric percentage, e.g. 92.5 or 92.5%", "selling_label": "optional free text; no invented price",
        "stock_status": "in_stock, limited, out_of_stock; blank = in_stock", "tags": "comma-separated; blank = []",
        "video_url": "optional HTTPS YouTube/Vimeo link, never fetched by parser", "visibility": "all or hidden; blank = hidden; commit defaults hidden",
        "is_new_arrival": "true/false; blank = true", "is_trending": "true/false; blank = false", "is_pinned": "true/false; blank = false",
        "base_metal": "optional gold/silver/platinum; conditional when diamond purity supplied",
        "stone_weight_ct": "optional positive number of carats, separate from metal grams"}
    for label, key in FIELDS:
        refs.append(f"{label} -> {key}: {descriptions.get(key, 'optional free text; blank remains blank')}")
    refs.extend(["", "No price column is required. Existing schema does not calculate product prices during PDF import.",
        "Additional images: upload through permanent product-media endpoint after import, not PDF image URLs.",
        "Long text may wrap inside its field column. Generator refuses overflow. Keep every product inside its boundary.",
        "Sample photographs are generated illustrative assets, not claims about actual inventory or purity."])
    text(page, [12*MM, 25*MM, 198*MM, 284*MM], "\n\n".join(refs), size=9)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destination, garbage=4, deflate=True); doc.close()
    destination.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--input", required=True); p.add_argument("--output", required=True)
    args = p.parse_args(); generate(args.input, args.output)