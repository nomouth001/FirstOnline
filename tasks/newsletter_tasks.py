import logging
from datetime import datetime, time
from celery import current_task
from celery_app import celery_app
from models import db, User, NewsletterSubscription, Stock, StockList, EmailLog
from services.newsletter_service import newsletter_service
from services.email_service import email_service
# from services.analysis_service import analyze_ticker_internal  # <- 이 줄은 주석 처리 또는 삭제
from services.progress_service import start_batch_progress, update_progress, end_batch_progress, is_stop_requested
from services.batch_analysis_service import _process_tickers_batch
from app import create_app  # <--- 이 부분을 추가합니다.

# Flask 앱 인스턴스 생성
flask_app = create_app()

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

 

@celery_app.task(bind=True)
def run_batch_analysis_task(self, list_name, user_id):
    """지정된 주식 목록에 대한 일괄 분석을 실행하는 Celery 태스크"""
    logger.info(f"Starting batch analysis task for list: {list_name}, user: {user_id}")
    try:
        with flask_app.app_context():  # <--- current_app 대신 flask_app을 사용합니다.
            user = User.query.get(user_id)
            if not user:
                raise ValueError(f"User with id {user_id} not found.")

            stock_list = StockList.query.filter_by(name=list_name, user_id=user_id).first()
            if not stock_list:
                raise ValueError(f"Stock list '{list_name}' not found for user {user_id}.")

            tickers = [stock.ticker for stock in stock_list.stocks]
            if not tickers:
                return {'status': 'Completed', 'message': 'No tickers in the list.'}

            batch_id = start_batch_progress(
                user_id=user_id,
                list_name=list_name,
                total_tickers=len(tickers),
                task_id=self.request.id,
                batch_type='single_list'
            )
            
            # 진행 상황 업데이트 함수 정의
            def update_task_progress(current, total, status_message):
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': current,
                        'total': total,
                        'status': status_message
                    }
                )
            
            # 초기 진행 상황 업데이트
            update_task_progress(0, len(tickers), f"일괄 분석 시작: {list_name}")
            
            # 기존 일괄 분석 로직 실행 (progress_callback 전달)
            success, data, status_code, summaries = _process_tickers_batch(
                tickers, user, list_name, list_name, progress_callback=update_task_progress
            )
            
            if success:
                logger.info(f"Batch analysis completed successfully for list: {list_name}")
                return {
                    "success": True,
                    "message": f"Batch analysis completed for {list_name}",
                    "data": data,
                    "summaries": summaries
                }
            else:
                logger.error(f"Batch analysis failed for list: {list_name}")
                return {
                    "success": False,
                    "error": data.get("error", "Unknown error"),
                    "data": data
                }
                
    except Exception as e:
        logger.exception(f"Error in batch analysis task for list: {list_name}")
        return {"error": f"Task execution failed: {str(e)}"}

@celery_app.task(bind=True)
def run_multiple_batch_analysis_task(self, list_names, user_id):
    """여러 주식 목록에 대한 일괄 분석을 실행하는 Celery 태스크"""
    logger.info(f"Starting multiple batch analysis task for lists: {list_names}, user: {user_id}")
    try:
        with flask_app.app_context(): # <--- current_app 대신 flask_app을 사용합니다.
            user = User.query.get(user_id)
            if not user:
                raise ValueError(f"User with id {user_id} not found.")

            stock_lists = StockList.query.filter(
                StockList.user_id == user_id,
                StockList.name.in_(list_names)
            ).all()

            if not stock_lists:
                raise ValueError(f"No valid stock lists found for user {user_id}.")
            
            results = {}
            all_summaries = {}
            
            for stock_list in stock_lists: # Changed from list_name to stock_list
                logger.info(f"Processing list: {stock_list.name}")
                
                # 개별 리스트 분석 실행
                result = run_batch_analysis_task.apply(args=[stock_list.name, user_id])
                results[stock_list.name] = result.result
                
                # 성공한 경우 요약 정보 수집
                if result.result.get("success") and result.result.get("summaries"):
                    all_summaries.update(result.result["summaries"])
            
            logger.info(f"Multiple batch analysis completed for lists: {list_names}")
            
            return {
                "success": True,
                "message": f"Multiple batch analysis completed for {len(list_names)} lists",
                "results": results,
                "summaries": all_summaries
            }
                
    except Exception as e:
        logger.exception(f"Error in multiple batch analysis task for lists: {list_names}")
        return {"error": f"Task execution failed: {str(e)}"} 

@celery_app.task(bind=True)
def resume_batch_analysis_task(self, batch_id):
    """중단된 일괄 분석 작업을 재개하는 Celery 태스크"""
    logger.info(f"Resuming batch analysis task for batch_id: {batch_id}")
    try:
        with flask_app.app_context(): # <--- current_app 대신 flask_app을 사용합니다.
            from services.batch_analysis_service import get_batch_progress, update_batch_task_id
            
            progress = get_batch_progress(batch_id)
            if not progress or progress['status'] not in ['stopped', 'error']:
                raise ValueError(f"Batch {batch_id} cannot be resumed.")

            update_batch_task_id(batch_id, self.request.id)

            user_id = progress['user_id']
            list_name = progress['list_name']
            
            # 사용자 정보 확인
            user = User.query.get(user_id)
            if not user:
                raise ValueError(f"User with id {user_id} not found.")
            
            # 처리할 종목 리스트 재구성 (이미 처리된 종목 제외)
            remaining_tickers = []
            stock_list = StockList.query.filter_by(name=list_name, user_id=user_id).first()
            if stock_list:
                all_tickers = [stock.ticker for stock in stock_list.stocks]
                # 이미 처리된 종목 제외
                for ticker in all_tickers:
                    if ticker not in progress.get('failed_tickers', []): # Use progress['failed_tickers']
                        # 실제로 분석 파일이 존재하는지 확인
                        from services.analysis_service import is_valid_analysis_file
                        from utils.file_manager import get_date_folder_path
                        from config import ANALYSIS_DIR
                        from datetime import datetime
                        
                        today_date_str = datetime.today().strftime("%Y%m%d")
                        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
                        
                        if not is_valid_analysis_file(ticker, analysis_date_folder):
                            remaining_tickers.append(ticker)
            
            if not remaining_tickers:
                logger.info(f"No remaining tickers to process for batch: {batch_id}")
                # Use progress_manager to mark batch completed
                from services.progress_service import get_progress_manager
                progress_manager = get_progress_manager()
                progress_manager.mark_batch_completed(batch_id, True, "All tickers already processed")
                return {"success": True, "message": "All tickers already processed"}
            
            logger.info(f"Resuming batch with {len(remaining_tickers)} remaining tickers")
            
            # 진행 상황 업데이트 함수 정의
            def update_task_progress(current, total, status_message):
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': progress.get('processed_tickers', 0) + current, # Use progress['processed_tickers']
                        'total': progress.get('total_tickers', 0), # Use progress['total_tickers']
                        'status': status_message
                    }
                )
            
            # 재시작 진행 상황 업데이트
            update_task_progress(0, len(remaining_tickers), f"배치 재시작: {batch_id}")
            
            # 배치 상태 업데이트
            # Use progress_manager to update batch state
            progress_manager = get_progress_manager()
            batch_state = progress_manager.load_batch_state(batch_id)
            if batch_state:
                batch_state.status = 'running'
                batch_state.recovery_count += 1
                progress_manager.save_batch_state(batch_state)
            
            # 남은 종목들 처리
            success, data, status_code, summaries = _process_tickers_batch(
                remaining_tickers, user, batch_id, batch_id, progress_callback=update_task_progress
            )
            
            if success:
                logger.info(f"Batch analysis resumed and completed successfully: {batch_id}")
                # Use progress_manager to mark batch completed
                progress_manager.mark_batch_completed(batch_id, True)
                return {
                    "success": True,
                    "message": f"Batch analysis resumed and completed: {batch_id}",
                    "data": data,
                    "summaries": summaries
                }
            else:
                logger.error(f"Batch analysis resume failed: {batch_id}")
                # Use progress_manager to mark batch completed with error
                progress_manager.mark_batch_completed(batch_id, False, data.get("error", "Unknown error"))
                return {
                    "success": False,
                    "error": data.get("error", "Unknown error"),
                    "data": data
                }
                
    except Exception as e:
        logger.exception(f"Error resuming batch analysis task: {batch_id}")
        return {"error": f"Task resume failed: {str(e)}"} 