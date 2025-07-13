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

# 7.1 Nginx 설정 확인 및 생성
echo -e "${YELLOW}🔍 Nginx 설정 확인 중...${NC}"
NGINX_CONFIG_DIR="/etc/nginx/sites-available"
NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"
NGINX_CONFIG_FILE="${NGINX_CONFIG_DIR}/whatsnextstock.com"

# Nginx 설치 여부 확인
if ! command -v nginx &> /dev/null; then
    echo -e "${YELLOW}⚠️ Nginx가 설치되어 있지 않습니다. 설정을 건너뜁니다.${NC}"
else
    # sites-available 디렉토리 확인
    if [ ! -d "$NGINX_CONFIG_DIR" ]; then
        echo -e "${YELLOW}⚠️ Nginx sites-available 디렉토리가 없습니다. 설정을 건너뜁니다.${NC}"
    else
        # 설정 파일 존재 여부 확인
        if [ ! -f "$NGINX_CONFIG_FILE" ]; then
            echo -e "${BLUE}ℹ️ Nginx 설정 파일이 없습니다. 새로 생성합니다.${NC}"
            
            # 설정 파일 생성
            sudo tee "$NGINX_CONFIG_FILE" > /dev/null << EOF
server {
    listen 80;
    server_name whatsnextstock.com www.whatsnextstock.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias $(pwd)/static/;
    }
}
EOF
            echo -e "${GREEN}✅ Nginx 설정 파일 생성 완료${NC}"
            
            # sites-enabled에 심볼릭 링크 생성
            if [ -d "$NGINX_ENABLED_DIR" ] && [ ! -f "${NGINX_ENABLED_DIR}/whatsnextstock.com" ]; then
                sudo ln -s "$NGINX_CONFIG_FILE" "${NGINX_ENABLED_DIR}/whatsnextstock.com"
                echo -e "${GREEN}✅ Nginx sites-enabled 심볼릭 링크 생성 완료${NC}"
            fi
        else
            echo -e "${BLUE}ℹ️ 기존 Nginx 설정 파일 발견: $NGINX_CONFIG_FILE${NC}"
            
            # 포트 설정 확인 및 수정
            if grep -q "proxy_pass.*:5000" "$NGINX_CONFIG_FILE"; then
                echo -e "${YELLOW}⚠️ 포트 불일치 감지: Nginx는 5000 포트로 연결 시도, 구니콘은 8000 포트 사용${NC}"
                echo -e "${BLUE}🔄 Nginx 설정 파일 수정 중...${NC}"
                
                # 백업 생성
                sudo cp "$NGINX_CONFIG_FILE" "${NGINX_CONFIG_FILE}.bak"
                
                # 설정 파일 수정 (5000 -> 8000)
                sudo sed -i 's/proxy_pass.*:5000/proxy_pass http:\/\/127.0.0.1:8000/g' "$NGINX_CONFIG_FILE"
                
                echo -e "${GREEN}✅ Nginx 설정 파일 수정 완료 (포트 5000 -> 8000)${NC}"
            else
                echo -e "${GREEN}✅ Nginx 포트 설정이 올바르거나 다른 형식을 사용 중입니다${NC}"
            fi
        fi
    fi
fi

# 8. 서비스 재시작
echo -e "${YELLOW}🔄 서비스 재시작 중...${NC}"

# 기존 프로세스 종료 (안전하게)
echo -e "${BLUE}🛑 기존 프로세스 종료 중...${NC}"
pkill -f "python app.py" || true
pkill -f "celery worker" || true
pkill -f "gunicorn" || true  # 모든 Gunicorn 프로세스 확실히 종료
sleep 5  # 프로세스가 완전히 종료될 때까지 충분히 대기

# Celery 워커 시작 (메모리 최적화 - 워커 수 1개로 제한)
echo -e "${BLUE}🌱 Celery 워커 시작 (메모리 최적화)...${NC}"
chmod +x celery_start.sh
./celery_start.sh
echo -e "${GREEN}✅ Celery 워커 시작 완료${NC}"

# systemd 서비스 재시작 시도 (Gunicorn은 여기서만 시작)
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
    pm2 restart newsletter-app || pm2 start "gunicorn -c gunicorn_config.py app:app" --name newsletter-app
    echo -e "${GREEN}✅ PM2 서비스 재시작 완료${NC}"
else
    # 수동 재시작 (Gunicorn 설정 파일 사용)
    echo -e "${YELLOW}⚠️ 수동으로 앱을 재시작합니다...${NC}"
    nohup gunicorn -c gunicorn_config.py app:app > logs/app.log 2>&1 &
    echo -e "${GREEN}✅ 앱 재시작 완료${NC}"
fi

# 9. nginx 재시작 (있는 경우)
if command -v nginx &> /dev/null && systemctl is-active --quiet nginx 2>/dev/null; then
    echo -e "${BLUE}🔄 Nginx 재시작 중...${NC}"
    # 설정 테스트
    if sudo nginx -t; then
        sudo systemctl restart nginx
        echo -e "${GREEN}✅ Nginx 재시작 완료${NC}"
    else
        echo -e "${RED}❌ Nginx 설정 테스트 실패${NC}"
        if [ -f "${NGINX_CONFIG_FILE}.bak" ]; then
            echo -e "${YELLOW}⚠️ 백업에서 Nginx 설정 복원 중...${NC}"
            sudo cp "${NGINX_CONFIG_FILE}.bak" "$NGINX_CONFIG_FILE"
            sudo systemctl restart nginx
            echo -e "${YELLOW}⚠️ 원래 Nginx 설정으로 복원 완료${NC}"
        fi
    fi
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