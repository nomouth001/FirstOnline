#!/bin/bash

# AWS Lightsail 배포 스크립트 (데이터베이스 동기화 포함)
# 사용법: ./deploy_with_sync.sh [--sync-from-local|--sync-from-remote|--compare-only]

echo "🚀 AWS Lightsail 배포 시작 (DB 동기화)..."

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 옵션 파싱
SYNC_OPTION=""
COMPARE_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --sync-from-local)
            SYNC_OPTION="sync-to-remote"
            shift
            ;;
        --sync-from-remote)
            SYNC_OPTION="sync-to-local"
            shift
            ;;
        --compare-only)
            COMPARE_ONLY=true
            shift
            ;;
        *)
            echo "알 수 없는 옵션: $1"
            echo "사용법: $0 [--sync-from-local|--sync-from-remote|--compare-only]"
            exit 1
            ;;
    esac
done

# 에러 발생 시 스크립트 중단
set -e

# 0. 데이터베이스 비교 (항상 실행)
echo -e "${BLUE}📊 데이터베이스 상태 확인 중...${NC}"
if python utils/db_sync.py compare; then
    echo -e "${GREEN}✅ 데이터베이스 비교 완료${NC}"
else
    echo -e "${YELLOW}⚠️ 데이터베이스 비교 중 오류 발생 (계속 진행)${NC}"
fi

# 비교만 수행하고 종료
if [ "$COMPARE_ONLY" = true ]; then
    echo -e "${BLUE}ℹ️ 비교만 수행하고 종료합니다.${NC}"
    exit 0
fi

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
    echo -e "${YELLOW}⚠️ 가상환경이 없습니다. 가상환경 활성화를 건너뜁니다.${NC}"
fi

# 3. 의존성 업데이트
echo -e "${BLUE}▶️ 3. 의존성 업데이트 중...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}✅ 의존성 업데이트 완료${NC}"

# 4. 데이터베이스 동기화
echo -e "${BLUE}▶️ 4. 데이터베이스 동기화 작업...${NC}"
if [ ! -z "$SYNC_OPTION" ]; then
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_file="backup_pre_deploy_${timestamp}.json"
    
    if python utils/db_sync.py export --file "$backup_file"; then
        echo -e "${GREEN}✅ 배포 전 백업 완료: $backup_file${NC}"
    else
        echo -e "${RED}❌ 배포 전 백업 실패${NC}"
        exit 1
    fi
    
    if python utils/db_sync.py "$SYNC_OPTION"; then
        echo -e "${GREEN}✅ 데이터베이스 동기화 완료${NC}"
    else
        echo -e "${RED}❌ 데이터베이스 동기화 실패${NC}"
        exit 1
    fi
else
    echo -e "${BLUE}ℹ️ 데이터베이스 동기화 생략 (옵션 없음)${NC}"
fi

# 5. 서비스 재시작 (Gunicorn, Celery)
echo -e "${BLUE}▶️ 5. 핵심 서비스 재시작 중...${NC}"
sudo systemctl restart newsletter
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat
echo -e "${GREEN}✅ 핵심 서비스(Gunicorn, Celery) 재시작 완료${NC}"

# 6. Nginx 재시작
echo -e "${BLUE}▶️ 6. Nginx 재시작 중...${NC}"
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
    fi
else
    echo -e "${YELLOW}⚠️ Nginx 설정 파일을 찾을 수 없어 재시작을 건너뜁니다: $NGINX_CONFIG_FILE${NC}"
        fi

echo -e "\n${GREEN}🎉 배포 완료!${NC}"
echo -e "${YELLOW}📝 사용 가능한 명령어:${NC}"
echo -e "${YELLOW}  로그 확인: tail -f logs/app.log${NC}"
echo -e "${YELLOW}  서비스 상태: systemctl status newsletter${NC}"
echo -e "${YELLOW}  DB 비교: python utils/db_sync.py compare${NC}"
echo -e "${YELLOW}  DB 동기화: python utils/db_sync.py [sync-to-remote|sync-to-local]${NC}" 