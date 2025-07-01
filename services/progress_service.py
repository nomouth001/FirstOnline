import logging
import json
import os
from datetime import datetime, timedelta
from utils.file_manager import safe_write_file

# 진행률 파일 경로
PROGRESS_FILE_PATH = "static/debug/current_progress.json"

def _load_progress():
    """진행률 파일에서 현재 상태를 로드합니다."""
    try:
        if os.path.exists(PROGRESS_FILE_PATH):
            with open(PROGRESS_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # start_time을 datetime 객체로 변환
                if data.get("start_time"):
                    data["start_time"] = datetime.fromisoformat(data["start_time"])
                if data.get("estimated_completion"):
                    data["estimated_completion"] = datetime.fromisoformat(data["estimated_completion"])
                return data
    except Exception as e:
        logging.error(f"진행률 파일 로드 실패: {e}")
    
    # 기본값 반환
    return {
        "is_running": False,
        "type": None,
        "current_ticker": None,
        "current_list": None,
        "total_tickers": 0,
        "processed_tickers": 0,
        "start_time": None,
        "estimated_completion": None,
        "stop_requested": False
    }

def _save_progress(progress_data):
    """진행률을 파일에 저장합니다."""
    try:
        # 디렉토리가 없으면 생성
        progress_dir = os.path.dirname(PROGRESS_FILE_PATH)
        if not os.path.exists(progress_dir):
            os.makedirs(progress_dir, exist_ok=True)
            logging.info(f"진행률 디렉토리 생성: {progress_dir}")
        
        # datetime 객체를 문자열로 변환
        save_data = progress_data.copy()
        if save_data.get("start_time"):
            save_data["start_time"] = save_data["start_time"].isoformat()
        if save_data.get("estimated_completion"):
            save_data["estimated_completion"] = save_data["estimated_completion"].isoformat()
        
        json_content = json.dumps(save_data, ensure_ascii=False, indent=2)
        safe_write_file(PROGRESS_FILE_PATH, json_content)
        logging.debug(f"진행률 저장 완료: {PROGRESS_FILE_PATH}")
    except Exception as e:
        logging.error(f"진행률 파일 저장 실패: {e}")

def update_progress(ticker=None, processed=0, total=0, list_name=None):
    """진행상황을 업데이트합니다."""
    current_batch_progress = _load_progress()
    
    logging.info(f"=== Progress Update Called ===")
    logging.info(f"Input params: ticker={ticker}, processed={processed}, total={total}, list_name={list_name}")
    logging.info(f"Current progress before update: {current_batch_progress}")
    
    # 진행 중이 아니면 업데이트하지 않음
    if not current_batch_progress.get("is_running", False):
        logging.warning("진행 중이 아닌 상태에서 업데이트 시도됨")
        return
    
    if ticker:
        current_batch_progress["current_ticker"] = ticker
    if processed >= 0:
        current_batch_progress["processed_tickers"] = processed
    if total > 0:
        current_batch_progress["total_tickers"] = total
    if list_name:
        current_batch_progress["current_list"] = list_name
    
    # 예상 완료 시간 계산
    if current_batch_progress["processed_tickers"] > 0 and current_batch_progress["start_time"]:
        elapsed = (datetime.now() - current_batch_progress["start_time"]).total_seconds()
        avg_time_per_ticker = elapsed / current_batch_progress["processed_tickers"]
        remaining_tickers = current_batch_progress["total_tickers"] - current_batch_progress["processed_tickers"]
        estimated_remaining = avg_time_per_ticker * remaining_tickers
        current_batch_progress["estimated_completion"] = datetime.now() + timedelta(seconds=estimated_remaining)
    
    # 진행상황 저장
    _save_progress(current_batch_progress)
    
    # 진행상황 로깅
    logging.info(f"Progress updated: {current_batch_progress['processed_tickers']}/{current_batch_progress['total_tickers']} - Current: {current_batch_progress['current_ticker']} - List: {current_batch_progress['current_list']}")
    logging.info(f"=== Progress Update Complete ===")

def start_batch_progress(type_name, total_tickers, list_name=None):
    """일괄 처리 시작을 기록합니다."""
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
        "stop_requested": False
    }
    
    _save_progress(current_batch_progress)
    
    logging.info(f"Batch progress initialized and saved: {current_batch_progress}")
    logging.info(f"=== Batch Progress Start Complete ===")

def end_batch_progress():
    """일괄 처리 종료를 기록합니다."""
    current_batch_progress = _load_progress()
    
    logging.info(f"=== Batch Progress End ===")
    logging.info(f"Ending batch progress: {current_batch_progress}")
    
    current_batch_progress = {
        "is_running": False,
        "type": None,
        "current_ticker": None,
        "current_list": None,
        "total_tickers": 0,
        "processed_tickers": 0,
        "start_time": None,
        "estimated_completion": None,
        "stop_requested": False
    }
    
    _save_progress(current_batch_progress)
    
    logging.info(f"Batch progress reset and saved")
    logging.info(f"=== Batch Progress End Complete ===")

def get_current_progress():
    """현재 진행상황을 반환합니다."""
    current_batch_progress = _load_progress()
    
    logging.info(f"Progress check requested. Current status: {current_batch_progress}")
    
    if not current_batch_progress.get("is_running", False):
        return {
            "is_running": False,
            "message": "현재 진행 중인 일괄 처리가 없습니다."
        }
    
    # 진행률 계산
    progress_percentage = 0
    if current_batch_progress["total_tickers"] > 0:
        progress_percentage = (current_batch_progress["processed_tickers"] / current_batch_progress["total_tickers"]) * 100
    
    # 경과 시간 계산
    elapsed_time = None
    if current_batch_progress["start_time"]:
        elapsed = datetime.now() - current_batch_progress["start_time"]
        elapsed_time = str(elapsed).split('.')[0]  # 마이크로초 제거
    
    # 예상 완료 시간
    estimated_completion = None
    if current_batch_progress.get("estimated_completion"):
        estimated_completion = current_batch_progress["estimated_completion"].strftime("%H:%M:%S")
    
    response_data = {
        "is_running": True,
        "type": current_batch_progress["type"],
        "current_ticker": current_batch_progress["current_ticker"],
        "current_list": current_batch_progress["current_list"],
        "total_tickers": current_batch_progress["total_tickers"],
        "processed_tickers": current_batch_progress["processed_tickers"],
        "progress_percentage": round(progress_percentage, 1),
        "elapsed_time": elapsed_time,
        "estimated_completion": estimated_completion
    }
    
    logging.info(f"Progress response: {response_data}")
    return response_data

def request_stop():
    """일괄 처리를 중단하도록 요청합니다."""
    current_batch_progress = _load_progress()
    
    logging.info("=== Stop Requested ===")
    current_batch_progress["stop_requested"] = True
    _save_progress(current_batch_progress)
    logging.info(f"Stop flag set and saved")
    logging.info("=== Stop Request Complete ===")

def is_stop_requested():
    """중단 요청이 있는지 확인합니다."""
    current_batch_progress = _load_progress()
    return current_batch_progress.get("stop_requested", False)

def clear_stop_request():
    """중단 요청을 초기화합니다."""
    current_batch_progress = _load_progress()
    current_batch_progress["stop_requested"] = False
    _save_progress(current_batch_progress)
    
def force_reset_progress():
    """진행률을 강제로 리셋합니다 (디버그 용도)."""
    logging.info("=== Force Reset Progress ===")
    reset_data = {
        "is_running": False,
        "type": None,
        "current_ticker": None,
        "current_list": None,
        "total_tickers": 0,
        "processed_tickers": 0,
        "start_time": None,
        "estimated_completion": None,
        "stop_requested": False
    }
    _save_progress(reset_data)
    logging.info("Progress forcefully reset") 