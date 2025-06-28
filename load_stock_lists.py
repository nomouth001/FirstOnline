#!/usr/bin/env python3
"""
기존 CSV 파일들을 읽어서 DB에 종목 리스트를 로드하는 스크립트

사용법:
python load_stock_lists.py

이 스크립트는 stock_lists/ 폴더의 모든 CSV 파일을 읽어서
해당하는 종목 리스트를 DB에 생성합니다.
"""

import os
import csv
import sys

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User, StockList, Stock

# CSV 파일명과 리스트 이름 매핑
CSV_TO_LIST_NAME = {
    '00_holdings.csv': '보유 종목',
    '01_ETF.csv': 'ETF 모음',
    '02_IT.csv': 'IT 섹터',
    '03_watch.csv': '관심 종목',
    '04_NomadCoding.csv': '노마드코딩 추천',
    '05_CJK.csv': 'CJK 종목',
    '06_KOSPI.csv': 'KOSPI 종목',
    'default.csv': '기본 종목',
    'test.csv': '테스트 종목',
    'test2.csv': '테스트 종목 2'
}

def load_csv_to_db(csv_file_path, list_name, user_id):
    """CSV 파일을 읽어서 DB에 종목 리스트로 저장"""
    
    # 기존 리스트가 있는지 확인
    existing_list = StockList.query.filter_by(name=list_name, user_id=user_id).first()
    if existing_list:
        print(f"⚠️  '{list_name}' 리스트가 이미 존재합니다. 건너뜁니다.")
        return
    
    # 새 종목 리스트 생성
    stock_list = StockList(
        name=list_name,
        description=f'{list_name} (CSV에서 자동 생성)',
        is_public=True,
        user_id=user_id
    )
    db.session.add(stock_list)
    db.session.commit()
    
    # CSV 파일 읽기
    try:
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            stocks_added = 0
            
            for row in csv_reader:
                ticker = row.get('ticker', '').strip()
                name = row.get('name', '').strip()
                
                if ticker and name:
                    # 중복 종목 확인
                    existing_stock = Stock.query.filter_by(
                        ticker=ticker, 
                        stock_list_id=stock_list.id
                    ).first()
                    
                    if not existing_stock:
                        stock = Stock(
                            ticker=ticker,
                            name=name,
                            stock_list_id=stock_list.id
                        )
                        db.session.add(stock)
                        stocks_added += 1
            
            db.session.commit()
            print(f"✅ '{list_name}' 리스트 생성 완료 - {stocks_added}개 종목 추가")
            
    except Exception as e:
        print(f"❌ '{csv_file_path}' 파일 처리 중 오류: {e}")
        db.session.rollback()

def main():
    """메인 함수"""
    
    with app.app_context():
        # 관리자 사용자 찾기 (첫 번째 사용자를 관리자로 가정)
        admin_user = User.query.filter_by(is_admin=True).first()
        if not admin_user:
            admin_user = User.query.first()
        
        if not admin_user:
            print("❌ DB에 사용자가 없습니다. 먼저 사용자를 생성해주세요.")
            return
        
        print(f"📋 관리자 사용자: {admin_user.username}")
        
        # stock_lists 폴더 경로
        stock_lists_dir = os.path.join(os.path.dirname(__file__), 'stock_lists')
        
        if not os.path.exists(stock_lists_dir):
            print(f"❌ {stock_lists_dir} 폴더가 존재하지 않습니다.")
            return
        
        print(f"📁 CSV 파일 폴더: {stock_lists_dir}")
        
        # CSV 파일들 처리
        csv_files = [f for f in os.listdir(stock_lists_dir) if f.endswith('.csv')]
        
        if not csv_files:
            print("❌ CSV 파일이 없습니다.")
            return
        
        print(f"📄 발견된 CSV 파일: {len(csv_files)}개")
        
        for csv_file in csv_files:
            csv_file_path = os.path.join(stock_lists_dir, csv_file)
            list_name = CSV_TO_LIST_NAME.get(csv_file, csv_file.replace('.csv', ''))
            
            print(f"\n🔄 처리 중: {csv_file} -> '{list_name}'")
            load_csv_to_db(csv_file_path, list_name, admin_user.id)
        
        print(f"\n🎉 CSV 파일 로드 완료!")
        
        # 결과 확인
        total_lists = StockList.query.filter_by(user_id=admin_user.id).count()
        total_stocks = Stock.query.join(StockList).filter(StockList.user_id == admin_user.id).count()
        
        print(f"📊 현재 종목 리스트: {total_lists}개")
        print(f"📊 현재 총 종목 수: {total_stocks}개")

if __name__ == '__main__':
    main() 