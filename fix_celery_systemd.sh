#!/bin/bash

# Celery systemd 서비스 파일 수정 스크립트
echo "🔧 Celery systemd 서비스 파일 수정 중..."

# Celery Worker 서비스 파일 수정
sudo tee /etc/systemd/system/celery-worker.service > /dev/null <<EOF
[Unit]
Description=Celery Worker Service
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/newsletter-app
Environment=PATH=/home/ubuntu/newsletter-app/venv/bin
Environment=CELERY_WORKER=1
ExecStart=/home/ubuntu/newsletter-app/venv/bin/celery -A celery_app:celery worker --concurrency=2 --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Celery Beat 서비스 파일 수정
sudo tee /etc/systemd/system/celery-beat.service > /dev/null <<EOF
[Unit]
Description=Celery Beat Service
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/newsletter-app
Environment=PATH=/home/ubuntu/newsletter-app/venv/bin
Environment=CELERY_WORKER=1
ExecStart=/home/ubuntu/newsletter-app/venv/bin/celery -A celery_app:celery beat --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# systemd 재로드
sudo systemctl daemon-reload

# 서비스 재시작
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat

# 상태 확인
sudo systemctl status celery-worker
sudo systemctl status celery-beat

echo "✅ Celery systemd 서비스 파일 수정 완료" 