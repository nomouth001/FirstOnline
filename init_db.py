#!/usr/bin/env python3
"""
데이터베이스 초기화 스크립트
"""

import os
import sys
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User, StockList, Stock

def init_database():
    """데이터베이스 초기화"""
    with app.app_context():
        print("🗄️ 데이터베이스 테이블 생성 중...")
        db.create_all()
        print("✅ 데이터베이스 테이블 생성 완료")

def create_default_data():
    """기본 데이터 생성"""
    with app.app_context():
        print("📝 기본 데이터 생성 중...")
        
        # 관리자 계정 생성 (실제 어드민 권한)
        if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                email='admin@example.com',
                first_name='관리자',
                last_name='사용자',
                is_verified=True,
                is_admin=True  # 어드민 권한 부여
            )
            
            # 환경변수에서 admin 비밀번호 가져오기
            admin_password = os.getenv('ADMIN_PASSWORD')
            if not admin_password:
                print("⚠️  경고: ADMIN_PASSWORD 환경변수가 설정되지 않았습니다!")
                print("   기본 임시 비밀번호를 사용합니다. 반드시 변경하세요!")
                admin_password = 'CHANGE_ME_IMMEDIATELY_123!'
            
            admin_user.set_password(admin_password)
            db.session.add(admin_user)
            print("👤 관리자 계정 생성 완료 (어드민 권한)")
        
        # 테스트 사용자 생성 (일반 사용자)
        if not User.query.filter_by(username='testuser').first():
            test_user = User(
                username='testuser',
                email='test@example.com',
                first_name='테스트',
                last_name='사용자',
                is_verified=True,
                is_admin=False  # 일반 사용자
            )
            test_user.set_password('test123')
            db.session.add(test_user)
            print("👤 테스트 사용자 계정 생성 완료 (일반 사용자)")
        
        db.session.commit()
        
        # 테스트 사용자의 기본 종목 리스트 생성
        test_user = User.query.filter_by(username='testuser').first()
        if test_user:
            # 기본 리스트 생성
            default_list = StockList(
                name='기본 관심종목',
                description='자주 확인하는 종목들',
                is_default=True,
                user_id=test_user.id
            )
            db.session.add(default_list)
            
            # IT 섹터 리스트 생성
            it_list = StockList(
                name='IT 섹터',
                description='IT 관련 종목들',
                is_public=True,
                user_id=test_user.id
            )
            db.session.add(it_list)
            
            db.session.commit()
            
            # 기본 종목들 추가
            default_stocks = [
                ('AAPL', 'Apple Inc.'),
                ('MSFT', 'Microsoft Corporation'),
                ('GOOGL', 'Alphabet Inc.'),
                ('005930.KS', 'Samsung Electronics Co Ltd'),
                ('000660.KS', 'SK Hynix Inc')
            ]
            
            for ticker, name in default_stocks:
                stock = Stock(
                    ticker=ticker,
                    name=name,
                    stock_list_id=default_list.id
                )
                db.session.add(stock)
            
            # IT 섹터 종목들 추가
            it_stocks = [
                ('NVDA', 'NVIDIA Corporation'),
                ('AMD', 'Advanced Micro Devices Inc'),
                ('INTC', 'Intel Corporation'),
                ('005380.KS', 'Hyundai Motor Co'),
                ('035420.KS', 'NAVER Corp')
            ]
            
            for ticker, name in it_stocks:
                stock = Stock(
                    ticker=ticker,
                    name=name,
                    stock_list_id=it_list.id
                )
                db.session.add(stock)
            
            db.session.commit()
            print("📋 기본 종목 리스트 및 종목들 생성 완료")
        
        print("✅ 기본 데이터 생성 완료")

def main():
    """메인 함수"""
    print("🚀 주식 분석 시스템 데이터베이스 초기화 시작")
    print("=" * 50)
    
    try:
        init_database()
        create_default_data()
        
        print("=" * 50)
        print("🎉 데이터베이스 초기화 완료!")
        print("\n📋 생성된 계정 정보:")
        admin_password_info = os.getenv('ADMIN_PASSWORD', 'CHANGE_ME_IMMEDIATELY_123!')
        if admin_password_info == 'CHANGE_ME_IMMEDIATELY_123!':
            print("  관리자 계정: admin / CHANGE_ME_IMMEDIATELY_123! (⚠️ 임시 비밀번호 - 반드시 변경 필요)")
        else:
            print("  관리자 계정: admin / [환경변수에서 설정된 비밀번호] (어드민 권한)")
        print("  테스트 계정: testuser / test123 (일반 사용자)")
        print("\n💡 이제 Flask 애플리케이션을 실행할 수 있습니다:")
        print("  python app.py")
        print("\n🔐 보안 팁:")
        print("  배포 전에 환경변수 ADMIN_PASSWORD를 설정하세요!")
        print("  예: $env:ADMIN_PASSWORD = 'your_strong_password'")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 