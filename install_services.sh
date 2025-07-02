#!/bin/bash

# Celery 서비스 파일 설치 스크립트
echo "Installing Celery systemd services..."

# 서비스 파일들을 시스템 디렉토리로 복사
sudo cp systemd/celery-worker.service /etc/systemd/system/
sudo cp systemd/celery-beat.service /etc/systemd/system/

# 권한 설정
sudo chmod 644 /etc/systemd/system/celery-worker.service
sudo chmod 644 /etc/systemd/system/celery-beat.service

# systemd 재로드
sudo systemctl daemon-reload

# 서비스 활성화 (부팅 시 자동 시작)
sudo systemctl enable celery-worker
sudo systemctl enable celery-beat

# 서비스 시작
sudo systemctl start celery-worker
sudo systemctl start celery-beat

echo "Celery services installed and started successfully!"

# 상태 확인
echo "Service status:"
sudo systemctl status celery-worker --no-pager
sudo systemctl status celery-beat --no-pager

echo "Process check:"
ps aux | grep -E "(celery)" | grep -v grep 