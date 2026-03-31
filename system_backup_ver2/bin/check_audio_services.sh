#!/bin/bash
# HQ Linux Music Player - 起動確認スクリプト

echo "======================================"
echo "HQ Linux Music Player - 起動確認テスト"
echo "======================================"
echo ""

# 色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# カウンター
PASSED=0
FAILED=0

# 1. loopback-drain チェック
echo -n "1. loopback-drain.service ... "
if systemctl is-active --quiet loopback-drain.service; then
    echo -e "${GREEN}✓ ACTIVE${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ INACTIVE${NC}"
    ((FAILED++))
fi

# 2. audiophile-backend チェック
echo -n "2. audiophile-backend.service ... "
if systemctl is-active --quiet audiophile-backend.service; then
    echo -e "${GREEN}✓ ACTIVE${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ INACTIVE${NC}"
    ((FAILED++))
fi

# 3. audiophile-frontend チェック
echo -n "3. audiophile-frontend.service ... "
if systemctl is-active --quiet audiophile-frontend.service; then
    echo -e "${GREEN}✓ ACTIVE${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ INACTIVE${NC}"
    ((FAILED++))
fi

echo ""
echo "ポート確認:"
echo ""

# 4. ポート 8000 チェック
echo -n "4. Backend port 8000 ... "
if ss -tlnp 2>/dev/null | grep -q ":8000 "; then
    echo -e "${GREEN}✓ LISTENING${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ NOT LISTENING${NC}"
    ((FAILED++))
fi

# 5. ポート 3000 チェック
echo -n "5. Frontend port 3000 ... "
if ss -tlnp 2>/dev/null | grep -q ":3000 "; then
    echo -e "${GREEN}✓ LISTENING${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ NOT LISTENING${NC}"
    ((FAILED++))
fi

echo ""
echo "接続確認:"
echo ""

# 6. Backend API チェック
echo -n "6. Backend API (/api/devices) ... "
if curl -s http://localhost:8000/api/devices 2>/dev/null | grep -q "bluealsa"; then
    echo -e "${GREEN}✓ OK${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC}"
    ((FAILED++))
fi

# 7. Frontend HTML チェック
echo -n "7. Frontend HTML (port 3000) ... "
if curl -s http://localhost:3000 2>/dev/null | grep -q "<title>"; then
    echo -e "${GREEN}✓ OK${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC}"
    ((FAILED++))
fi

echo ""
echo "======================================"
echo "結果: ${GREEN}${PASSED} 成功${NC} / ${RED}${FAILED} 失敗${NC}"
echo "======================================"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ すべてのチェックに成功しました！${NC}"
    echo ""
    echo "ブラウザでアクセス:"
    echo "  http://localhost:3000"
    echo ""
    exit 0
else
    echo -e "${RED}✗ いくつかのチェックが失敗しました${NC}"
    echo ""
    echo "トラブルシューティング:"
    echo "  1. ログを確認: journalctl -u audiophile-backend.service -n 50"
    echo "  2. サービスを再起動: systemctl restart audiophile-backend.service"
    echo ""
    exit 1
fi
