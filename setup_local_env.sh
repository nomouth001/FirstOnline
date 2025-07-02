#!/bin/bash
# 이 스크립트는 WSL/Linux 환경에서 로컬 개발 환경을 초기화합니다.
# 데이터베이스 생성 및 사용자 권한 부여는 미리 완료되어 있어야 합니다.
#
# 사용법:
# 1. source venv/bin/activate  (가상 환경 활성화)
# 2. chmod +x setup_local_env.sh (최초 1회만 실행 권한 부여)
# 3. ./setup_local_env.sh      (스크립트 실행)

echo "--- 로컬 개발 환경 초기화를 시작합니다 ---"

# 오류 발생 시 즉시 스크립트 중단
set -e

# .env 파일이 있는지 확인
if [ ! -f .env ]; then
    echo "오류: .env 파일이 없습니다. 먼저 .env 파일을 생성해주세요."
    exit 1
fi

echo ">>> 기존 마이그레이션 폴더 삭제..."
rm -rf migrations

echo ">>> 데이터베이스 초기화 및 데이터 로드..."
# .env 파일을 자동으로 읽어오므로, DATABASE_URL을 직접 export할 필요가 없습니다.
python init_db.py
python load_stock_lists.py

echo "--- ✅ 로컬 개발 환경 설정 완료! ---"
echo "이제 'flask run' 명령으로 서버를 시작할 수 있습니다." 