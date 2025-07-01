#!/usr/bin/env python3
"""
PostgreSQL 직접 초기화 스크립트
환경변수 무관하게 PostgreSQL에 바로 연결
"""

import os
import sys
import csv
from sqlalchemy import create_engine, text

# PostgreSQL 직접 연결
POSTGRESQL_URI = "postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db"

def main():
    """PostgreSQL 직접 초기화"""
    print("🔧 PostgreSQL 직접 초기화 시작")
    
    try:
        engine = create_engine(POSTGRESQL_URI)
        
        with engine.connect() as conn:
            print("✅ PostgreSQL 연결 성공")
            
            # 관리자 사용자 생성
            from werkzeug.security import generate_password_hash
            password_hash = generate_password_hash('NewsLetter2025!')
            
            # 기존 사용자 확인
            result = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin';"))
            if result.fetchone()[0] == 0:
                conn.execute(text("""
                    INSERT INTO users (username, email, password_hash, first_name, last_name, is_verified, is_admin)
                    VALUES ('admin', 'admin@whatsnextstock.com', :password_hash, '관리자', '사용자', TRUE, TRUE);
                """), {'password_hash': password_hash})
                print("👤 관리자 생성 완료")
            
            # 관리자 ID 가져오기
            result = conn.execute(text("SELECT id FROM users WHERE username = 'admin';"))
            admin_id = result.fetchone()[0]
            
            # CSV 파일 처리
            stock_lists_dir = os.path.join(os.path.dirname(__file__), 'stock_lists')
            csv_files = [f for f in os.listdir(stock_lists_dir) if f.endswith('.csv')]
            
            for csv_file in csv_files:
                list_name = csv_file.replace('.csv', '').replace('_', ' ').title()
                
                # 리스트 생성
                result = conn.execute(text("""
                    INSERT INTO stock_lists (name, description, is_public, user_id)
                    VALUES (:name, :description, TRUE, :user_id)
                    ON CONFLICT DO NOTHING
                    RETURNING id;
                """), {
                    'name': list_name,
                    'description': f'{list_name} 종목',
                    'user_id': admin_id
                })
                
                list_id_result = result.fetchone()
                if list_id_result:
                    list_id = list_id_result[0]
                    
                    # CSV 파일 읽기
                    csv_path = os.path.join(stock_lists_dir, csv_file)
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        csv_reader = csv.DictReader(f)
                        for row in csv_reader:
                            ticker = row.get('ticker', '').strip()
                            name = row.get('name', '').strip()
                            
                            if ticker and name:
                                conn.execute(text("""
                                    INSERT INTO stocks (ticker, name, stock_list_id)
                                    VALUES (:ticker, :name, :list_id)
                                    ON CONFLICT DO NOTHING;
                                """), {
                                    'ticker': ticker,
                                    'name': name,
                                    'list_id': list_id
                                })
                    
                    print(f"📋 {list_name} 생성 완료")
            
            conn.commit()
            
            # 결과 확인
            result = conn.execute(text("SELECT COUNT(*) FROM stock_lists WHERE user_id = :admin_id;"), {'admin_id': admin_id})
            list_count = result.fetchone()[0]
            
            result = conn.execute(text("SELECT COUNT(*) FROM stocks s JOIN stock_lists sl ON s.stock_list_id = sl.id WHERE sl.user_id = :admin_id;"), {'admin_id': admin_id})
            stock_count = result.fetchone()[0]
            
            print(f"\n🎉 완료! 종목 리스트: {list_count}개, 종목: {stock_count}개")
            
    except Exception as e:
        print(f"❌ 오류: {e}")

if __name__ == "__main__":
    main() 