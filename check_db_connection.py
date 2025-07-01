#!/usr/bin/env python3
"""
데이터베이스 연결 상태 확인 스크립트
AWS에서 실행하여 어떤 DB에 연결되는지 확인
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import SQLALCHEMY_DATABASE_URI
from app import app, db
from models import User, StockList, Stock

def check_db_connection():
    """데이터베이스 연결 및 데이터 상태 확인"""
    
    print("🔍 데이터베이스 연결 상태 확인")
    print("=" * 60)
    
    # 1. 환경변수 확인
    print("📋 환경변수 정보:")
    print(f"  DATABASE_URL: {os.getenv('DATABASE_URL', '설정되지 않음')}")
    print(f"  SQLALCHEMY_DATABASE_URI: {SQLALCHEMY_DATABASE_URI}")
    print()
    
    # 2. 데이터베이스 연결 테스트
    try:
        with app.app_context():
            print("🔗 데이터베이스 연결 테스트:")
            
            # 연결 테스트
            db.engine.connect()
            print("  ✅ 데이터베이스 연결 성공")
            
            # 테이블 존재 확인
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"  📋 존재하는 테이블: {tables}")
            
            # 데이터 개수 확인
            print("\n📊 데이터 현황:")
            try:
                user_count = User.query.count()
                print(f"  👥 Users: {user_count}개")
                
                if user_count > 0:
                    users = User.query.all()
                    for user in users:
                        print(f"    - {user.username} (ID: {user.id}, Admin: {user.is_admin})")
                
                stock_list_count = StockList.query.count()
                print(f"  📋 StockLists: {stock_list_count}개")
                
                if stock_list_count > 0:
                    stock_lists = StockList.query.all()
                    for sl in stock_lists:
                        stock_count = Stock.query.filter_by(stock_list_id=sl.id).count()
                        print(f"    - {sl.name} (User ID: {sl.user_id}, Stocks: {stock_count}개)")
                
                total_stocks = Stock.query.count()
                print(f"  📈 Total Stocks: {total_stocks}개")
                
            except Exception as e:
                print(f"  ❌ 데이터 조회 실패: {e}")
                
    except Exception as e:
        print(f"  ❌ 데이터베이스 연결 실패: {e}")
        return False
    
    return True

def force_postgresql_connection():
    """강제로 PostgreSQL 연결 테스트"""
    print("\n🔧 PostgreSQL 강제 연결 테스트")
    print("=" * 60)
    
    # PostgreSQL 연결 문자열 직접 구성
    postgresql_uri = "postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db"
    
    try:
        from sqlalchemy import create_engine
        engine = create_engine(postgresql_uri)
        
        with engine.connect() as conn:
            print("✅ PostgreSQL 직접 연결 성공")
            
            # 테이블 목록 조회
            result = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
            tables = [row[0] for row in result]
            print(f"📋 PostgreSQL 테이블: {tables}")
            
            # 사용자 수 조회
            if 'users' in tables:
                result = conn.execute("SELECT COUNT(*) FROM users;")
                user_count = result.fetchone()[0]
                print(f"👥 PostgreSQL Users: {user_count}개")
                
                if user_count > 0:
                    result = conn.execute("SELECT username, id, is_admin FROM users;")
                    users = result.fetchall()
                    for username, user_id, is_admin in users:
                        print(f"    - {username} (ID: {user_id}, Admin: {is_admin})")
            
            # 종목 리스트 수 조회
            if 'stock_lists' in tables:
                result = conn.execute("SELECT COUNT(*) FROM stock_lists;")
                stock_list_count = result.fetchone()[0]
                print(f"📋 PostgreSQL StockLists: {stock_list_count}개")
                
                if stock_list_count > 0:
                    result = conn.execute("SELECT name, user_id, id FROM stock_lists;")
                    stock_lists = result.fetchall()
                    for name, user_id, list_id in stock_lists:
                        # 각 리스트의 종목 수 조회
                        stock_result = conn.execute(f"SELECT COUNT(*) FROM stocks WHERE stock_list_id = {list_id};")
                        stock_count = stock_result.fetchone()[0]
                        print(f"    - {name} (User ID: {user_id}, Stocks: {stock_count}개)")
            
    except Exception as e:
        print(f"❌ PostgreSQL 직접 연결 실패: {e}")

def main():
    """메인 함수"""
    print("🗄️ 데이터베이스 연결 진단 도구")
    print("이 스크립트는 현재 어떤 데이터베이스에 연결되는지 확인합니다.")
    print()
    
    # Flask 앱 설정 확인
    check_db_connection()
    
    # PostgreSQL 직접 연결 테스트
    force_postgresql_connection()
    
    print("\n" + "=" * 60)
    print("✅ 진단 완료")
    print("\n💡 해결 방법:")
    print("1. AWS에서 실행: export DATABASE_URL='postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db'")
    print("2. 그 후: python init_db.py && python load_stock_lists.py")

if __name__ == "__main__":
    main() 