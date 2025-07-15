#!/bin/bash

# AWS Lightsail 안전 배포 스크립트
# 사용법: ./deploy_safe.sh

echo "🚀 AWS Lightsail 안전 배포 시작..."

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 에러 발생 시 스크립트 중단
set -e

# 1. 최신 코드 가져오기
echo -e "${BLUE}▶️ 1. GitHub에서 최신 코드 가져오는 중...${NC}"
git fetch origin main
git reset --hard origin/main
echo -e "${GREEN}✅ 코드 업데이트 완료${NC}"

# 2. 가상환경 활성화
echo -e "${BLUE}▶️ 2. 가상환경 활성화 중...${NC}"
if [ -d "venv" ]; then
    source venv/bin/activate
    echo -e "${GREEN}✅ 가상환경 활성화 완료${NC}"
else
    echo -e "${RED}❌ venv 디렉토리를 찾을 수 없습니다.${NC}"
    exit 1
fi

# 3. 의존성 업데이트
echo -e "${BLUE}▶️ 3. 의존성 업데이트 중...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}✅ 의존성 업데이트 완료${NC}"

# 4. 데이터베이스 마이그레이션
echo -e "${BLUE}▶️ 4. 데이터베이스 업데이트 중...${NC}"
python init_db.py
echo -e "${GREEN}✅ 데이터베이스 업데이트 완료${NC}"

# 5. 정적 파일 폴더 확인
echo -e "${BLUE}▶️ 5. 정적 파일 폴더 확인 중...${NC}"
mkdir -p static/charts static/analysis static/summaries static/debug static/memos static/multi_summaries
echo -e "${GREEN}✅ 정적 파일 폴더 확인 완료${NC}"

# 6. 서비스 재시작 (Gunicorn, Celery)
echo -e "${BLUE}▶️ 6. 핵심 서비스 재시작 중...${NC}"
sudo systemctl restart newsletter
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat
echo -e "${GREEN}✅ 핵심 서비스(Gunicorn, Celery) 재시작 완료${NC}"

# 7. Nginx 재시작
echo -e "${BLUE}▶️ 7. Nginx 재시작 중...${NC}"
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_CONFIG_FILE="$NGINX_SITES_AVAILABLE/whatsnextstock.com"

if [ -f "$NGINX_CONFIG_FILE" ]; then
    echo -e "${YELLOW}🧪 Nginx 설정 테스트 중...${NC}"
    if sudo nginx -t; then
        echo -e "${GREEN}✅ Nginx 설정 테스트 통과${NC}"
        sudo systemctl restart nginx
        echo -e "${GREEN}✅ Nginx 재시작 완료${NC}"
    else
        echo -e "${RED}❌ Nginx 설정 테스트 실패. Nginx를 재시작하지 않습니다.${NC}"
        echo -e "${YELLOW}   문제가 발생하면 수동으로 확인하세요: sudo nginx -t${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ Nginx 설정 파일을 찾을 수 없어 재시작을 건너뜁니다: $NGINX_CONFIG_FILE${NC}"
fi

# 8. Nginx 설정 확인 및 재시작
if [ -d "$NGINX_SITES_AVAILABLE" ]; then
    echo -e "${BLUE}▶️ Nginx 설정 처리 시작...${NC}"
    NGINX_CONFIG_FILE="$NGINX_SITES_AVAILABLE/whatsnextstock.com"

    if [ -f "$NGINX_CONFIG_FILE" ]; then
        echo -e "${YELLOW}🔍 Nginx 설정 파일 감지: $NGINX_CONFIG_FILE${NC}"
        
        echo -e "${YELLOW}🧪 Nginx 설정 테스트 중...${NC}"
        if sudo nginx -t; then
            echo -e "${GREEN}✅ Nginx 설정 테스트 통과${NC}"
            echo -e "${YELLOW}🔄 Nginx 서비스 재시작 중...${NC}"
            sudo systemctl restart nginx
            echo -e "${GREEN}✅ Nginx 재시작 완료${NC}"
        else
            echo -e "${RED}❌ Nginx 설정 테스트 실패. 서비스를 재시작하지 않습니다.${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️ Nginx 설정 파일($NGINX_CONFIG_FILE)을 찾을 수 없습니다. Nginx 재시작을 건너뜁니다.${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ Nginx 설정 디렉토리($NGINX_SITES_AVAILABLE)를 찾을 수 없습니다. Nginx 재시작을 건너뜁니다.${NC}"
fi


echo -e "\n${GREEN}🎉 배포 완료!${NC}"
echo -e "   - ${YELLOW}Gunicorn, Celery, Nginx 서비스가 재시작되었습니다.${NC}"
echo -e "   - ${YELLOW}서비스 상태 확인: sudo systemctl status newsletter celery-worker celery-beat nginx${NC}" 