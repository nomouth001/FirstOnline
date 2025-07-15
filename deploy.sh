#!/bin/bash

# AWS Lightsail 배포 스크립트
# 사용법: ./deploy.sh

echo "🚀 AWS Lightsail 배포 시작..."

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 에러 발생 시 스크립트 중단
set -e

# 1. 최신 코드 가져오기
echo -e "${YELLOW}📥 GitHub에서 최신 코드 가져오는 중...${NC}"
git fetch origin
git reset --hard origin/main
echo -e "${GREEN}✅ 코드 업데이트 완료${NC}"

# 2. 가상환경 활성화 (있는 경우)
if [ -d "venv" ]; then
    echo -e "${YELLOW}🔧 가상환경 활성화 중...${NC}"
    source venv/bin/activate
    echo -e "${GREEN}✅ 가상환경 활성화 완료${NC}"
fi

# 3. 의존성 업데이트
echo -e "${YELLOW}📦 의존성 업데이트 중...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}✅ 의존성 업데이트 완료${NC}"

# 4. 데이터베이스 마이그레이션
echo -e "${YELLOW}🗄️ 데이터베이스 업데이트 중...${NC}"
python init_db.py
echo -e "${GREEN}✅ 데이터베이스 업데이트 완료${NC}"

# 5. 정적 파일 수집 (필요시)
echo -e "${YELLOW}📁 정적 파일 처리 중...${NC}"
mkdir -p static/charts static/analysis static/summaries static/debug static/memos static/multi_summaries
echo -e "${GREEN}✅ 정적 파일 처리 완료${NC}"

# 6. 서비스 재시작
echo -e "${YELLOW}🔄 서비스 재시작 중...${NC}"

# Redis 서비스 확인 및 시작
if ! systemctl is-active --quiet redis; then
    echo -e "${YELLOW}🔧 Redis 서비스 시작 중...${NC}"
    sudo systemctl start redis
fi

# Celery 워커 재시작
echo -e "${YELLOW}🔄 Celery 워커 재시작 중...${NC}"
pkill -f "celery worker" || echo "실행 중인 Celery 워커가 없습니다."
sleep 2

# Celery 워커 백그라운드 실행
nohup celery -A celery_app:get_celery_app worker --concurrency=2 --loglevel=info > celery-worker.log 2>&1 &
echo -e "${GREEN}✅ Celery 워커 시작 완료${NC}"

# systemd 서비스 재시작 시도
if systemctl is-active --quiet newsletter-app; then
    sudo systemctl restart newsletter-app
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

echo -e "${GREEN}🎉 배포 완료!${NC}"
echo -e "${YELLOW}📝 로그 확인: tail -f app.log${NC}"
echo -e "${YELLOW}🌐 서비스 상태: systemctl status newsletter-app${NC}" 