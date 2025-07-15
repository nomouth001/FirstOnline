#!/usr/bin/env python3
"""중복 다운로드 해결 테스트"""

import logging
from models import User
from services.batch_analysis_service import run_single_list_analysis

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_single_ticker_analysis():
    """단일 종목으로 중복 다운로드 테스트"""
    try:
        # 관리자 사용자 조회
        admin_user = User.query.filter_by(is_admin=True).first()
        if not admin_user:
            print("Admin user not found")
            return False
        
        print("Starting single list analysis test...")
        print("Watch the logs for duplicate downloads...")
        
        # 작은 리스트로 테스트 (test 리스트 사용)
        success, data, status_code = run_single_list_analysis("test", admin_user)
        
        if success:
            print(f"Test PASSED: Analysis completed successfully")
            print(f"Data: {data}")
            return True
        else:
            print(f"Test FAILED: {data}")
            return False
            
    except Exception as e:
        print(f'Test FAILED: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    from app import app
    with app.app_context():
        test_single_ticker_analysis() 