#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# DATABASE_URL 환경변수 강제 설정
os.environ['DATABASE_URL'] = 'postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db'

from app import app, db
from models import User, StockList, Stock

def main():
    print("🔧 PostgreSQL 직접 초기화")
    
    with app.app_context():
        print("✅ Flask 앱 컨텍스트 시작")
        
        # 테이블 생성
        db.create_all()
        print("✅ 테이블 생성 완료")
        
        # 관리자 확인/생성
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@whatsnextstock.com',
                first_name='관리자',
                last_name='사용자',
                is_verified=True,
                is_admin=True
            )
            admin.set_password('NewsLetter2025!')
            db.session.add(admin)
            db.session.commit()
            print("✅ 관리자 생성 완료")
        else:
            print("✅ 관리자 이미 존재")
        
        # 종목 리스트 개수 확인
        list_count = StockList.query.filter_by(user_id=admin.id).count()
        stock_count = Stock.query.join(StockList).filter(StockList.user_id == admin.id).count()
        
        print(f"📊 현재 종목 리스트: {list_count}개")
        print(f"📊 현재 종목: {stock_count}개")
        
        if list_count == 0:
            print("⚠️  종목 리스트가 없습니다. load_stocks_simple.py를 실행하세요.")
        else:
            print("🎉 데이터가 이미 존재합니다!")

if __name__ == "__main__":
    main() 