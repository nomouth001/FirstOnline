#!/bin/bash

# AWS Lightsail 배포 스크립트 (데이터베이스 동기화 포함)
# 사용법: ./deploy_with_sync.sh [--sync-from-local|--sync-from-remote|--compare-only]

echo "🚀 AWS Lightsail 배포 시작 (데이터베이스 동기화 포함)..."

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

# 1. 데이터베이스 동기화 (옵션에 따라)
if [ ! -z "$SYNC_OPTION" ]; then
    echo -e "${YELLOW}🔄 데이터베이스 동기화 시작: $SYNC_OPTION${NC}"
    
    # 동기화 전 백업
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_file="backup_pre_deploy_${timestamp}.json"
    
    if python utils/db_sync.py export --file "$backup_file"; then
        echo -e "${GREEN}✅ 배포 전 백업 완료: $backup_file${NC}"
    else
        echo -e "${RED}❌ 배포 전 백업 실패${NC}"
        exit 1
    fi
    
    # 동기화 실행
    if python utils/db_sync.py "$SYNC_OPTION"; then
        echo -e "${GREEN}✅ 데이터베이스 동기화 완료${NC}"
    else
        echo -e "${RED}❌ 데이터베이스 동기화 실패${NC}"
        exit 1
    fi
else
    echo -e "${BLUE}ℹ️ 데이터베이스 동기화 생략 (옵션 없음)${NC}"
fi

# 2. 최신 코드 가져오기
echo -e "${YELLOW}📥 GitHub에서 최신 코드 가져오는 중...${NC}"
git fetch origin
git reset --hard origin/main
echo -e "${GREEN}✅ 코드 업데이트 완료${NC}"

# 3. 가상환경 활성화 (있는 경우)
if [ -d "venv" ]; then
    echo -e "${YELLOW}🔧 가상환경 활성화 중...${NC}"
    source venv/bin/activate
    echo -e "${GREEN}✅ 가상환경 활성화 완료${NC}"
fi

# 4. 의존성 업데이트
echo -e "${YELLOW}📦 의존성 업데이트 중...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}✅ 의존성 업데이트 완료${NC}"

# 5. 데이터베이스 마이그레이션 (동기화를 했다면 스킵)
if [ -z "$SYNC_OPTION" ]; then
    echo -e "${YELLOW}🗄️ 데이터베이스 업데이트 중...${NC}"
    python init_db.py
    echo -e "${GREEN}✅ 데이터베이스 업데이트 완료${NC}"
else
    echo -e "${BLUE}ℹ️ 데이터베이스 마이그레이션 생략 (동기화 완료)${NC}"
fi

# 6. 정적 파일 수집 (필요시)
echo -e "${YELLOW}📁 정적 파일 처리 중...${NC}"
mkdir -p static/charts static/analysis static/summaries static/debug static/memos static/multi_summaries
echo -e "${GREEN}✅ 정적 파일 처리 완료${NC}"

# 7. 서비스 재시작
echo -e "${YELLOW}🔄 서비스 재시작 중...${NC}"

# systemd 서비스 재시작 시도
if systemctl is-active --quiet newsletter-app; then
    sudo systemctl restart newsletter-app
    echo -e "${GREEN}✅ systemd 서비스 재시작 완료${NC}"
elif systemctl is-active --quiet newsletter; then
    sudo systemctl restart newsletter
    echo -e "${GREEN}✅ systemd 서비스 재시작 완료${NC}"
elif command -v pm2 &> /dev/null; then
    # PM2 재시작 시도
    pm2 restart newsletter-app || pm2 start app.py --name newsletter-app
    echo -e "${GREEN}✅ PM2 서비스 재시작 완료${NC}"
else
    # 수동 재시작
    echo -e "${YELLOW}⚠️ 수동으로 앱을 재시작합니다...${NC}"
    pkill -f "python app.py" || true
    nohup python app.py > app.log 2>&1 &
    echo -e "${GREEN}✅ 앱 재시작 완료${NC}"
fi

# nginx 재시작 (있는 경우)
if systemctl is-active --quiet nginx; then
    sudo systemctl restart nginx
    echo -e "${GREEN}✅ Nginx 재시작 완료${NC}"
fi

# 8. 배포 후 데이터베이스 상태 확인
echo -e "${BLUE}📊 배포 후 데이터베이스 상태 확인 중...${NC}"
if python utils/db_sync.py compare; then
    echo -e "${GREEN}✅ 배포 후 데이터베이스 확인 완료${NC}"
else
    echo -e "${YELLOW}⚠️ 배포 후 데이터베이스 확인 중 오류 발생${NC}"
fi

echo -e "${GREEN}🎉 배포 완료!${NC}"
echo -e "${YELLOW}📝 사용 가능한 명령어:${NC}"
echo -e "${YELLOW}  로그 확인: tail -f app.log${NC}"
echo -e "${YELLOW}  서비스 상태: systemctl status newsletter${NC}"
echo -e "${YELLOW}  DB 비교: python utils/db_sync.py compare${NC}"
echo -e "${YELLOW}  DB 동기화: python utils/db_sync.py [sync-to-remote|sync-to-local]${NC}" 