import logging
from datetime import datetime, time
from celery import current_task
from celery_app import celery_app
from models import db, User, NewsletterSubscription, Stock, StockList, EmailLog
from services.newsletter_service import newsletter_service
from services.email_service import email_service
# from services.analysis_service import analyze_ticker_internal  # <- 이 줄은 주석 처리 또는 삭제
from services.progress_service import start_batch_progress, update_progress, end_batch_progress, is_stop_requested

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def send_daily_newsletters(self):
    """일일 뉴스레터 발송 태스크"""
    try:
        logger.info("일일 뉴스레터 발송 시작")
        
        # 활성 구독자 중 일일 구독자 찾기
        subscriptions = NewsletterSubscription.query.filter_by(
            is_active=True, 
            frequency='daily'
        ).all()
        
        success_count = 0
        error_count = 0
        
        for subscription in subscriptions:
            try:
                # 사용자 정보 확인
                if not subscription.user or not subscription.user.is_active:
                    continue
                
                # 발송 시간 확인 (현재 시간이 설정된 발송 시간과 일치하는지)
                current_time = datetime.now().time()
                if subscription.send_time and current_time.hour != subscription.send_time.hour:
                    continue
                
                # 뉴스레터 발송
                success = newsletter_service.send_daily_newsletter(subscription.user_id)
                
                if success:
                    success_count += 1
                    logger.info(f"일일 뉴스레터 발송 성공: {subscription.user.email}")
                else:
                    error_count += 1
                    logger.error(f"일일 뉴스레터 발송 실패: {subscription.user.email}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"사용자 {subscription.user_id} 일일 뉴스레터 발송 오류: {e}")
        
        result = f"일일 뉴스레터 발송 완료: 성공 {success_count}건, 실패 {error_count}건"
        logger.info(result)
        
        return {
            'success': True,
            'message': result,
            'success_count': success_count,
            'error_count': error_count
        }
        
    except Exception as e:
        logger.error(f"일일 뉴스레터 발송 태스크 오류: {e}")
        return {
            'success': False,
            'message': str(e)
        }

@celery_app.task(bind=True)
def send_weekly_newsletters(self):
    """주간 뉴스레터 발송 태스크"""
    try:
        logger.info("주간 뉴스레터 발송 시작")
        
        # 활성 구독자 중 주간 구독자 찾기
        subscriptions = NewsletterSubscription.query.filter_by(
            is_active=True, 
            frequency='weekly'
        ).all()
        
        success_count = 0
        error_count = 0
        
        for subscription in subscriptions:
            try:
                # 사용자 정보 확인
                if not subscription.user or not subscription.user.is_active:
                    continue
                
                # 발송 시간 확인
                current_time = datetime.now().time()
                if subscription.send_time and current_time.hour != subscription.send_time.hour:
                    continue
                
                # 뉴스레터 발송
                success = newsletter_service.send_weekly_newsletter(subscription.user_id)
                
                if success:
                    success_count += 1
                    logger.info(f"주간 뉴스레터 발송 성공: {subscription.user.email}")
                else:
                    error_count += 1
                    logger.error(f"주간 뉴스레터 발송 실패: {subscription.user.email}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"사용자 {subscription.user_id} 주간 뉴스레터 발송 오류: {e}")
        
        result = f"주간 뉴스레터 발송 완료: 성공 {success_count}건, 실패 {error_count}건"
        logger.info(result)
        
        return {
            'success': True,
            'message': result,
            'success_count': success_count,
            'error_count': error_count
        }
        
    except Exception as e:
        logger.error(f"주간 뉴스레터 발송 태스크 오류: {e}")
        return {
            'success': False,
            'message': str(e)
        }

@celery_app.task(bind=True)
def send_monthly_newsletters(self):
    """월간 뉴스레터 발송 태스크"""
    try:
        logger.info("월간 뉴스레터 발송 시작")
        
        # 활성 구독자 중 월간 구독자 찾기
        subscriptions = NewsletterSubscription.query.filter_by(
            is_active=True, 
            frequency='monthly'
        ).all()
        
        success_count = 0
        error_count = 0
        
        for subscription in subscriptions:
            try:
                # 사용자 정보 확인
                if not subscription.user or not subscription.user.is_active:
                    continue
                
                # 발송 시간 확인
                current_time = datetime.now().time()
                if subscription.send_time and current_time.hour != subscription.send_time.hour:
                    continue
                
                # 월간 뉴스레터 발송 (별도 메서드 사용)
                success = newsletter_service.send_monthly_newsletter(subscription.user_id)
                
                if success:
                    success_count += 1
                    logger.info(f"월간 뉴스레터 발송 성공: {subscription.user.email}")
                else:
                    error_count += 1
                    logger.error(f"월간 뉴스레터 발송 실패: {subscription.user.email}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"사용자 {subscription.user_id} 월간 뉴스레터 발송 오류: {e}")
        
        result = f"월간 뉴스레터 발송 완료: 성공 {success_count}건, 실패 {error_count}건"
        logger.info(result)
        
        return {
            'success': True,
            'message': result,
            'success_count': success_count,
            'error_count': error_count
        }
        
    except Exception as e:
        logger.error(f"월간 뉴스레터 발송 태스크 오류: {e}")
        return {
            'success': False,
            'message': str(e)
        }

@celery_app.task(bind=True)
def send_newsletter_to_user(self, user_id, newsletter_type='daily'):
    """특정 사용자에게 뉴스레터 발송"""
    try:
        logger.info(f"사용자 {user_id}에게 {newsletter_type} 뉴스레터 발송 시작")
        
        if newsletter_type == 'daily':
            success = newsletter_service.send_daily_newsletter(user_id)
        elif newsletter_type == 'weekly':
            success = newsletter_service.send_weekly_newsletter(user_id)
        else:
            success = newsletter_service.send_daily_newsletter(user_id)
        
        if success:
            logger.info(f"사용자 {user_id} {newsletter_type} 뉴스레터 발송 성공")
            return {'success': True, 'message': '발송 성공'}
        else:
            logger.error(f"사용자 {user_id} {newsletter_type} 뉴스레터 발송 실패")
            return {'success': False, 'message': '발송 실패'}
        
    except Exception as e:
        logger.error(f"사용자 {user_id} {newsletter_type} 뉴스레터 발송 오류: {e}")
        return {'success': False, 'message': str(e)}

@celery_app.task(bind=True)
def send_bulk_newsletters(self, user_ids, newsletter_type='daily'):
    """대량 뉴스레터 발송"""
    try:
        logger.info(f"대량 {newsletter_type} 뉴스레터 발송 시작: {len(user_ids)}명")
        
        success_count = 0
        error_count = 0
        
        for user_id in user_ids:
            try:
                if newsletter_type == 'daily':
                    success = newsletter_service.send_daily_newsletter(user_id)
                elif newsletter_type == 'weekly':
                    success = newsletter_service.send_weekly_newsletter(user_id)
                else:
                    success = newsletter_service.send_daily_newsletter(user_id)
                
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                logger.error(f"사용자 {user_id} 뉴스레터 발송 실패: {e}")
        
        result = f"대량 발송 완료: 성공 {success_count}건, 실패 {error_count}건"
        logger.info(result)
        
        return {
            'success': True,
            'message': result,
            'success_count': success_count,
            'error_count': error_count
        }
        
    except Exception as e:
        logger.error(f"대량 뉴스레터 발송 오류: {e}")
        return {'success': False, 'message': str(e)}

@celery_app.task(name='tasks.run_bulk_analysis_for_user')
def run_bulk_analysis_for_user(user_id, list_ids):
    """
    특정 사용자의 여러 종목 리스트에 포함된 모든 종목을 일괄 분석합니다.
    (기존 user_stock_routes.py의 bulk_generate 로직을 비동기 태스크로 분리)
    """
    from app import app, db
    from services.analysis_service import analyze_ticker_internal  # 함수 내부에서 import

    with app.app_context():
        user = User.query.get(user_id)
        if not user:
            logger.error(f"일괄 분석 태스크 실패: 사용자 ID {user_id}를 찾을 수 없습니다.")
            return

        stock_lists = StockList.query.filter(StockList.user_id == user.id, StockList.id.in_(list_ids)).all()
        if not stock_lists:
            logger.warning(f"사용자 {user.username}에 대해 분석할 리스트를 찾지 못했습니다: {list_ids}")
            return

        all_tickers = []
        for stock_list in stock_lists:
            tickers_in_list = [stock.ticker for stock in stock_list.stocks]
            all_tickers.extend(tickers_in_list)
        
        # 중복 제거
        unique_tickers = sorted(list(set(all_tickers)))
        total_tickers = len(unique_tickers)

        if total_tickers == 0:
            logger.info(f"사용자 {user.username}의 선택된 리스트에 분석할 종목이 없습니다.")
            # 사용자에게 알림을 보내는 로직 추가 가능
            return

        list_names = ", ".join([l.name for l in stock_lists])
        logger.info(f"사용자 '{user.username}'의 리스트 '{list_names}'에 대한 일괄 분석 시작. 총 {total_tickers}개 종목.")
        
        start_batch_progress(user_id, total_tickers, f"Admin bulk job for {user.username}: {list_names}")

        try:
            for i, ticker in enumerate(unique_tickers, 1):
                if is_stop_requested(user_id):
                    logger.info(f"사용자 {user.username}에 의한 작업 중단 요청. {i-1}/{total_tickers} 처리 완료.")
                    break
                
                logger.info(f"분석 중: {i}/{total_tickers} - {ticker} (for user: {user.username})")
                update_progress(user_id, ticker, i, total_tickers, f"Admin bulk job for {user.username}: {list_names}")
                
                # 내부 분석 함수 호출
                analyze_ticker_internal(ticker, user_id=user_id)

            logger.info(f"사용자 {user.username}의 일괄 분석 완료. 총 {i}개 종목 처리.")

        except Exception as e:
            logger.error(f"사용자 {user.username}의 일괄 분석 중 오류 발생: {e}", exc_info=True)
        finally:
            end_batch_progress(user_id)
            # 완료 후 사용자에게 이메일 알림 등 추가 가능 