#!/usr/bin/env python3
"""
안전한 데이터베이스 마이그레이션 시스템
기존 데이터를 보존하면서 스키마 변경 및 초기 데이터 설정을 담당합니다.
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import User, StockList, Stock, AnalysisHistory, NewsletterSubscription, EmailLog

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseMigrationManager:
    """안전한 데이터베이스 마이그레이션 관리자"""
    
    def __init__(self):
        self.version_file = 'db_version.json'
        self.current_version = self.get_current_version()
        self.target_version = "1.0.0"  # 현재 스키마 버전
        
    def get_current_version(self) -> str:
        """현재 데이터베이스 버전 조회"""
        try:
            if os.path.exists(self.version_file):
                with open(self.version_file, 'r') as f:
                    version_data = json.load(f)
                    return version_data.get('version', '0.0.0')
            return '0.0.0'
        except Exception:
            return '0.0.0'
    
    def set_version(self, version: str):
        """데이터베이스 버전 설정"""
        version_data = {
            'version': version,
            'updated_at': datetime.now().isoformat(),
            'migration_history': self.get_migration_history()
        }
        
        with open(self.version_file, 'w') as f:
            json.dump(version_data, f, indent=2)
        
        logger.info(f"데이터베이스 버전 업데이트: {version}")
    
    def get_migration_history(self) -> List[Dict]:
        """마이그레이션 히스토리 조회"""
        try:
            if os.path.exists(self.version_file):
                with open(self.version_file, 'r') as f:
                    version_data = json.load(f)
                    return version_data.get('migration_history', [])
            return []
        except Exception:
            return []
    
    def backup_database(self) -> str:
        """데이터베이스 백업"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"migration_backup_{timestamp}.json"
        
        try:
            with app.app_context():
                # 현재 데이터 내보내기
                data = {}
                
                # 사용자 데이터
                users = User.query.all()
                data['users'] = [{
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'password_hash': user.password_hash,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_active': user.is_active,
                    'is_verified': user.is_verified,
                    'is_admin': user.is_admin,
                    'is_withdrawn': user.is_withdrawn,
                    'withdrawn_at': user.withdrawn_at.isoformat() if user.withdrawn_at else None,
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'updated_at': user.updated_at.isoformat() if user.updated_at else None
                } for user in users]
                
                # 주식 리스트 데이터
                stock_lists = StockList.query.all()
                data['stock_lists'] = [{
                    'id': sl.id,
                    'name': sl.name,
                    'description': sl.description,
                    'is_public': sl.is_public,
                    'is_default': sl.is_default,
                    'user_id': sl.user_id,
                    'created_at': sl.created_at.isoformat() if sl.created_at else None,
                    'updated_at': sl.updated_at.isoformat() if sl.updated_at else None
                } for sl in stock_lists]
                
                # 주식 데이터
                stocks = Stock.query.all()
                data['stocks'] = [{
                    'id': stock.id,
                    'ticker': stock.ticker,
                    'name': stock.name,
                    'stock_list_id': stock.stock_list_id,
                    'added_at': stock.added_at.isoformat() if stock.added_at else None
                } for stock in stocks]
                
                # 분석 히스토리
                analysis_history = AnalysisHistory.query.all()
                data['analysis_history'] = [{
                    'id': ah.id,
                    'ticker': ah.ticker,
                    'analysis_date': ah.analysis_date.isoformat() if ah.analysis_date else None,
                    'analysis_type': ah.analysis_type,
                    'chart_path': ah.chart_path,
                    'analysis_path': ah.analysis_path,
                    'summary': ah.summary,
                    'status': ah.status,
                    'user_id': ah.user_id,
                    'created_at': ah.created_at.isoformat() if ah.created_at else None
                } for ah in analysis_history]
                
                # 뉴스레터 구독
                newsletter_subs = NewsletterSubscription.query.all()
                data['newsletter_subscriptions'] = [{
                    'id': ns.id,
                    'user_id': ns.user_id,
                    'is_active': ns.is_active,
                    'frequency': ns.frequency,
                    'send_time': ns.send_time.isoformat() if ns.send_time else None,
                    'include_charts': ns.include_charts,
                    'include_summary': ns.include_summary,
                    'include_technical_analysis': ns.include_technical_analysis,
                    'unsubscribe_token': ns.unsubscribe_token,
                    'created_at': ns.created_at.isoformat() if ns.created_at else None,
                    'updated_at': ns.updated_at.isoformat() if ns.updated_at else None
                } for ns in newsletter_subs]
                
                # 이메일 로그
                email_logs = EmailLog.query.all()
                data['email_logs'] = [{
                    'id': el.id,
                    'user_id': el.user_id,
                    'email_type': el.email_type,
                    'subject': el.subject,
                    'status': el.status,
                    'sent_at': el.sent_at.isoformat() if el.sent_at else None,
                    'error_message': el.error_message
                } for el in email_logs]
                
                # 백업 파일 저장
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"✅ 데이터베이스 백업 완료: {backup_file}")
                logger.info(f"📊 백업된 데이터:")
                for table, items in data.items():
                    logger.info(f"  - {table}: {len(items)}개")
                
                return backup_file
                
        except Exception as e:
            logger.error(f"❌ 데이터베이스 백업 실패: {e}")
            raise
    
    def check_table_exists(self, table_name: str) -> bool:
        """테이블 존재 여부 확인 (SQLite/PostgreSQL 호환)"""
        try:
            with app.app_context():
                with db.engine.connect() as conn:
                    # 데이터베이스 엔진에 따라 다른 쿼리 사용
                    if 'sqlite' in str(db.engine.url).lower():
                        # SQLite용 쿼리
                        result = conn.execute(db.text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"))
                    else:
                        # PostgreSQL용 쿼리
                        result = conn.execute(db.text(f"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename='{table_name}'"))
                    return result.fetchone() is not None
        except Exception:
            return False
    
    def safe_create_tables(self):
        """안전한 테이블 생성 (기존 데이터 보존)"""
        logger.info("🔄 안전한 테이블 생성 시작")
        
        with app.app_context():
            try:
                # 기존 테이블 확인
                existing_tables = []
                table_names = ['users', 'stock_lists', 'stocks', 'analysis_history', 'newsletter_subscriptions', 'email_logs']
                
                for table_name in table_names:
                    if self.check_table_exists(table_name):
                        existing_tables.append(table_name)
                
                if existing_tables:
                    logger.info(f"📋 기존 테이블 발견: {', '.join(existing_tables)}")
                    logger.info("🔄 기존 데이터를 보존하면서 스키마 업데이트 진행")
                else:
                    logger.info("🆕 새로운 데이터베이스 - 전체 테이블 생성")
                
                # 안전한 테이블 생성 (기존 테이블은 그대로 유지)
                db.create_all()
                logger.info("✅ 테이블 생성/업데이트 완료")
                
            except Exception as e:
                logger.error(f"❌ 테이블 생성 실패: {e}")
                raise
    
    def create_initial_data_if_needed(self):
        """필요한 경우에만 초기 데이터 생성"""
        logger.info("🔄 초기 데이터 확인 및 생성")
        
        with app.app_context():
            try:
                # 관리자 계정 확인/생성
                admin_user = User.query.filter_by(username='admin').first()
                if not admin_user:
                    logger.info("👤 관리자 계정 생성 중...")
                    admin_password = os.getenv('ADMIN_PASSWORD', 'CHANGE_ME_IMMEDIATELY_123!')
                    
                    admin_user = User(
                        username='admin',
                        email='admin@example.com',
                        first_name='관리자',
                        last_name='사용자',
                        is_verified=True,
                        is_admin=True
                    )
                    admin_user.set_password(admin_password)
                    db.session.add(admin_user)
                    logger.info("✅ 관리자 계정 생성 완료")
                else:
                    logger.info("ℹ️ 관리자 계정이 이미 존재합니다.")
                
                # 테스트 사용자 확인 (개발 환경에서만)
                if os.getenv('FLASK_DEBUG', 'False').lower() == 'true':
                    test_user = User.query.filter_by(username='testuser').first()
                    if not test_user:
                        logger.info("👤 테스트 사용자 생성 중...")
                        test_user = User(
                            username='testuser',
                            email='test@example.com',
                            first_name='테스트',
                            last_name='사용자',
                            is_verified=True,
                            is_admin=False
                        )
                        test_user.set_password('test123')
                        db.session.add(test_user)
                        logger.info("✅ 테스트 사용자 생성 완료")
                
                db.session.commit()
                logger.info("✅ 초기 데이터 생성 완료")
                
            except Exception as e:
                db.session.rollback()
                logger.error(f"❌ 초기 데이터 생성 실패: {e}")
                raise
    
    def run_migration(self):
        """전체 마이그레이션 실행"""
        logger.info("🚀 데이터베이스 마이그레이션 시작")
        logger.info(f"📋 현재 버전: {self.current_version}")
        logger.info(f"🎯 목표 버전: {self.target_version}")
        
        try:
            # 1. 데이터베이스 백업
            backup_file = self.backup_database()
            
            # 2. 안전한 테이블 생성/업데이트
            self.safe_create_tables()
            
            # 3. 초기 데이터 생성 (필요한 경우만)
            self.create_initial_data_if_needed()
            
            # 4. 버전 업데이트
            self.set_version(self.target_version)
            
            logger.info("✅ 데이터베이스 마이그레이션 완료")
            logger.info(f"📁 백업 파일: {backup_file}")
            
        except Exception as e:
            logger.error(f"❌ 마이그레이션 실패: {e}")
            raise
    
    def check_migration_needed(self) -> bool:
        """마이그레이션 필요 여부 확인"""
        return self.current_version != self.target_version
    
    def get_migration_status(self):
        """마이그레이션 상태 확인"""
        logger.info("📊 데이터베이스 마이그레이션 상태")
        logger.info("=" * 50)
        logger.info(f"현재 버전: {self.current_version}")
        logger.info(f"목표 버전: {self.target_version}")
        logger.info(f"마이그레이션 필요: {'예' if self.check_migration_needed() else '아니오'}")
        
        # 테이블 존재 여부 확인
        table_names = ['users', 'stock_lists', 'stocks', 'analysis_history', 'newsletter_subscriptions', 'email_logs']
        logger.info("\n📋 테이블 상태:")
        for table_name in table_names:
            status = "✅ 존재" if self.check_table_exists(table_name) else "❌ 없음"
            logger.info(f"  {table_name}: {status}")
        
        # 기본 데이터 확인
        with app.app_context():
            try:
                admin_count = User.query.filter_by(is_admin=True).count()
                total_users = User.query.count()
                logger.info(f"\n👥 사용자 현황:")
                logger.info(f"  전체 사용자: {total_users}명")
                logger.info(f"  관리자: {admin_count}명")
            except Exception as e:
                logger.info(f"  사용자 정보 확인 불가: {e}")

def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='데이터베이스 마이그레이션 도구')
    parser.add_argument('action', choices=['status', 'migrate', 'backup'], 
                       help='수행할 작업 선택')
    
    args = parser.parse_args()
    
    migration_manager = DatabaseMigrationManager()
    
    try:
        if args.action == 'status':
            migration_manager.get_migration_status()
        
        elif args.action == 'migrate':
            migration_manager.run_migration()
        
        elif args.action == 'backup':
            backup_file = migration_manager.backup_database()
            print(f"✅ 백업 완료: {backup_file}")
    
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 