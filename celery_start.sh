#!/bin/bash

# Celery 워커 시작 스크립트 (개선된 구조)
# 사용법: ./celery_start.sh

echo "🚀 Celery 워커 시작 (개선된 구조)..."

# 가상환경 활성화 (있는 경우)
if [ -d "venv" ]; then
    echo "🔧 가상환경 활성화 중..."
    source venv/bin/activate
fi

# 기존 Celery 프로세스 중지
echo "🛑 기존 Celery 프로세스 중지 중..."
pkill -f "celery worker" || echo "실행 중인 Celery 워커가 없습니다."
sleep 2

# CPU 코어 수 확인
CPU_CORES=$(nproc)
echo "🔍 CPU 코어 수: $CPU_CORES"

# Celery 워커 환경변수 설정 및 시작
echo "✨ Celery 워커 시작 (동시성: $CPU_CORES)..."
export CELERY_WORKER=1
celery -A celery_app:get_celery_app worker --concurrency=$CPU_CORES --loglevel=info &

echo "✅ Celery 워커 시작 완료!" 