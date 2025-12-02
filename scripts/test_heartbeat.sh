#!/bin/bash
# Quick Heartbeat Test Script

# Load .env
source .env

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 GrowDash Heartbeat Test"
echo "=========================="
echo ""
echo "Device-ID: $DEVICE_PUBLIC_ID"
echo "Token: ${DEVICE_TOKEN:0:8}..."
echo ""

# Test heartbeat endpoint
echo "Sende Heartbeat..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  https://grow.linn.games/api/growdash/agent/heartbeat \
  -H "X-Device-ID: $DEVICE_PUBLIC_ID" \
  -H "X-Device-Token: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "last_state": {
      "uptime": 123,
      "test": true
    }
  }')

# Extract HTTP status code (last line)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

echo ""
echo "HTTP Status: $HTTP_CODE"
echo "Response Body:"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

# Evaluate result
case $HTTP_CODE in
  200)
    echo -e "${GREEN}✅ Heartbeat erfolgreich!${NC}"
    exit 0
    ;;
  401)
    echo -e "${RED}❌ Authentication failed (401)${NC}"
    echo "Prüfe Device-Token in .env vs. Laravel-DB (SHA256-Hash)"
    exit 1
    ;;
  404)
    echo -e "${RED}❌ Route nicht gefunden (404)${NC}"
    echo "Laravel-Backend fehlt Route:"
    echo "  Route::middleware('device.auth')->prefix('growdash/agent')->group(function () {"
    echo "    Route::post('/heartbeat', [AgentController::class, 'heartbeat']);"
    echo "  });"
    exit 1
    ;;
  500)
    echo -e "${RED}❌ Server Error (500)${NC}"
    echo "Prüfe Laravel Logs: tail -f storage/logs/laravel.log"
    exit 1
    ;;
  *)
    echo -e "${YELLOW}⚠️ Unerwarteter Status: $HTTP_CODE${NC}"
    exit 1
    ;;
esac
