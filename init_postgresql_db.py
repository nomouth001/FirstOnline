#!/usr/bin/env python3
"""
PostgreSQL 데이터베이스 직접 초기화 스크립트
환경변수에 관계없이 PostgreSQL에 직접 연결하여 초기화
"""

import os
import sys
import csv
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# PostgreSQL 연결 정보
POSTGRESQL_URI = "postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db"

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

def create_postgresql_tables(engine):
    """PostgreSQL에 테이블 생성"""
    print("🗄️ PostgreSQL 테이블 생성 중...")
    
    with engine.connect() as conn:
        # Users 테이블 생성
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(25) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                first_name VARCHAR(50),
                last_name VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                is_verified BOOLEAN DEFAULT FALSE,
                is_admin BOOLEAN DEFAULT FALSE,
                is_withdrawn BOOLEAN DEFAULT FALSE,
                withdrawn_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        
        # StockLists 테이블 생성
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_lists (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                is_public BOOLEAN DEFAULT FALSE,
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """))
        
        # Stocks 테이블 생성
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stocks (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(20) NOT NULL,
                name VARCHAR(200),
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                stock_list_id INTEGER NOT NULL,
                FOREIGN KEY (stock_list_id) REFERENCES stock_lists(id)
            );
        """))
        
        # AnalysisHistory 테이블 생성
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS analysis_history (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(20) NOT NULL,
                analysis_date DATE NOT NULL,
                analysis_type VARCHAR(50) DEFAULT 'daily',
                chart_path VARCHAR(500),
                analysis_path VARCHAR(500),
                summary TEXT,
                status VARCHAR(20) DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """))
        
        # NewsletterSubscriptions 테이블 생성
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS newsletter_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                frequency VARCHAR(20) DEFAULT 'daily',
                send_time TIME DEFAULT '09:00:00',
                include_charts BOOLEAN DEFAULT TRUE,
                include_summary BOOLEAN DEFAULT TRUE,
                include_technical_analysis BOOLEAN DEFAULT TRUE,
                unsubscribe_token VARCHAR(100) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """))
        
        # EmailLogs 테이블 생성
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS email_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                email_type VARCHAR(50) NOT NULL,
                subject VARCHAR(200) NOT NULL,
                status VARCHAR(20) DEFAULT 'sent',
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """))
        
        conn.commit()
        print("✅ PostgreSQL 테이블 생성 완료")

def create_admin_user(engine):
    """관리자 사용자 생성"""
    print("👤 관리자 사용자 생성 중...")
    
    with engine.connect() as conn:
        # 기존 admin 사용자 확인
        result = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin';"))
        admin_count = result.fetchone()[0]
        
        if admin_count == 0:
            # 비밀번호 해시 생성 (werkzeug 사용)
            from werkzeug.security import generate_password_hash
            password_hash = generate_password_hash('NewsLetter2025!')
            
            conn.execute(text("""
                INSERT INTO users (username, email, password_hash, first_name, last_name, is_verified, is_admin)
                VALUES ('admin', 'admin@whatsnextstock.com', :password_hash, '관리자', '사용자', TRUE, TRUE);
            """), {'password_hash': password_hash})
            
            conn.commit()
            print("✅ 관리자 사용자 생성 완료: admin / NewsLetter2025!")
        else:
            print("⚠️  관리자 사용자가 이미 존재합니다.")

def load_stock_lists_to_postgresql(engine):
    """CSV 파일들을 읽어서 PostgreSQL에 종목 리스트 생성"""
    print("📋 종목 리스트 로딩 중...")
    
    # 관리자 사용자 ID 가져오기
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id FROM users WHERE username = 'admin';"))
        admin_user_id = result.fetchone()[0]
        
        # stock_lists 디렉토리 경로
        script_dir = os.path.dirname(os.path.abspath(__file__))
        stock_lists_dir = os.path.join(script_dir, 'stock_lists')
        
        if not os.path.exists(stock_lists_dir):
            print(f"❌ {stock_lists_dir} 폴더가 존재하지 않습니다.")
            return
        
        # CSV 파일들 처리
        csv_files = [f for f in os.listdir(stock_lists_dir) if f.endswith('.csv')]
        
        for csv_file in csv_files:
            csv_file_path = os.path.join(stock_lists_dir, csv_file)
            list_name = CSV_TO_LIST_NAME.get(csv_file, csv_file.replace('.csv', ''))
            
            print(f"🔄 처리 중: {csv_file} -> '{list_name}'")
            
            # 기존 리스트 확인
            result = conn.execute(text("""
                SELECT COUNT(*) FROM stock_lists 
                WHERE name = :list_name AND user_id = :user_id;
            """), {'list_name': list_name, 'user_id': admin_user_id})
            
            if result.fetchone()[0] > 0:
                print(f"⚠️  '{list_name}' 리스트가 이미 존재합니다. 건너뜁니다.")
                continue
            
            # 새 종목 리스트 생성
            result = conn.execute(text("""
                INSERT INTO stock_lists (name, description, is_public, user_id)
                VALUES (:name, :description, TRUE, :user_id)
                RETURNING id;
            """), {
                'name': list_name,
                'description': f'{list_name} (CSV에서 자동 생성)',
                'user_id': admin_user_id
            })
            
            stock_list_id = result.fetchone()[0]
            
            # CSV 파일 읽기 및 종목 추가
            try:
                stocks_added = 0
                with open(csv_file_path, 'r', encoding='utf-8') as file:
                    csv_reader = csv.DictReader(file)
                    
                    for row in csv_reader:
                        ticker = row.get('ticker', '').strip()
                        name = row.get('name', '').strip()
                        
                        if ticker and name:
                            # 중복 종목 확인
                            duplicate_check = conn.execute(text("""
                                SELECT COUNT(*) FROM stocks 
                                WHERE ticker = :ticker AND stock_list_id = :stock_list_id;
                            """), {'ticker': ticker, 'stock_list_id': stock_list_id})
                            
                            if duplicate_check.fetchone()[0] == 0:
                                conn.execute(text("""
                                    INSERT INTO stocks (ticker, name, stock_list_id)
                                    VALUES (:ticker, :name, :stock_list_id);
                                """), {
                                    'ticker': ticker,
                                    'name': name,
                                    'stock_list_id': stock_list_id
                                })
                                stocks_added += 1
                
                conn.commit()
                print(f"✅ '{list_name}' 리스트 생성 완료 - {stocks_added}개 종목 추가")
                
            except Exception as e:
                print(f"❌ '{csv_file_path}' 파일 처리 중 오류: {e}")
                conn.rollback()

def main():
    """메인 함수"""
    print("🚀 PostgreSQL 데이터베이스 직접 초기화")
    print("=" * 60)
    print(f"연결 대상: {POSTGRESQL_URI}")
    print()
    
    try:
        # PostgreSQL 엔진 생성
        engine = create_engine(POSTGRESQL_URI)
        
        # 연결 테스트
        with engine.connect() as conn:
            print("✅ PostgreSQL 연결 성공")
        
        # 1. 테이블 생성
        create_postgresql_tables(engine)
        
        # 2. 관리자 사용자 생성
        create_admin_user(engine)
        
        # 3. 종목 리스트 로딩
        load_stock_lists_to_postgresql(engine)
        
        # 4. 결과 확인
        with engine.connect() as conn:
            user_result = conn.execute(text("SELECT COUNT(*) FROM users;"))
            user_count = user_result.fetchone()[0]
            
            list_result = conn.execute(text("SELECT COUNT(*) FROM stock_lists;"))
            list_count = list_result.fetchone()[0]
            
            stock_result = conn.execute(text("SELECT COUNT(*) FROM stocks;"))
            stock_count = stock_result.fetchone()[0]
            
            print("\n📊 최종 결과:")
            print(f"  👥 사용자: {user_count}개")
            print(f"  📋 종목 리스트: {list_count}개")
            print(f"  📈 종목: {stock_count}개")
        
        print("\n🎉 PostgreSQL 데이터베이스 초기화 완료!")
        print("\n💡 이제 웹사이트에서 admin/NewsLetter2025! 로 로그인하세요.")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 