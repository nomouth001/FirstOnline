#!/usr/bin/env python3
"""
데이터베이스 초기화 스크립트
"""

import os
import sys
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, User, StockList, Stock, AnalysisHistory, NewsletterSubscription, EmailLog
import logging

def initialize_database():
    """데이터베이스 테이블을 생성하고 기본 데이터를 추가합니다."""
    app = create_app()
    with app.app_context():
        logger.info("데이터베이스 테이블 생성 시작...")
        db.create_all()
        logger.info("데이터베이스 테이블 생성 완료")
        
        # 기본 관리자 계정 생성 (없는 경우에만)
        if not User.query.filter_by(username='admin').first():
            logger.info("기본 관리자 계정 생성 중...")
            admin_user = User(username='admin', email='admin@example.com')
            admin_user.set_password('admin')
            admin_user.is_admin = True
            db.session.add(admin_user)
            db.session.commit()
            logger.info("기본 관리자 계정 생성 완료")
        else:
            logger.info("기본 관리자 계정이 이미 존재합니다")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    initialize_database() 