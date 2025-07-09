import logging
from datetime import datetime, timedelta

# 실시간 진행상황 추적을 위한 전역 변수
current_batch_progress = {
    "is_running": False,
    "type": None,  # "single" 또는 "multiple"
    "current_ticker": None,
    "current_list": None,
    "total_tickers": 0,
    "processed_tickers": 0,
    "start_time": None,
    "estimated_completion": None,
    "stop_requested": False  # 중단 요청 플래그 추가
}

def update_progress(ticker=None, processed=0, total=0, list_name=None):
    """진행상황을 업데이트합니다."""
    global current_batch_progress
    
    try:
        logging.info(f"=== Progress Update Called ===")
        logging.info(f"Input params: ticker={ticker}, processed={processed}, total={total}, list_name={list_name}")
        logging.info(f"Current progress before update: {current_batch_progress}")
        
        # 유효성 검사
        if processed < 0:
            processed = 0
        if total < 0:
            total = 0
        if processed > total and total > 0:
            logging.warning(f"Processed ({processed}) > Total ({total}), adjusting processed to total")
            processed = total
        
        # 안전한 업데이트
        if ticker:
            current_batch_progress["current_ticker"] = str(ticker)
        if processed >= 0:
            current_batch_progress["processed_tickers"] = processed
        if total > 0:
            current_batch_progress["total_tickers"] = total
        if list_name:
            current_batch_progress["current_list"] = str(list_name)
        
        # 예상 완료 시간 계산
        try:
            if (current_batch_progress.get("processed_tickers", 0) > 0 and 
                current_batch_progress.get("start_time") and
                current_batch_progress.get("total_tickers", 0) > 0):
                
                start_time = current_batch_progress["start_time"]
                elapsed = (datetime.now() - start_time).total_seconds()
                processed_count = current_batch_progress["processed_tickers"]
                total_count = current_batch_progress["total_tickers"]
                
                if elapsed > 0 and processed_count > 0:
                    avg_time_per_ticker = elapsed / processed_count
                    remaining_tickers = total_count - processed_count
                    
                    if remaining_tickers > 0:
                        estimated_remaining = avg_time_per_ticker * remaining_tickers
                        current_batch_progress["estimated_completion"] = datetime.now() + timedelta(seconds=estimated_remaining)
                    else:
                        current_batch_progress["estimated_completion"] = datetime.now()
        except Exception as e:
            logging.warning(f"Failed to calculate estimated completion time: {e}")
            current_batch_progress["estimated_completion"] = None
        
        logging.info(f"Progress updated successfully: {current_batch_progress}")
        
    except Exception as e:
        logging.error(f"Error in update_progress: {e}", exc_info=True)
        # 오류 발생 시에도 최소한의 업데이트는 시도
        try:
            if ticker:
                current_batch_progress["current_ticker"] = str(ticker)
            if processed >= 0:
                current_batch_progress["processed_tickers"] = max(0, processed)
        except:
            pass

def start_batch_progress(type_name, total_tickers, list_name=None):
    """일괄 처리 시작을 기록합니다."""
    global current_batch_progress
    
    logging.info(f"=== Batch Progress Start ===")
    logging.info(f"Starting batch: type={type_name}, total_tickers={total_tickers}, list_name={list_name}")
    
    current_batch_progress = {
        "is_running": True,
        "type": type_name,
        "current_ticker": None,
        "current_list": list_name,
        "total_tickers": total_tickers,
        "processed_tickers": 0,
        "start_time": datetime.now(),
        "estimated_completion": None,
        "stop_requested": False  # 중단 요청 초기화
    }
    
    logging.info(f"Batch progress initialized: {current_batch_progress}")
    logging.info(f"=== Batch Progress Start Complete ===")

def end_batch_progress():
    """일괄 처리 종료를 기록합니다."""
    global current_batch_progress
    
    logging.info(f"=== Batch Progress End ===")
    logging.info(f"Ending batch progress: {current_batch_progress}")
    
    current_batch_progress["is_running"] = False
    current_batch_progress["type"] = None
    current_batch_progress["current_ticker"] = None
    current_batch_progress["current_list"] = None
    current_batch_progress["total_tickers"] = 0
    current_batch_progress["processed_tickers"] = 0
    current_batch_progress["start_time"] = None
    current_batch_progress["estimated_completion"] = None
    current_batch_progress["stop_requested"] = False  # 중단 요청 초기화
    
    logging.info(f"Batch progress reset: {current_batch_progress}")
    logging.info(f"=== Batch Progress End Complete ===")

def get_current_progress():
    """현재 진행상황을 반환합니다."""
    global current_batch_progress
    
    try:
        logging.info(f"Progress check requested. Current status: {current_batch_progress}")
        
        if not current_batch_progress.get("is_running", False):
            return {
                "is_running": False,
                "message": "현재 진행 중인 일괄 처리가 없습니다."
            }
        
        # 안전한 데이터 추출 (기본값 제공)
        total_tickers = current_batch_progress.get("total_tickers", 0)
        processed_tickers = current_batch_progress.get("processed_tickers", 0)
        
        # 진행률 계산 (0으로 나누기 방지)
        progress_percentage = 0
        if total_tickers > 0:
            progress_percentage = (processed_tickers / total_tickers) * 100
        
        # 경과 시간 계산
        elapsed_time = None
        start_time = current_batch_progress.get("start_time")
        if start_time:
            try:
                elapsed = datetime.now() - start_time
                elapsed_time = str(elapsed).split('.')[0]  # 마이크로초 제거
            except Exception as e:
                logging.warning(f"Failed to calculate elapsed time: {e}")
                elapsed_time = "계산 불가"
        
        # 예상 완료 시간
        estimated_completion = None
        estimated_completion_time = current_batch_progress.get("estimated_completion")
        if estimated_completion_time:
            try:
                estimated_completion = estimated_completion_time.strftime("%H:%M:%S")
            except Exception as e:
                logging.warning(f"Failed to format estimated completion time: {e}")
                estimated_completion = "계산 불가"
        
        response_data = {
            "is_running": True,
            "type": current_batch_progress.get("type", "unknown"),
            "current_ticker": current_batch_progress.get("current_ticker", "준비 중"),
            "current_list": current_batch_progress.get("current_list", ""),
            "total_tickers": total_tickers,
            "processed_tickers": processed_tickers,
            "progress_percentage": round(progress_percentage, 1),
            "elapsed_time": elapsed_time,
            "estimated_completion": estimated_completion,
            "stop_requested": current_batch_progress.get("stop_requested", False)
        }
        
        logging.info(f"Progress response: {response_data}")
        return response_data
        
    except Exception as e:
        logging.error(f"Error in get_current_progress: {e}", exc_info=True)
        # 오류 발생 시 안전한 기본 응답 반환
        return {
            "is_running": False,
            "message": "진행률 조회 중 오류가 발생했습니다.",
            "error": str(e)
        }

def request_stop():
    """일괄 처리를 중단하도록 요청합니다."""
    global current_batch_progress
    
    logging.info("=== Stop Requested ===")
    current_batch_progress["stop_requested"] = True
    logging.info(f"Stop flag set: {current_batch_progress}")
    logging.info("=== Stop Request Complete ===")

def is_stop_requested():
    """중단 요청이 있는지 확인합니다."""
    global current_batch_progress
    return current_batch_progress.get("stop_requested", False)

def clear_stop_request():
    """중단 요청을 초기화합니다."""
    global current_batch_progress
    current_batch_progress["stop_requested"] = False 