#!/bin/bash
# HQ Linux Music Player - Service Startup Verification Script
# 起動チェック スクリプト
# 用途: システム再起動後にサービスが正常に起動したか確認

set -e

echo "======================================"
echo "HQ Linux Music Player - 起動確認"
echo "======================================"
echo ""

BACKEND_PORT=8000
FRONTEND_PORT=3000
MAX_WAIT=30
CHECK_INTERVAL=2

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check service status
check_service() {
    local service=$1
    echo -n "チェック中: $service ... "
    
    if systemctl is-active --quiet "$service"; then
        echo -e "${GREEN}✓ 稼働中${NC}"
        return 0
    else
        echo -e "${RED}✗ 停止中${NC}"
        return 1
    fi
}

# Function to check port connectivity
check_port() {
    local port=$1
    local service=$2
    local url=$3
    
    echo -n "ポート確認: $service (port $port) ... "
    
    local counter=0
    while [ $counter -lt $MAX_WAIT ]; do
        if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port" 2>/dev/null | grep -qE "200|404"; then
            echo -e "${GREEN}✓ 応答確認${NC}"
            return 0
        fi
        
        counter=$((counter + CHECK_INTERVAL))
        if [ $counter -lt $MAX_WAIT ]; then
            sleep $CHECK_INTERVAL
        fi
    done
    
    echo -e "${RED}✗ 接続失敗${NC}"
    return 1
}

# Function to check API connectivity
check_api() {
    echo -n "API確認: バックエンド ... "
    
    if curl -s http://localhost:8000/api/devices 2>/dev/null | grep -q "id"; then
        echo -e "${GREEN}✓ API応答確認${NC}"
        return 0
    else
        echo -e "${RED}✗ API応答なし${NC}"
        return 1
    fi
}

# Main checks
echo "【サービス確認】"
check_service "audiophile-backend.service" || true
check_service "audiophile-frontend.service" || true
check_service "loopback-drain.service" || true

echo ""
echo "【ネットワーク確認】"
check_port $BACKEND_PORT "FastAPI Backend" "http://localhost:8000" || true
check_port $FRONTEND_PORT "Next.js Frontend" "http://localhost:3000" || true

echo ""
echo "【API確認】"
check_api || true

echo ""
echo "======================================"
echo "確認完了"
echo "======================================"
echo ""
echo "ブラウザでアクセス:"
echo "  http://localhost:3000"
echo ""
