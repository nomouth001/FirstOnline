#!/bin/bash

# 안전한 AWS Lightsail 배포 스크립트
# 기존 데이터를 보존하면서 배포합니다.
# 사용법: ./deploy_safe.sh

echo "🚀 안전한 배포 시작 (기존 데이터 보존)..."

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 에러 발생 시 스크립트 중단
set -e

# 시작 시간 기록
START_TIME=$(date +%s)

echo -e "${BLUE}📋 배포 전 환경 확인${NC}"
echo "현재 시간: $(date)"
echo "작업 디렉토리: $(pwd)"
echo "Python 버전: $(python --version)"

# 0. 배포 전 데이터베이스 백업
echo -e "${YELLOW}💾 배포 전 데이터베이스 백업 중...${NC}"
if python utils/db_migration.py backup; then
    echo -e "${GREEN}✅ 배포 전 백업 완료${NC}"
else
    echo -e "${RED}❌ 배포 전 백업 실패${NC}"
    exit 1
fi

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

# 4. 데이터베이스 마이그레이션 상태 확인
echo -e "${BLUE}📊 데이터베이스 마이그레이션 상태 확인${NC}"
python utils/db_migration.py status

# 5. 안전한 데이터베이스 마이그레이션 실행
echo -e "${YELLOW}🔄 안전한 데이터베이스 마이그레이션 중...${NC}"
echo -e "${BLUE}ℹ️ 기존 데이터를 보존하면서 스키마 업데이트를 진행합니다...${NC}"

if python utils/db_migration.py migrate; then
    echo -e "${GREEN}✅ 데이터베이스 마이그레이션 완료${NC}"
else
    echo -e "${RED}❌ 데이터베이스 마이그레이션 실패${NC}"
    echo -e "${YELLOW}⚠️ 백업 파일에서 데이터 복원을 고려하세요${NC}"
    exit 1
fi

# 6. 정적 파일 수집 (필요시)
echo -e "${YELLOW}📁 정적 파일 처리 중...${NC}"
mkdir -p static/charts static/analysis static/summaries static/debug static/memos static/multi_summaries
mkdir -p logs
echo -e "${GREEN}✅ 정적 파일 처리 완료${NC}"

# 7. 설정 파일 권한 확인
echo -e "${YELLOW}🔒 설정 파일 권한 확인 중...${NC}"
if [ -f ".env" ]; then
    chmod 600 .env
    echo -e "${GREEN}✅ .env 파일 권한 설정 완료${NC}"
fi

# 8. 서비스 재시작
echo -e "${YELLOW}🔄 서비스 재시작 중...${NC}"

# 기존 프로세스 종료 (안전하게)
echo -e "${BLUE}🛑 기존 프로세스 종료 중...${NC}"
pkill -f "python app.py" || true
pkill -f "celery worker" || true
sleep 2

# Celery 워커 시작 (메모리 최적화 - 워커 수 1개로 제한)
echo -e "${BLUE}🌱 Celery 워커 시작 (메모리 최적화)...${NC}"
chmod +x celery_start.sh
./celery_start.sh
echo -e "${GREEN}✅ Celery 워커 시작 완료${NC}"

# systemd 서비스 재시작 시도
if systemctl is-active --quiet newsletter 2>/dev/null; then
    echo -e "${BLUE}🔄 systemd 서비스 재시작 중...${NC}"
    sudo systemctl restart newsletter
    echo -e "${GREEN}✅ systemd 서비스 재시작 완료${NC}"
elif systemctl is-active --quiet newsletter-app 2>/dev/null; then
    echo -e "${BLUE}🔄 systemd 서비스 재시작 중...${NC}"
    sudo systemctl restart newsletter-app
    echo -e "${GREEN}✅ systemd 서비스 재시작 완료${NC}"
elif command -v pm2 &> /dev/null; then
    # PM2 재시작 시도
    echo -e "${BLUE}🔄 PM2 서비스 재시작 중...${NC}"
    pm2 restart newsletter-app || pm2 start app.py --name newsletter-app --interpreter python3
    echo -e "${GREEN}✅ PM2 서비스 재시작 완료${NC}"
else
    # 수동 재시작
    echo -e "${YELLOW}⚠️ 수동으로 앱을 재시작합니다...${NC}"
    nohup python app.py > logs/app.log 2>&1 &
    echo -e "${GREEN}✅ 앱 재시작 완료${NC}"
fi

# 9. nginx 재시작 (있는 경우)
if systemctl is-active --quiet nginx 2>/dev/null; then
    echo -e "${BLUE}🔄 Nginx 재시작 중...${NC}"
    sudo systemctl restart nginx
    echo -e "${GREEN}✅ Nginx 재시작 완료${NC}"
fi

# 10. 서비스 상태 확인
echo -e "${BLUE}🔍 서비스 상태 확인 중...${NC}"
sleep 5

# 서비스 상태 확인
if systemctl is-active --quiet newsletter 2>/dev/null; then
    echo -e "${GREEN}✅ Newsletter 서비스 정상 실행 중${NC}"
elif systemctl is-active --quiet newsletter-app 2>/dev/null; then
    echo -e "${GREEN}✅ Newsletter-app 서비스 정상 실행 중${NC}"
elif command -v pm2 &> /dev/null && pm2 list | grep -q newsletter-app; then
    echo -e "${GREEN}✅ PM2 서비스 정상 실행 중${NC}"
else
    echo -e "${YELLOW}⚠️ 서비스 상태 확인 필요${NC}"
    # 프로세스 확인
    if pgrep -f "python app.py" > /dev/null; then
        echo -e "${GREEN}✅ Python 앱 프로세스 확인됨${NC}"
    else
        echo -e "${RED}❌ Python 앱 프로세스 없음${NC}"
    fi
fi

# 11. 배포 후 데이터베이스 상태 확인
echo -e "${BLUE}📊 배포 후 데이터베이스 상태 확인${NC}"
python utils/db_migration.py status

# 12. 배포 완료 요약
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo -e "${GREEN}🎉 안전한 배포 완료!${NC}"
echo -e "${BLUE}📋 배포 요약:${NC}"
echo -e "${BLUE}  소요 시간: ${DURATION}초${NC}"
echo -e "${BLUE}  완료 시간: $(date)${NC}"
echo -e "${BLUE}  백업 파일: migration_backup_*.json${NC}"

echo -e "${YELLOW}📝 유용한 명령어:${NC}"
echo -e "${YELLOW}  로그 확인: tail -f logs/app.log${NC}"
echo -e "${YELLOW}  서비스 상태: systemctl status newsletter${NC}"
echo -e "${YELLOW}  DB 상태: python utils/db_migration.py status${NC}"
echo -e "${YELLOW}  DB 백업: python utils/db_migration.py backup${NC}"
echo -e "${YELLOW}  프로세스 확인: ps aux | grep python${NC}"

echo -e "${GREEN}✨ 배포가 성공적으로 완료되었습니다!${NC}" 