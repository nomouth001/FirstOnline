#!/bin/bash

# Celery 워커 시작 스크립트 (워커 수 제한)
# 사용법: ./celery_start.sh

echo "🚀 Celery 워커 시작 (메모리 최적화 버전)..."

# 가상환경 활성화 (있는 경우)
if [ -d "venv" ]; then
    echo "🔧 가상환경 활성화 중..."
    source venv/bin/activate
fi

# 기존 Celery 프로세스 중지
echo "🛑 기존 Celery 프로세스 중지 중..."
pkill -f "celery worker" || echo "실행 중인 Celery 워커가 없습니다."
sleep 2

# Celery 워커 시작 (동시성 1로 설정)
echo "✨ Celery 워커 시작 (워커 수: 1)..."
celery -A celery_app worker --concurrency=1 --loglevel=info &

echo "✅ Celery 워커 시작 완료!" 