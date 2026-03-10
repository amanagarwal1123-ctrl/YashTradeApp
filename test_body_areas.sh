#!/bin/bash

API_URL="https://yash-tryon-test.preview.emergentagent.com"

# Login
TOKEN=$(curl -s -X POST "$API_URL/api/auth/verify-otp" \
  -H "Content-Type: application/json" \
  -d '{"phone":"8888888888","otp":"1234"}' | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# Get product ID
PRODUCT_ID=$(curl -s "$API_URL/api/products?limit=1" \
  -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['products'][0]['id'])")

# Test image
TEST_B64=$(python3 -c "
import base64
from PIL import Image, ImageDraw
import io
img = Image.new('RGB', (400, 500), (200, 180, 160))
draw = ImageDraw.Draw(img)
draw.ellipse([150, 50, 250, 170], fill=(230, 200, 170))
draw.rectangle([180, 170, 220, 220], fill=(230, 200, 170))
draw.rectangle([130, 220, 270, 400], fill=(100, 120, 140))
buf = io.BytesIO()
img.save(buf, 'JPEG', quality=80)
print(base64.b64encode(buf.getvalue()).decode())
")

echo "=== TESTING DIFFERENT BODY AREAS ==="

# Test different body areas
BODY_AREAS=("neck" "ear" "wrist" "ankle" "finger" "auto")

for area in "${BODY_AREAS[@]}"; do
  echo "Testing body area: $area"
  RESPONSE=$(curl -s -X POST "$API_URL/api/ai/try-on" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"product_id\":\"$PRODUCT_ID\",\"user_photo_base64\":\"$TEST_B64\",\"body_area\":\"$area\",\"scale\":0.45,\"offset_x\":0.5,\"offset_y\":0.25}")
  
  # Parse response
  DETECTED_AREA=$(echo "$RESPONSE" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('body_area', 'N/A'))" 2>/dev/null)
  METHOD=$(echo "$RESPONSE" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('method', 'N/A'))" 2>/dev/null)
  
  echo "  → Detected area: $DETECTED_AREA, Method: $METHOD"
done

echo "=== BODY AREAS TEST COMPLETE ==="
