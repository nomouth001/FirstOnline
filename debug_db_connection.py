#!/usr/bin/env python3
"""
데이터베이스 연결 및 환경변수 디버깅 스크립트
"""

import os
import sys
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_environment():
    """환경변수 확인"""
    print("🔍 환경변수 확인")
    print("=" * 50)
    
    # 중요한 환경변수들 확인
    env_vars = [
        'DATABASE_URL',
        'ADMIN_PASSWORD',
        'GOOGLE_API_KEY',
        'SECRET_KEY',
        'FLASK_DEBUG'
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # 민감한 정보는 일부만 표시
            if var in ['DATABASE_URL', 'ADMIN_PASSWORD', 'GOOGLE_API_KEY', 'SECRET_KEY']:
                display_value = f"{value[:10]}..." if len(value) > 10 else value
            else:
                display_value = value
            print(f"  ✅ {var}: {display_value}")
        else:
            print(f"  ❌ {var}: 설정되지 않음")

def check_database_connection():
    """데이터베이스 연결 확인"""
    print("\n🗄️ 데이터베이스 연결 확인")
    print("=" * 50)
    
    try:
        from app import app, db
        from models import User
        
        with app.app_context():
            # 데이터베이스 URI 확인
            print(f"  📍 데이터베이스 URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
            
            # 연결 테스트
            db.session.execute(db.text("SELECT 1"))
            print("  ✅ 데이터베이스 연결 성공")
            
            # 데이터베이스 타입 확인
            engine_name = db.engine.name
            print(f"  🔧 데이터베이스 엔진: {engine_name}")
            
            # 테이블 확인
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"  📋 테이블 수: {len(tables)}")
            
            # 사용자 수 확인
            user_count = User.query.count()
            print(f"  👤 사용자 수: {user_count}")
            
            # 관리자 계정 확인
            admin_user = User.query.filter_by(username='admin').first()
            if admin_user:
                print(f"  👑 관리자 계정: 존재 (ID: {admin_user.id})")
                print(f"  🔐 관리자 권한: {admin_user.is_admin}")
            else:
                print("  ❌ 관리자 계정: 없음")
                
    except Exception as e:
        print(f"  ❌ 데이터베이스 연결 실패: {e}")
        return False
    
    return True

def check_config():
    """설정 확인"""
    print("\n⚙️ 설정 확인")
    print("=" * 50)
    
    try:
        from config import SQLALCHEMY_DATABASE_URI, DEBUG
        
        print(f"  📍 설정 파일 DATABASE_URI: {SQLALCHEMY_DATABASE_URI[:50]}...")
        print(f"  🐛 DEBUG 모드: {DEBUG}")
        
        # 데이터베이스 타입 판단
        if SQLALCHEMY_DATABASE_URI.startswith('postgresql'):
            print("  🐘 데이터베이스 타입: PostgreSQL")
        elif SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
            print("  🗃️ 데이터베이스 타입: SQLite")
        else:
            print(f"  ❓ 데이터베이스 타입: 알 수 없음 ({SQLALCHEMY_DATABASE_URI.split(':')[0]})")
            
    except Exception as e:
        print(f"  ❌ 설정 확인 실패: {e}")

def main():
    """메인 함수"""
    print("🚀 데이터베이스 연결 디버깅")
    print("=" * 50)
    print(f"실행 시간: {datetime.now()}")
    print(f"작업 디렉토리: {os.getcwd()}")
    
    check_environment()
    check_config()
    
    if check_database_connection():
        print("\n🎉 모든 확인 완료!")
    else:
        print("\n❌ 문제가 발견되었습니다.")
        sys.exit(1)

if __name__ == "__main__":
    main() 