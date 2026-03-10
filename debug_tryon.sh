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

# Create test image
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

echo "Testing AI Try-On API..."
echo "Product ID: $PRODUCT_ID"

# Call API and show full response
RESPONSE=$(curl -s -X POST "$API_URL/api/ai/try-on" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"product_id\":\"$PRODUCT_ID\",\"user_photo_base64\":\"$TEST_B64\",\"body_area\":\"neck\",\"scale\":0.45,\"offset_x\":0.5,\"offset_y\":0.25}")

echo "Full Response:"
echo "$RESPONSE"
echo

# Parse specific fields
echo "Parsed fields:"
echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'image_url: {data.get(\"image_url\", \"MISSING\")}')
    print(f'image_base64 length: {len(data.get(\"image_base64\", \"\"))} chars')
    print(f'method: {data.get(\"method\", \"MISSING\")}')
    print(f'body_area: {data.get(\"body_area\", \"MISSING\")}')
    print(f'product_id: {data.get(\"product_id\", \"MISSING\")}')
except Exception as e:
    print(f'Error parsing JSON: {e}')
"
