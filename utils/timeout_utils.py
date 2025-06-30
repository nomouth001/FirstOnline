import threading
import queue
import logging
import time
from functools import wraps

def timeout_wrapper(func, timeout_seconds, func_name="function"):
    """
    함수에 타임아웃을 적용하는 래퍼
    
    Args:
        func: 실행할 함수
        timeout_seconds: 타임아웃 시간 (초)
        func_name: 함수 이름 (로깅용)
    
    Returns:
        함수 실행 결과 또는 None (타임아웃 시)
    """
    result_queue = queue.Queue()
    exception_queue = queue.Queue()
    
    def worker():
        try:
            result = func()
            result_queue.put(result)
        except Exception as e:
            exception_queue.put(e)
    
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout_seconds)
    
    if thread.is_alive():
        logging.error(f"{func_name} timed out after {timeout_seconds} seconds")
        return None
    
    if not exception_queue.empty():
        exception = exception_queue.get()
        logging.error(f"{func_name} failed with exception: {str(exception)}")
        raise exception
    
    return result_queue.get()

def safe_chart_generation(ticker, timeout_seconds=60):
    """
    안전한 차트 생성 함수 (타임아웃 적용)
    """
    from services.chart_service import generate_chart
    
    def chart_func():
        return generate_chart(ticker)
    
    return timeout_wrapper(chart_func, timeout_seconds, f"Chart generation for {ticker}")

def safe_ai_analysis(ticker, timeout_seconds=120):
    """
    안전한 AI 분석 함수 (타임아웃 적용)
    """
    from services.analysis_service import analyze_ticker_internal_logic
    from config import ANALYSIS_DIR
    from utils.file_manager import get_date_folder_path
    from datetime import datetime
    import os
    
    def analysis_func():
        # 분석 파일 경로 설정
        today_date_str = datetime.today().strftime("%Y%m%d")
        html_file_name = f"{ticker}_{today_date_str}.html"
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        analysis_html_path = os.path.join(analysis_date_folder, html_file_name)
        
        return analyze_ticker_internal_logic(ticker, analysis_html_path)
    
    return timeout_wrapper(analysis_func, timeout_seconds, f"AI analysis for {ticker}") 