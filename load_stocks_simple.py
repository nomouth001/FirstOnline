#!/usr/bin/env python3
import os
import sys
import csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# DATABASE_URL 환경변수 강제 설정
os.environ['DATABASE_URL'] = 'postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db'

from app import app, db
from models import User, StockList, Stock

def main():
    print("📋 종목 리스트 로딩")
    
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("❌ admin 사용자가 없습니다. 먼저 init_postgresql_simple.py를 실행하세요.")
            return
        
        csv_files = [f for f in os.listdir('stock_lists') if f.endswith('.csv')]
        
        for csv_file in csv_files:
            list_name = csv_file.replace('.csv', '').replace('_', ' ').title()
            
            # 기존 리스트 확인
            existing = StockList.query.filter_by(name=list_name, user_id=admin.id).first()
            if existing:
                print(f"⚠️  {list_name} 이미 존재")
                continue
            
            # 새 리스트 생성
            stock_list = StockList(
                name=list_name,
                description=f'{list_name} 종목',
                is_public=True,
                user_id=admin.id
            )
            db.session.add(stock_list)
            db.session.commit()
            
            # CSV 읽기
            csv_path = os.path.join('stock_lists', csv_file)
            stocks_added = 0
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                csv_reader = csv.DictReader(f)
                for row in csv_reader:
                    ticker = row.get('ticker', '').strip()
                    name = row.get('name', '').strip()
                    
                    if ticker and name:
                        stock = Stock(
                            ticker=ticker,
                            name=name,
                            stock_list_id=stock_list.id
                        )
                        db.session.add(stock)
                        stocks_added += 1
            
            db.session.commit()
            print(f"✅ {list_name}: {stocks_added}개 종목 추가")
        
        # 최종 결과
        list_count = StockList.query.filter_by(user_id=admin.id).count()
        stock_count = Stock.query.join(StockList).filter(StockList.user_id == admin.id).count()
        print(f"\n🎉 완료! 리스트: {list_count}개, 종목: {stock_count}개")

if __name__ == "__main__":
    main() 