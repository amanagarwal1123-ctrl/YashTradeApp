"""One authoring/parser contract. All geometry is unrotated A4 PDF points."""
MM = 72 / 25.4
VERSION = 1
PAGE = (210 * MM, 297 * MM)
SLOTS_MM = [(10, 22, 200, 151), (10, 157, 200, 286)]
MASTER_SIZE = 1024
THUMB_SIZE = 320
FIELDS = [
    ("Product Code", "product_code"), ("Product Name", "title"), ("Product Type", "metal_type"),
    ("Category", "category"), ("Description", "description"), ("Subcategory", "subcategory"),
    ("Metal Weight", "approx_weight"), ("Purity", "purity"), ("Selling Touch", "selling_touch"),
    ("Selling Label", "selling_label"), ("Stock Status", "stock_status"), ("Tags", "tags"),
    ("Video URL", "video_url"), ("Visibility", "visibility"), ("New Arrival", "is_new_arrival"),
    ("Trending", "is_trending"), ("Pinned", "is_pinned"), ("Base Metal", "base_metal"),
    ("Stone Weight ct", "stone_weight_ct"),
]
DEFAULTS = {"stock_status": "in_stock", "visibility": "hidden", "is_new_arrival": True,
            "is_trending": False, "is_pinned": False, "tags": []}


def photo_box(slot):
    _, y, _, _ = SLOTS_MM[slot]
    return [16*MM, (y+20)*MM, 96*MM, (y+100)*MM]


def field_box(slot):
    _, y, _, _ = SLOTS_MM[slot]
    return [102*MM, (y+12)*MM, 196*MM, (y+123)*MM]


def contract():
    return {"version": VERSION, "page_size_mm": [210, 297], "points_per_mm": MM,
            "max_blocks_per_page": 2, "slots_mm": SLOTS_MM,
            "photo_boxes_points": [photo_box(i) for i in range(2)],
            "field_boxes_points": [field_box(i) for i in range(2)],
            "begin_marker_mm": {"x": 12, "offset_y": 6}, "end_marker_mm": {"x": 12, "offset_y": 127},
            "master_pixels": MASTER_SIZE, "thumbnail_pixels": THUMB_SIZE, "fields": dict(FIELDS),
            "defaults": DEFAULTS, "required": ["product_code", "title", "metal_type", "category", "photo"],
            "modes": ["template_v1", "legacy_pages"], "default_visibility": "hidden",
            "cropbox_policy": "full A4 required; rotated pages supported; altered crop boxes rejected with instructions"}