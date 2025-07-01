#!/bin/bash
echo "🚀 NewsLetter 자동 배포 스크립트"
echo "================================="

# 1. 환경변수 설정
export DATABASE_URL='postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db'
echo "✅ 환경변수 설정 완료"

# 2. Python 패키지 설치
echo "📦 Python 패키지 설치 중..."
pip3 install -r requirements.txt
echo "✅ 패키지 설치 완료"

# 3. 데이터베이스 초기화
echo "🗄️ 데이터베이스 초기화 중..."
python3 init_postgresql_simple.py

# 4. 종목 데이터 로딩
echo "📋 종목 데이터 로딩 중..."
python3 load_stocks_simple.py

# 5. 서비스 재시작
echo "🔄 서비스 재시작 중..."
sudo systemctl restart newsletter

# 6. 상태 확인
echo "🔍 서비스 상태 확인..."
sudo systemctl status newsletter --no-pager

echo ""
echo "🎉 배포 완료!"
echo "웹사이트: https://whatsnextstock.com"
echo "관리자: admin / NewsLetter2025!" 