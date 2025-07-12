#!/usr/bin/env python3
"""
데이터베이스 동기화 유틸리티
로컬 SQLite와 온라인 PostgreSQL 간의 데이터 동기화를 담당합니다.
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import User, StockList, Stock, AnalysisHistory, NewsletterSubscription, EmailLog

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseSyncManager:
    """데이터베이스 동기화 관리자"""
    
    def __init__(self):
        self.local_db_path = 'app.db'
        self.postgres_url = os.getenv('DATABASE_URL', '').replace('postgres://', 'postgresql://')
        self.sync_tables = [
            'users', 'stock_lists', 'stocks', 'analysis_history', 
            'newsletter_subscriptions', 'email_logs'
        ]
        
    def export_data_to_json(self, target_env='local') -> Dict[str, Any]:
        """데이터베이스 데이터를 JSON으로 내보내기"""
        logger.info(f"🔄 {target_env} 데이터베이스에서 데이터 내보내기 시작")
        
        data = {}
        
        with app.app_context():
            try:
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
                
                # 분석 히스토리 데이터
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
                
                # 뉴스레터 구독 데이터
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
                
                # 이메일 로그 데이터
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
                
                logger.info(f"✅ {target_env} 데이터 내보내기 완료")
                logger.info(f"📊 내보낸 데이터 통계:")
                for table, items in data.items():
                    logger.info(f"  - {table}: {len(items)}개")
                
                return data
                
            except Exception as e:
                logger.error(f"❌ 데이터 내보내기 실패: {e}")
                raise
    
    def import_data_from_json(self, data: Dict[str, Any], target_env='local'):
        """JSON 데이터를 데이터베이스에 가져오기"""
        logger.info(f"🔄 {target_env} 데이터베이스로 데이터 가져오기 시작")
        
        with app.app_context():
            try:
                # 기존 데이터 백업 (필요시)
                backup_data = self.export_data_to_json(target_env)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = f"backup_{target_env}_{timestamp}.json"
                
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)
                logger.info(f"📋 기존 데이터 백업 완료: {backup_file}")
                
                # 데이터 가져오기 (참조 무결성 순서 고려)
                
                # 1. 사용자 데이터 먼저 가져오기
                if 'users' in data:
                    User.query.delete()
                    for user_data in data['users']:
                        user = User(
                            id=user_data['id'],
                            username=user_data['username'],
                            email=user_data['email'],
                            password_hash=user_data['password_hash'],
                            first_name=user_data.get('first_name'),
                            last_name=user_data.get('last_name'),
                            is_active=user_data.get('is_active', True),
                            is_verified=user_data.get('is_verified', False),
                            is_admin=user_data.get('is_admin', False),
                            is_withdrawn=user_data.get('is_withdrawn', False),
                            withdrawn_at=datetime.fromisoformat(user_data['withdrawn_at']) if user_data.get('withdrawn_at') else None,
                            created_at=datetime.fromisoformat(user_data['created_at']) if user_data.get('created_at') else None,
                            updated_at=datetime.fromisoformat(user_data['updated_at']) if user_data.get('updated_at') else None
                        )
                        db.session.add(user)
                
                # 2. 주식 리스트 데이터
                if 'stock_lists' in data:
                    StockList.query.delete()
                    for sl_data in data['stock_lists']:
                        stock_list = StockList(
                            id=sl_data['id'],
                            name=sl_data['name'],
                            description=sl_data.get('description'),
                            is_public=sl_data.get('is_public', False),
                            is_default=sl_data.get('is_default', False),
                            user_id=sl_data['user_id'],
                            created_at=datetime.fromisoformat(sl_data['created_at']) if sl_data.get('created_at') else None,
                            updated_at=datetime.fromisoformat(sl_data['updated_at']) if sl_data.get('updated_at') else None
                        )
                        db.session.add(stock_list)
                
                # 3. 주식 데이터
                if 'stocks' in data:
                    Stock.query.delete()
                    for stock_data in data['stocks']:
                        stock = Stock(
                            id=stock_data['id'],
                            ticker=stock_data['ticker'],
                            name=stock_data.get('name'),
                            stock_list_id=stock_data['stock_list_id'],
                            added_at=datetime.fromisoformat(stock_data['added_at']) if stock_data.get('added_at') else None
                        )
                        db.session.add(stock)
                
                # 4. 분석 히스토리 데이터
                if 'analysis_history' in data:
                    AnalysisHistory.query.delete()
                    for ah_data in data['analysis_history']:
                        analysis_history = AnalysisHistory(
                            id=ah_data['id'],
                            ticker=ah_data['ticker'],
                            analysis_date=datetime.fromisoformat(ah_data['analysis_date']).date() if ah_data.get('analysis_date') else None,
                            analysis_type=ah_data.get('analysis_type', 'daily'),
                            chart_path=ah_data.get('chart_path'),
                            analysis_path=ah_data.get('analysis_path'),
                            summary=ah_data.get('summary'),
                            status=ah_data.get('status', 'completed'),
                            user_id=ah_data['user_id'],
                            created_at=datetime.fromisoformat(ah_data['created_at']) if ah_data.get('created_at') else None
                        )
                        db.session.add(analysis_history)
                
                # 5. 뉴스레터 구독 데이터
                if 'newsletter_subscriptions' in data:
                    NewsletterSubscription.query.delete()
                    for ns_data in data['newsletter_subscriptions']:
                        # send_time 필드 처리: "09:00:00" 형식의 시간 문자열
                        send_time = None
                        if ns_data.get('send_time'):
                            try:
                                # 단순 시간 형식 "HH:MM:SS"
                                send_time = datetime.strptime(ns_data['send_time'], '%H:%M:%S').time()
                            except ValueError:
                                try:
                                    # ISO 형식으로 시도
                                    send_time = datetime.fromisoformat(ns_data['send_time']).time()
                                except ValueError:
                                    logger.warning(f"시간 형식 오류: {ns_data['send_time']}")
                                    send_time = None
                        
                        newsletter_sub = NewsletterSubscription(
                            id=ns_data['id'],
                            user_id=ns_data['user_id'],
                            is_active=ns_data.get('is_active', True),
                            frequency=ns_data.get('frequency', 'daily'),
                            send_time=send_time,
                            include_charts=ns_data.get('include_charts', True),
                            include_summary=ns_data.get('include_summary', True),
                            include_technical_analysis=ns_data.get('include_technical_analysis', True),
                            unsubscribe_token=ns_data.get('unsubscribe_token'),
                            created_at=datetime.fromisoformat(ns_data['created_at']) if ns_data.get('created_at') else None,
                            updated_at=datetime.fromisoformat(ns_data['updated_at']) if ns_data.get('updated_at') else None
                        )
                        db.session.add(newsletter_sub)
                
                # 6. 이메일 로그 데이터
                if 'email_logs' in data:
                    EmailLog.query.delete()
                    for el_data in data['email_logs']:
                        email_log = EmailLog(
                            id=el_data['id'],
                            user_id=el_data['user_id'],
                            email_type=el_data['email_type'],
                            subject=el_data['subject'],
                            status=el_data.get('status', 'sent'),
                            sent_at=datetime.fromisoformat(el_data['sent_at']) if el_data.get('sent_at') else None,
                            error_message=el_data.get('error_message')
                        )
                        db.session.add(email_log)
                
                db.session.commit()
                logger.info(f"✅ {target_env} 데이터 가져오기 완료")
                
            except Exception as e:
                db.session.rollback()
                logger.error(f"❌ 데이터 가져오기 실패: {e}")
                raise
    
    def sync_local_to_remote(self):
        """로컬 데이터베이스를 온라인으로 동기화"""
        logger.info("🔄 로컬 → 온라인 동기화 시작")
        
        # 로컬 데이터 내보내기
        local_data = self.export_data_to_json('local')
        
        # 온라인 환경으로 전환
        original_db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        if self.postgres_url:
            app.config['SQLALCHEMY_DATABASE_URI'] = self.postgres_url
            db.init_app(app)
            
            # 온라인 데이터 가져오기
            self.import_data_from_json(local_data, 'remote')
            
            # 원래 설정 복원
            app.config['SQLALCHEMY_DATABASE_URI'] = original_db_uri
            db.init_app(app)
            
            logger.info("✅ 로컬 → 온라인 동기화 완료")
        else:
            logger.error("❌ DATABASE_URL 환경변수가 설정되지 않음")
    
    def sync_remote_to_local(self):
        """온라인 데이터베이스를 로컬로 동기화"""
        logger.info("🔄 온라인 → 로컬 동기화 시작")
        
        if not self.postgres_url:
            logger.error("❌ DATABASE_URL 환경변수가 설정되지 않음")
            return
        
        # 온라인 환경으로 전환
        original_db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        app.config['SQLALCHEMY_DATABASE_URI'] = self.postgres_url
        db.init_app(app)
        
        # 온라인 데이터 내보내기
        remote_data = self.export_data_to_json('remote')
        
        # 로컬 환경으로 복원
        app.config['SQLALCHEMY_DATABASE_URI'] = original_db_uri
        db.init_app(app)
        
        # 로컬 데이터 가져오기
        self.import_data_from_json(remote_data, 'local')
        
        logger.info("✅ 온라인 → 로컬 동기화 완료")
    
    def compare_databases(self):
        """두 데이터베이스 비교"""
        logger.info("🔍 데이터베이스 비교 시작")
        
        # 로컬 데이터 가져오기
        local_data = self.export_data_to_json('local')
        
        # 온라인 데이터 가져오기
        if self.postgres_url:
            original_db_uri = app.config['SQLALCHEMY_DATABASE_URI']
            app.config['SQLALCHEMY_DATABASE_URI'] = self.postgres_url
            db.init_app(app)
            
            remote_data = self.export_data_to_json('remote')
            
            app.config['SQLALCHEMY_DATABASE_URI'] = original_db_uri
            db.init_app(app)
            
            # 비교 결과 출력
            print("\n📊 데이터베이스 비교 결과:")
            print("=" * 50)
            for table in self.sync_tables:
                local_count = len(local_data.get(table, []))
                remote_count = len(remote_data.get(table, []))
                status = "✅ 동일" if local_count == remote_count else "⚠️ 차이"
                print(f"{table:25} | 로컬: {local_count:3d} | 온라인: {remote_count:3d} | {status}")
        else:
            logger.error("❌ DATABASE_URL 환경변수가 설정되지 않음")

def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='데이터베이스 동기화 도구')
    parser.add_argument('action', choices=['export', 'import', 'sync-to-remote', 'sync-to-local', 'compare'],
                       help='수행할 동작')
    parser.add_argument('--file', help='가져오기/내보내기 파일 경로')
    
    args = parser.parse_args()
    
    sync_manager = DatabaseSyncManager()
    
    try:
        if args.action == 'export':
            data = sync_manager.export_data_to_json()
            file_path = args.file or f"db_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✅ 데이터 내보내기 완료: {file_path}")
        
        elif args.action == 'import':
            if not args.file:
                print("❌ --file 옵션이 필요합니다")
                return
            
            with open(args.file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            sync_manager.import_data_from_json(data)
            print("✅ 데이터 가져오기 완료")
        
        elif args.action == 'sync-to-remote':
            sync_manager.sync_local_to_remote()
        
        elif args.action == 'sync-to-local':
            sync_manager.sync_remote_to_local()
        
        elif args.action == 'compare':
            sync_manager.compare_databases()
    
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 