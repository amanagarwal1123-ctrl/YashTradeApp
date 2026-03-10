#!/bin/bash

API_URL="https://yash-tryon-test.preview.emergentagent.com"

echo "=== YASH TRADE VIRTUAL TRY-ON CURL TESTING ==="
echo "API URL: $API_URL"
echo

# Step 1: Login
echo "Step 1: Login with phone 8888888888, OTP 1234..."
TOKEN=$(curl -s -X POST "$API_URL/api/auth/verify-otp" \
  -H "Content-Type: application/json" \
  -d '{"phone":"8888888888","otp":"1234"}' | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['token'])" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Failed to get authentication token"
  exit 1
else
  echo "✅ Authentication successful, token obtained"
fi

# Step 2: Get a product ID
echo "Step 2: Get a product ID..."
PRODUCT_ID=$(curl -s "$API_URL/api/products?limit=1" \
  -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['products'][0]['id'])" 2>/dev/null)

if [ -z "$PRODUCT_ID" ]; then
  echo "❌ Failed to get product ID"
  exit 1
else
  echo "✅ Product ID obtained: $PRODUCT_ID"
fi

# Step 3: Create a small test image (base64)
echo "Step 3: Create test image in base64..."
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

echo "✅ Test image created (${#TEST_B64} chars)"

# Step 4: Call try-on API
echo "Step 4: Call try-on API..."
RESPONSE=$(curl -s -X POST "$API_URL/api/ai/try-on" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"product_id\":\"$PRODUCT_ID\",\"user_photo_base64\":\"$TEST_B64\",\"body_area\":\"neck\",\"scale\":0.45,\"offset_x\":0.5,\"offset_y\":0.25}")

echo "Response received:"
echo "$RESPONSE" | python3 -c "import sys,json;r=json.load(sys.stdin);print(f'✅ Success! image_url: {r.get(\"image_url\", \"N/A\")}, method: {r.get(\"method\", \"N/A\")}')" 2>/dev/null || echo "❌ Failed to parse response: $RESPONSE"

echo
echo "=== CURL TEST COMPLETE ==="
