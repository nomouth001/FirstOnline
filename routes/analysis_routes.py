import os
import csv
import json
import logging
import time
import glob
from datetime import datetime
from flask import Blueprint, request, jsonify, session, render_template, send_from_directory, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from celery.result import AsyncResult

# Models and database
from models import db, Stock, StockList, AnalysisHistory, User, get_stock_list_path, get_analysis_summary_path, _extract_summary_from_analysis

# Services
from services.analysis_service import analyze_ticker_internal, analyze_ticker_internal_logic, is_valid_analysis_file, analyze_ticker_force_new
from services.chart_service import generate_chart
from services.indicator_service import indicator_service
from services.progress_service import start_batch_progress, end_batch_progress, update_progress, get_current_progress, request_stop, is_stop_requested, clear_stop_request
from services.market_data_service import download_from_yahoo_finance
from services.batch_analysis_service import run_single_list_analysis, run_multiple_lists_analysis

# Tasks and Celery
from tasks.newsletter_tasks import run_batch_analysis_task, run_multiple_batch_analysis_task, resume_batch_analysis_task
from celery_app import get_celery_app

# Utils and config
from utils.file_manager import get_date_folder_path, find_latest_analysis_file, get_all_analysis_dates, find_analysis_file_by_date
from utils.timeout_utils import safe_chart_generation, safe_ai_analysis
from config import ANALYSIS_DIR, MULTI_SUMMARY_DIR, CHART_GENERATION_TIMEOUT, AI_ANALYSIS_TIMEOUT

# Blueprint 생성
analysis_bp = Blueprint('analysis', __name__)

# Celery 앱 인스턴스 가져오기 (필요한 경우)
def get_celery_instance():
    """Celery 인스턴스를 지연 로드합니다."""
    return get_celery_app()

# 누락된 함수들 추가
def get_progress():
    """진행 상황을 가져옵니다."""
    return get_current_progress()

def stop_batch():
    """배치 작업을 중단합니다."""
    return request_stop()

@analysis_bp.route("/generate_chart/<ticker>")
def generate_chart_route(ticker):
    try:
        chart_paths = generate_chart(ticker)
        return jsonify(chart_paths), 200
    except Exception as e:
        logging.exception(f"Chart generation failed for {ticker}")
        return jsonify({"error": f"Chart generation failed for {ticker}: {e}"}), 500

@analysis_bp.route("/view_chart/<ticker>")
def view_chart(ticker):
    """차트 보기 - 기존 분석이 있으면 확인 후 새로 생성하거나 기존 파일을 보여줍니다."""
    try:
        ticker = ticker.upper()
        today_date_str = datetime.today().strftime("%Y%m%d")
        
        # 날짜별 폴더 구조 사용
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        
        # 오늘 날짜의 모든 분석 파일 찾기 (타임스탬프 포함)
        today_files = []
        if os.path.exists(analysis_date_folder):
            for file in os.listdir(analysis_date_folder):
                if file.startswith(f"{ticker}_{today_date_str}") and file.endswith(".html"):
                    today_files.append(file)
        
        # 가장 최신 파일 찾기 (타임스탬프 기준)
        latest_file = None
        if today_files:
            # 파일명에서 타임스탬프 추출하여 정렬
            def extract_timestamp(filename):
                # AAPL_20250620_143052.html -> 143052
                parts = filename.replace(f"{ticker}_{today_date_str}_", "").replace(".html", "")
                if "_" in parts:
                    return parts.split("_")[-1]  # 마지막 부분이 타임스탬프
                else:
                    return "000000"  # 타임스탬프가 없으면 가장 오래된 것으로 처리
            
            today_files.sort(key=extract_timestamp, reverse=True)
            latest_file = today_files[0]
        
        # 기존 파일이 있으면 사용자에게 확인 요청
        if latest_file:
            # 기존 파일 경로
            existing_file_path = os.path.join(analysis_date_folder, latest_file)
            
            # 유효성 검사
            if is_valid_analysis_file(existing_file_path):
                # 기존 파일이 유효하면 바로 보여줌
                return send_from_directory(analysis_date_folder, latest_file)
            else:
                # 유효하지 않은 파일이면 삭제하고 새로 생성
                logging.info(f"[{ticker}] Existing analysis file is invalid, will create new one")
                try:
                    os.remove(existing_file_path)
                    logging.info(f"[{ticker}] Removed invalid analysis file: {existing_file_path}")
                except Exception as e:
                    logging.warning(f"[{ticker}] Failed to remove invalid analysis file: {e}")
        
        # 기존 파일이 없거나 유효하지 않으면 새로 생성
        logging.info(f"[{ticker}] No valid analysis file found, creating new one")
        return create_new_analysis_with_timestamp(ticker, analysis_date_folder, today_date_str)
        
    except Exception as e:
        logging.exception(f"Error in view_chart for {ticker}")
        return f"Error: Failed to view chart for {ticker}: {str(e)}", 500

def create_new_analysis_with_timestamp(ticker, analysis_date_folder, today_date_str):
    """타임스탬프를 포함한 새로운 분석 파일을 생성합니다."""
    try:
        # 현재 타임스탬프 생성 (HHMMSS 형식)
        current_timestamp = datetime.now().strftime("%H%M%S")
        
        # 새로운 파일명 생성
        html_file_name = f"{ticker}_{today_date_str}_{current_timestamp}.html"
        analysis_html_path = os.path.join(analysis_date_folder, html_file_name)
        
        # 기존 파일들을 백업 (모든 기존 파일 보존)
        existing_files = []
        if os.path.exists(analysis_date_folder):
            for file in os.listdir(analysis_date_folder):
                if file.startswith(f"{ticker}_{today_date_str}") and file.endswith(".html"):
                    existing_files.append(file)
        
        # 기존 파일들을 백업 (타임스탬프가 없는 파일에만 타임스탬프 추가)
        for existing_file in existing_files:
            # 파일명에서 타임스탬프 부분 추출
            file_without_ext = existing_file.replace(".html", "")
            if file_without_ext == f"{ticker}_{today_date_str}":
                # 타임스탬프가 없는 기존 파일을 백업
                backup_timestamp = datetime.now().strftime("%H%M%S")
                backup_file_name = f"{ticker}_{today_date_str}_{backup_timestamp}.html"
                backup_file_path = os.path.join(analysis_date_folder, backup_file_name)
                
                try:
                    os.rename(
                        os.path.join(analysis_date_folder, existing_file),
                        backup_file_path
                    )
                    logging.info(f"[{ticker}] Backed up existing file: {existing_file} -> {backup_file_name}")
                except Exception as e:
                    logging.warning(f"[{ticker}] Failed to backup existing file {existing_file}: {e}")
            else:
                # 이미 타임스탬프가 있는 파일은 그대로 유지
                logging.info(f"[{ticker}] Existing file with timestamp preserved: {existing_file}")
        
        # 새로운 분석 생성 (기존 파일을 덮어쓰지 않도록 새로운 경로 사용)
        analysis_data, analysis_status_code = analyze_ticker_internal_logic(ticker, analysis_html_path)
        
        if analysis_status_code == 200 and analysis_data.get("success"):
            # 성공한 경우 생성된 HTML 파일 반환
            if os.path.exists(analysis_html_path):
                return send_from_directory(analysis_date_folder, html_file_name)
            else:
                return f"Error: Analysis completed but HTML file not found for {ticker}.", 500
        else:
            return f"Error: Analysis failed for {ticker}: {analysis_data.get('analysis_gemini', 'Unknown error')}", 500
            
    except Exception as e:
        logging.exception(f"Error creating analysis for {ticker}")
        return f"Error: Failed to create analysis for {ticker}: {str(e)}", 500

@analysis_bp.route("/generate_all_charts_and_analysis/<list_name>", methods=['GET', 'POST'])
def generate_all_charts_and_analysis_route(list_name):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        # Celery 백그라운드 작업으로 일괄 분석 실행
        task = run_batch_analysis_task.delay(list_name, current_user.id)
        
        logging.info(f"Batch analysis task started for list: {list_name}, task_id: {task.id}")
        
        return jsonify({
            "success": True,
            "message": f"일괄 분석이 백그라운드에서 시작되었습니다.",
            "task_id": task.id,
            "list_name": list_name
        }), 202  # 202 Accepted - 작업이 수락되었지만 아직 완료되지 않음
        
    except Exception as e:
        logging.exception(f"Error starting batch analysis task for list: {list_name}")
        return jsonify({"error": f"일괄 분석 시작 실패: {str(e)}"}), 500

@analysis_bp.route("/generate_multiple_lists_analysis", methods=["POST"])
def generate_multiple_lists_analysis_route():
    """
    선택된 여러 리스트에 대한 일괄 분석을 실행하는 엔드포인트
    이 함수는 들여쓰기 문제를 방지하기 위해 완전히 재작성되었습니다.
    """
    from flask_login import current_user
    
    # 함수 시작 로그
    logging.info("=== Starting generate_multiple_lists_analysis_route ===")
    
    # 사용자 인증 확인
    if not current_user.is_authenticated:
        logging.warning("Unauthorized access attempt to generate_multiple_lists_analysis")
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        # 요청 데이터 파싱 - 이 부분이 가장 중요합니다
        logging.info("Attempting to parse request JSON data")
        data = request.get_json()
        
        if data is None:
            logging.error("No JSON data received in request")
            return jsonify({"error": "No JSON data provided"}), 400
        
        logging.info(f"Received data: {data}")
        
        # 선택된 리스트 이름들 추출
        list_names = data.get('selected_lists', [])
        if not list_names:
            logging.error("No list names provided in request")
            return jsonify({"error": "No list names provided"}), 400
        
        logging.info(f"Selected lists: {list_names}")
        
        # 여러 리스트 분석을 Celery 백그라운드 작업으로 실행
        logging.info("Starting multiple lists analysis with Celery")
        task = run_multiple_batch_analysis_task.delay(list_names, current_user.id)
        
        logging.info(f"Multiple batch analysis task started for lists: {list_names}, task_id: {task.id}")
        
        return jsonify({
            "success": True,
            "message": f"{len(list_names)}개 리스트의 일괄 분석이 백그라운드에서 시작되었습니다.",
            "task_id": task.id,
            "list_names": list_names
        }), 202  # 202 Accepted - 작업이 수락되었지만 아직 완료되지 않음
        
    except json.JSONDecodeError as e:
        logging.exception("JSON decode error in generate_multiple_lists_analysis_route")
        return jsonify({"error": f"Invalid JSON data: {str(e)}"}), 400
    except Exception as e:
        logging.exception("Unexpected error in generate_multiple_lists_analysis_route")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    finally:
        logging.info("=== Ending generate_multiple_lists_analysis_route ===")

@analysis_bp.route("/get_batch_progress/<list_name>")
def get_batch_progress(list_name):
    """
    현재 진행 중인 일괄 처리의 진행 상황을 반환합니다.
    """
    csv_file_path = get_stock_list_path(list_name)
    if not os.path.exists(csv_file_path):
        return jsonify({"error": f"Stock list '{list_name}' not found."}), 404

    try:
        with open(csv_file_path, newline="", encoding='utf-8') as f:
            reader = csv.DictReader(f)
            total_tickers = len(list(reader))
    except Exception as e:
        return jsonify({"error": f"Failed to read tickers: {e}"}), 500

    # 현재 처리된 종목 수를 확인 (분석 파일이 있는 종목 수)
    processed_count = 0
    today_date_str = datetime.today().strftime("%Y%m%d")
    
    try:
        with open(csv_file_path, newline="", encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row["ticker"]
                html_file_name = f"{ticker}_{today_date_str}.html"
                analysis_html_path = os.path.join(ANALYSIS_DIR, html_file_name)
                if os.path.exists(analysis_html_path):
                    processed_count += 1
    except Exception as e:
        logging.error(f"Error checking processed tickers: {e}")

    progress_percentage = (processed_count / total_tickers * 100) if total_tickers > 0 else 0
    
    return jsonify({
        "total_tickers": total_tickers,
        "processed_tickers": processed_count,
        "progress_percentage": round(progress_percentage, 1),
        "status": "completed" if processed_count >= total_tickers else "in_progress"
    }), 200

def get_ticker_price_change(ticker):
    """티커의 최근 가격 변화율을 계산합니다."""
    try:
        import yfinance as yf
        import time
        from datetime import datetime, timedelta
        
        # 최근 5일간 데이터 가져오기
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)  # 주말 고려해서 10일
        
        # retry 로직 적용
        for attempt in range(3):
            try:
                # yfinance가 자체 세션을 사용하도록 세션 파라미터 제거
                ticker_obj = yf.Ticker(ticker)
                stock_data = ticker_obj.history(start=start_date, end=end_date, auto_adjust=False)
                
                if not stock_data.empty and len(stock_data) >= 2:
                    # 최신 종가와 이전 종가 비교
                    latest_close = stock_data['Close'].iloc[-1]
                    previous_close = stock_data['Close'].iloc[-2]
                    
                    # 변화율 계산 (백분율)
                    change_rate = ((latest_close - previous_close) / previous_close) * 100
                    return round(change_rate, 2)
                else:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    else:
                        return 0.0  # 데이터가 없으면 0% 변화율
                        
            except Exception as e:
                error_msg = str(e).lower()
                if '429' in error_msg or 'rate' in error_msg or 'too many' in error_msg:
                    if attempt < 2:
                        wait_time = 3 * (2 ** attempt)
                        logging.info(f"[{ticker}] Rate limit detected in price change, waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logging.warning(f"Failed to get price change for {ticker}: {e}")
                        return 0.0
                else:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    else:
                        logging.warning(f"Failed to get price change for {ticker}: {e}")
                        return 0.0
        
        return 0.0
        
    except Exception as e:
        logging.warning(f"Failed to get price change for {ticker}: {e}")
        return 0.0

@analysis_bp.route("/get_all_summaries/<list_name>")
def get_all_summaries(list_name):
    from models import _extract_summary_from_analysis
    
    summary_file_path = get_analysis_summary_path(list_name)
    if not os.path.exists(summary_file_path):
        return jsonify({"error": f"No analysis summaries found for list '{list_name}'. Please run 'Generate All Charts & Analysis' first."}), 404
    try:
        with open(summary_file_path, 'r', encoding='utf-8') as f:
            summaries = json.load(f)
        
        # 동적으로 gemini_summary 보정 및 가격 변화율 추가
        for ticker, summary in summaries.items():
            if summary.get("gemini_summary") in ["기존 파일 존재", "데이터 준비 실패", None, ""]:
                latest_summary = load_latest_gemini_summary(ticker)
                if latest_summary:
                    summary["gemini_summary"] = latest_summary
            
            # 기존 gemini_summary를 실시간으로 재추출하여 형식 개선
            original_gemini_summary = summary.get("gemini_summary", "")
            if original_gemini_summary and original_gemini_summary not in ["기존 파일 존재", "데이터 준비 실패", "요약 없음."]:
                try:
                    # models.py의 개선된 함수로 요약 재추출
                    improved_summary = _extract_summary_from_analysis(original_gemini_summary, 3)
                    if improved_summary and improved_summary != "요약 없음.":
                        summary["gemini_summary"] = improved_summary
                except Exception as e:
                    logging.warning(f"Failed to extract improved summary for {ticker}: {e}")
                    # 추출 실패 시 원본 사용
            
            # 가격 변화율 추가
            summary["price_change_rate"] = get_ticker_price_change(ticker)
        
        # 가격 변화율 기준으로 내림차순 정렬 (상승률 높은 순)
        sorted_items = sorted(summaries.items(), 
                            key=lambda x: x[1].get("price_change_rate", 0), 
                            reverse=True)
        
        # 정렬된 순서를 유지하기 위해 특별한 구조로 반환
        result = {}
        for ticker, summary in sorted_items:
            result[ticker] = summary
        
        return jsonify(result), 200
    except Exception as e:
        logging.exception(f"Failed to load summaries for list '{list_name}'")
        return jsonify({"error": f"Failed to load summaries: {e}"}), 500

def load_latest_gemini_summary(ticker):
    try:
        multi_dir = os.path.join("static", "multi_summaries")
        # 날짜별 폴더가 아닌 직접 폴더에서 JSON 파일 검색
        all_jsons = glob.glob(os.path.join(multi_dir, "*.json"))
        latest_file = None
        latest_time = None
        for f in all_jsons:
            mtime = os.path.getmtime(f)
            if latest_time is None or mtime > latest_time:
                latest_time = mtime
                latest_file = f
        if latest_file:
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for list_summaries in data.get("all_summaries", {}).values():
                if ticker in list_summaries:
                    return list_summaries[ticker].get("gemini_summary")
        return None
    except Exception:
        return None

@analysis_bp.route("/get_multiple_lists_summaries", methods=["POST"])
def get_multiple_lists_summaries_route():
    """
    여러 리스트의 기존 요약 데이터를 가져와서 파일로 저장하는 엔드포인트
    """
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        data = request.get_json()
        selected_lists = data.get("selected_lists", [])
        
        logging.info(f"Multiple lists summaries requested for: {selected_lists}")
        
        if not selected_lists:
            return jsonify({"error": "No lists selected."}), 400
        
        all_summaries = {}
        summary_stats = {
            "total_lists": len(selected_lists),
            "lists_with_data": 0,
            "total_tickers": 0,
            "successful_analyses": 0
        }
        
        for list_name in selected_lists:
            summary_file_path = get_analysis_summary_path(list_name)
            logging.info(f"Checking summary file for {list_name}: {summary_file_path}")
            
            if not os.path.exists(summary_file_path):
                logging.warning(f"No analysis summaries found for list '{list_name}'")
                all_summaries[list_name] = {"error": f"No analysis summaries found for list '{list_name}'."}
                continue
            
            try:
                with open(summary_file_path, 'r', encoding='utf-8') as f:
                    summaries = json.load(f)
                
                logging.info(f"Loaded {len(summaries)} summaries for {list_name}")
                
                if summaries:
                    summary_stats["lists_with_data"] += 1
                    summary_stats["total_tickers"] += len(summaries)
                    
                    # 동적으로 gemini_summary 보정 및 가격 변화율 추가
                    for ticker, summary in summaries.items():
                        if summary.get("gemini_summary") in ["기존 파일 존재", "데이터 준비 실패", None, ""]:
                            latest_summary = load_latest_gemini_summary(ticker)
                            if latest_summary:
                                summary["gemini_summary"] = latest_summary
                        
                        # 기존 gemini_summary를 실시간으로 재추출하여 형식 개선
                        original_gemini_summary = summary.get("gemini_summary", "")
                        if original_gemini_summary and original_gemini_summary not in ["기존 파일 존재", "데이터 준비 실패", "요약 없음."]:
                            try:
                                # models.py의 개선된 함수로 요약 재추출
                                improved_summary = _extract_summary_from_analysis(original_gemini_summary, 3)
                                if improved_summary and improved_summary != "요약 없음.":
                                    summary["gemini_summary"] = improved_summary
                            except Exception as e:
                                logging.warning(f"Failed to extract improved summary for {ticker}: {e}")
                                # 추출 실패 시 원본 사용
                        
                        # 가격 변화율 추가
                        summary["price_change_rate"] = get_ticker_price_change(ticker)
                    
                    # 가격 변화율 기준으로 내림차순 정렬 (상승률 높은 순)
                    from collections import OrderedDict
                    sorted_items = sorted(summaries.items(), 
                                        key=lambda x: x[1].get("price_change_rate", 0), 
                                        reverse=True)
                    sorted_summaries = OrderedDict(sorted_items)
                    
                    # 성공한 분석 수 계산
                    for ticker, summary in sorted_summaries.items():
                        gemini_summary = summary.get("gemini_summary", "")
                        if (gemini_summary and 
                            "분석 실패" not in gemini_summary and 
                            "처리 중 오류" not in gemini_summary and
                            "기존 파일 존재" not in gemini_summary and
                            "데이터 준비 실패" not in gemini_summary):
                            summary_stats["successful_analyses"] += 1
                    
                    all_summaries[list_name] = sorted_summaries
                else:
                    all_summaries[list_name] = {"error": f"No data found in summaries for list '{list_name}'."}
                    
            except Exception as e:
                logging.exception(f"Failed to load summaries for list '{list_name}'")
                all_summaries[list_name] = {"error": f"Failed to load summaries: {e}"}
        
        # 전체 통계 계산
        summary_stats["success_rate"] = f"{(summary_stats['successful_analyses']/summary_stats['total_tickers'])*100:.1f}%" if summary_stats['total_tickers'] > 0 else "0%"
        
        # 파일에 데이터 저장 (타임스탬프 포함)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_id = f"multi_summary_{timestamp}_{len(selected_lists)}"
        file_path = os.path.join(MULTI_SUMMARY_DIR, f"{file_id}.json")
        
        # MULTI_SUMMARY_DIR 디렉토리가 없으면 생성
        if not os.path.exists(MULTI_SUMMARY_DIR):
            os.makedirs(MULTI_SUMMARY_DIR)
        
        file_data = {
            "file_id": file_id,
            "all_summaries": all_summaries,
            "summary_stats": summary_stats,
            "selected_lists": selected_lists,
            "created_at": datetime.now().isoformat()
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(file_data, f, ensure_ascii=False, indent=4)
        
        logging.info(f"Multi summary data saved to file: {file_path}")
        
        return jsonify({
            "file_id": file_id,
            "summary_stats": summary_stats
        }), 200
        
    except Exception as e:
        logging.exception("Error in multiple lists summaries")
        return jsonify({"error": f"Failed to load multiple lists summaries: {str(e)}"}), 500

@analysis_bp.route('/chart_analysis/<list_name>/<ticker>')
def chart_analysis(list_name, ticker):
    # 최신 분석 파일 찾기
    latest_analysis_path = find_latest_analysis_file(ticker)
    
    if latest_analysis_path and os.path.exists(latest_analysis_path):
        # 기존 파일이 있으면 유효성 확인
        if is_valid_analysis_file(latest_analysis_path):
            return send_from_directory(os.path.dirname(latest_analysis_path), 
                                     os.path.basename(latest_analysis_path))
        else:
            # 유효하지 않은 파일이면 삭제하고 새로 생성
            logging.info(f"[{ticker}] Existing analysis file is invalid, will create new one")
            try:
                os.remove(latest_analysis_path)
                logging.info(f"[{ticker}] Removed invalid analysis file: {latest_analysis_path}")
            except Exception as e:
                logging.warning(f"[{ticker}] Failed to remove invalid analysis file: {e}")
    
    # 파일이 없거나 유효하지 않으면 새로 생성
    logging.info(f"[{ticker}] No valid analysis file found, creating new one")
    try:
        # 기존 분석 파일 확인 및 유효성 검사
        today_date_str = datetime.today().strftime("%Y%m%d")
        html_file_name = f"{ticker}_{today_date_str}.html"
        
        # 날짜별 폴더 구조 사용
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        analysis_html_path = os.path.join(analysis_date_folder, html_file_name)
        
        # analyze_ticker_internal_logic 직접 호출하여 분석 생성
        analysis_data, analysis_status_code = analyze_ticker_internal_logic(ticker, analysis_html_path)
        
        if analysis_status_code == 200 and analysis_data.get("success"):
            # 성공한 경우 생성된 HTML 파일 반환
            if os.path.exists(analysis_html_path):
                return send_from_directory(analysis_date_folder, html_file_name)
            else:
                return f"Error: Analysis completed but HTML file not found for {ticker}.", 500
        else:
            return f"Error: Analysis failed for {ticker}: {analysis_data.get('analysis_gemini', 'Unknown error')}", 500
            
    except Exception as e:
        logging.exception(f"Error creating analysis for {ticker}")
        return f"Error: Failed to create analysis for {ticker}: {str(e)}", 500

@analysis_bp.route("/get_multi_summary_data/<file_id>")
def get_multi_summary_data(file_id):
    """
    파일에서 여러 리스트 요약 데이터를 가져오는 엔드포인트
    """
    try:
        logging.info(f"Multi summary data requested for file: {file_id}")
        
        file_path = os.path.join(MULTI_SUMMARY_DIR, f"{file_id}.json")
        
        if not os.path.exists(file_path):
            logging.error(f"File {file_path} not found")
            return jsonify({"error": "Summary file not found."}), 404
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logging.info(f"Retrieved data from file {file_id}: {len(data)} items")
        
        return jsonify(data), 200
        
    except Exception as e:
        logging.exception(f"Error getting multi summary data for file {file_id}")
        return jsonify({"error": f"Failed to get summary data: {str(e)}"}), 500

@analysis_bp.route("/get_latest_multi_summary")
def get_latest_multi_summary():
    """
    가장 최근의 여러 리스트 요약 파일을 찾아서 반환하는 엔드포인트
    """
    try:
        if not os.path.exists(MULTI_SUMMARY_DIR):
            return jsonify({"error": "No summary files found."}), 404
        
        # multi_summary_로 시작하는 모든 JSON 파일 찾기
        summary_files = [f for f in os.listdir(MULTI_SUMMARY_DIR) 
                        if f.startswith("multi_summary_") and f.endswith(".json")]
        
        if not summary_files:
            return jsonify({"error": "No summary files found."}), 404
        
        # 가장 최근 파일 찾기 (파일명의 타임스탬프 기준)
        latest_file = max(summary_files, key=lambda x: x.split('_')[2])  # 타임스탬프 부분
        
        file_id = latest_file.replace('.json', '')
        file_path = os.path.join(MULTI_SUMMARY_DIR, latest_file)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logging.info(f"Retrieved latest multi summary data: {file_id}")
        
        return jsonify({
            "file_id": file_id,
            "data": data
        }), 200
        
    except Exception as e:
        logging.exception("Error getting latest multi summary")
        return jsonify({"error": f"Failed to get latest summary: {str(e)}"}), 500

@analysis_bp.route("/get_analysis_dates/<ticker>")
def get_analysis_dates(ticker):
    """
    특정 종목의 분석 기록 날짜들을 반환하는 엔드포인트
    """
    try:
        ticker = ticker.upper()
        dates = get_all_analysis_dates(ticker)
        return jsonify(dates), 200
        
    except Exception as e:
        logging.exception("Error getting analysis dates")
        return jsonify({"error": f"Failed to get analysis dates: {str(e)}"}), 500

@analysis_bp.route("/get_analysis_by_date/<ticker>/<date_str>")
def get_analysis_by_date(ticker, date_str):
    """
    특정 날짜의 분석 결과를 반환하는 엔드포인트
    """
    try:
        ticker = ticker.upper()
        analysis_html_path = find_analysis_file_by_date(ticker, date_str)
        
        if analysis_html_path:
            return send_from_directory(os.path.dirname(analysis_html_path), 
                                     os.path.basename(analysis_html_path))
        else:
            return jsonify({"error": f"Analysis for {ticker} on {date_str} not found."}), 404
        
    except Exception as e:
        logging.exception("Error getting analysis by date")
        return jsonify({"error": f"Failed to get analysis: {str(e)}"}), 500

@analysis_bp.route("/get_current_progress")
def get_current_progress_route():
    """
    현재 진행상황을 반환하는 엔드포인트
    """
    try:
        progress_data = get_current_progress()
        return jsonify(progress_data), 200
        
    except Exception as e:
        logging.exception("Error getting current progress")
        return jsonify({"error": f"Failed to get progress: {str(e)}"}), 500

@analysis_bp.route("/check_existing_analysis/<ticker>")
def check_existing_analysis(ticker):
    """기존 분석 파일이 있는지 확인하고 사용자에게 선택권을 제공합니다."""
    try:
        ticker = ticker.upper()
        today_date_str = datetime.today().strftime("%Y%m%d")
        
        # 날짜별 폴더 구조 사용
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        
        # 오늘 날짜의 모든 분석 파일 찾기 (타임스탬프 포함)
        today_files = []
        if os.path.exists(analysis_date_folder):
            for file in os.listdir(analysis_date_folder):
                if file.startswith(f"{ticker}_{today_date_str}") and file.endswith(".html"):
                    today_files.append(file)
        
        # 가장 최신 파일 찾기 (타임스탬프 기준)
        latest_file = None
        if today_files:
            def extract_timestamp(filename):
                parts = filename.replace(f"{ticker}_{today_date_str}_", "").replace(".html", "")
                if "_" in parts:
                    return parts.split("_")[-1]
                else:
                    return "000000"
            
            today_files.sort(key=extract_timestamp, reverse=True)
            latest_file = today_files[0]
        
        if latest_file:
            # 기존 파일이 있으면 확인 요청
            existing_file_path = os.path.join(analysis_date_folder, latest_file)
            if is_valid_analysis_file(existing_file_path):
                return jsonify({
                    "exists": True,
                    "file_path": existing_file_path,
                    "message": f"{ticker} 종목의 {today_date_str} 분석 파일이 이미 존재합니다. 새로 생성하시겠습니까?",
                    "ticker": ticker,
                    "date": today_date_str,
                    "latest_file": latest_file
                }), 200
            else:
                # 유효하지 않은 파일이면 새로 생성
                return jsonify({
                    "exists": False,
                    "message": f"{ticker} 종목의 기존 분석 파일이 유효하지 않습니다. 새로 생성합니다.",
                    "ticker": ticker,
                    "date": today_date_str
                }), 200
        else:
            # 기존 파일이 없으면 바로 분석 진행
            return jsonify({
                "exists": False,
                "message": f"{ticker} 종목의 분석 파일이 없습니다. 새로 생성합니다.",
                "ticker": ticker,
                "date": today_date_str
            }), 200
            
    except Exception as e:
        logging.exception(f"Error checking existing analysis for {ticker}")
        return jsonify({"error": f"Error checking existing analysis: {e}"}), 500

@analysis_bp.route("/force_new_analysis/<ticker>")
def force_new_analysis(ticker):
    """기존 파일을 무시하고 강제로 새로운 분석을 생성합니다."""
    try:
        ticker = ticker.upper()
        today_date_str = datetime.today().strftime("%Y%m%d")
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        
        # 타임스탬프가 포함된 새로운 분석 생성
        return create_new_analysis_with_timestamp(ticker, analysis_date_folder, today_date_str)
        
    except Exception as e:
        logging.exception(f"Force new analysis failed for {ticker}")
        return jsonify({"error": f"Force new analysis failed for {ticker}: {e}"}), 500

@analysis_bp.route("/stop_batch_processing", methods=["POST"])
def stop_batch_processing():
    """일괄 처리를 중단하도록 요청합니다."""
    try:
        request_stop()
        logging.info("Batch processing stop requested by user")
        return jsonify({"message": "일괄 처리가 중단 요청되었습니다. 현재 처리 중인 종목이 완료되면 중단됩니다."}), 200
    except Exception as e:
        logging.exception("Error requesting batch stop")
        return jsonify({"error": f"중단 요청 실패: {str(e)}"}), 500

@analysis_bp.route("/task_status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    """Celery 작업의 상태를 확인합니다."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        task = get_celery_instance().AsyncResult(task_id)
        
        if task.state == 'PENDING':
            response = {
                'state': task.state,
                'status': '작업이 대기 중입니다...'
            }
        elif task.state == 'PROGRESS':
            response = {
                'state': task.state,
                'current': task.info.get('current', 0),
                'total': task.info.get('total', 1),
                'status': task.info.get('status', '')
            }
        elif task.state == 'SUCCESS':
            response = {
                'state': task.state,
                'result': task.info
            }
        else:  # FAILURE
            response = {
                'state': task.state,
                'error': str(task.info)
            }
        
        return jsonify(response)
        
    except Exception as e:
        logging.exception(f"Error getting task status for task_id: {task_id}")
        return jsonify({"error": f"작업 상태 확인 실패: {str(e)}"}), 500

@analysis_bp.route("/cancel_task/<task_id>", methods=["POST"])
def cancel_task(task_id):
    """Celery 작업을 취소합니다."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        get_celery_instance().control.revoke(task_id, terminate=True)
        logging.info(f"Task cancelled: {task_id}")
        return jsonify({"message": "작업이 취소되었습니다."}), 200
            
    except Exception as e:
        logging.exception(f"Error cancelling task: {task_id}")
        return jsonify({"error": f"작업 취소 실패: {str(e)}"}), 500

@analysis_bp.route("/resume_batch/<batch_id>", methods=["POST"])
def resume_batch_analysis(batch_id):
    """중단된 배치 분석을 재시작합니다."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        # 배치 상태 확인
        from utils.batch_recovery import get_recovery_manager
        recovery_manager = get_recovery_manager()
        batch_state = recovery_manager.load_batch_state(batch_id)
        
        if not batch_state:
            return jsonify({"error": "배치 상태를 찾을 수 없습니다."}), 404
        
        # 사용자 권한 확인
        if not current_user.is_admin and batch_state.user_id != current_user.id:
            return jsonify({"error": "권한이 없습니다."}), 403
        
        # 재시작 가능한 상태인지 확인
        if batch_state.status in ['completed', 'running']:
            return jsonify({"error": f"배치가 이미 {batch_state.status} 상태입니다."}), 400
        
        # Celery 작업으로 재시작
        task = resume_batch_analysis_task.delay(batch_id)
        
        logging.info(f"Batch analysis resume task started: {batch_id}, task_id: {task.id}")
        
        return jsonify({
            "success": True,
            "message": f"배치 분석 재시작이 백그라운드에서 시작되었습니다.",
            "task_id": task.id,
            "batch_id": batch_id
        }), 202
        
    except Exception as e:
        logging.exception(f"Error resuming batch analysis: {batch_id}")
        return jsonify({"error": f"배치 재시작 실패: {str(e)}"}), 500

@analysis_bp.route("/batch_status/<batch_id>", methods=["GET"])
def get_batch_status(batch_id):
    """배치 상태를 확인합니다."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        from utils.batch_recovery import get_batch_status
        status = get_batch_status(batch_id)
        
        return jsonify(status)
        
    except Exception as e:
        logging.exception(f"Error getting batch status: {batch_id}")
        return jsonify({"error": f"배치 상태 확인 실패: {str(e)}"}), 500

@analysis_bp.route("/recoverable_batches", methods=["GET"])
def get_recoverable_batches():
    """복구 가능한 배치 목록을 반환합니다."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        from utils.batch_recovery import check_and_recover_batches, get_recovery_manager
        
        recovery_manager = get_recovery_manager()
        recoverable_batches = recovery_manager.get_recoverable_batches()
        
        # 사용자 권한에 따라 필터링
        user_batches = []
        for batch_state in recoverable_batches:
            if current_user.is_admin or batch_state.user_id == current_user.id:
                user_batches.append(batch_state.to_dict())
        
        return jsonify({
            "recoverable_batches": user_batches,
            "count": len(user_batches)
        })
        
    except Exception as e:
        logging.exception("Error getting recoverable batches")
        return jsonify({"error": f"복구 가능한 배치 조회 실패: {str(e)}"}), 500

@analysis_bp.route("/force_new_analysis_with_timestamp/<ticker>")
def force_new_analysis_with_timestamp(ticker):
    """타임스탬프를 포함한 새로운 분석을 강제로 생성하고 HTML 페이지를 반환합니다."""
    try:
        ticker = ticker.upper()
        today_date_str = datetime.today().strftime("%Y%m%d")
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        
        return create_new_analysis_with_timestamp(ticker, analysis_date_folder, today_date_str)
        
    except Exception as e:
        logging.exception(f"Force new analysis with timestamp failed for {ticker}")
        return f"Error: Force new analysis failed for {ticker}: {e}", 500

@analysis_bp.route("/get_indicator_data/<ticker>")
def get_indicator_data(ticker):
    """지표 데이터와 크로스오버 정보를 반환하는 API"""
    try:
        ticker = ticker.upper()
        
        # 최신 지표 데이터 가져오기 (최근 1개 데이터만)
        daily_ohlcv = indicator_service.get_latest_indicator_data(ticker, "ohlcv", "d", rows=1)
        daily_ema5 = indicator_service.get_latest_indicator_data(ticker, "ema5", "d", rows=1)
        daily_ema20 = indicator_service.get_latest_indicator_data(ticker, "ema20", "d", rows=1)
        daily_ema40 = indicator_service.get_latest_indicator_data(ticker, "ema40", "d", rows=1)
        daily_macd = indicator_service.get_latest_indicator_data(ticker, "macd", "d", rows=1)
        daily_bollinger = indicator_service.get_latest_indicator_data(ticker, "bollinger", "d", rows=1)
        daily_rsi = indicator_service.get_latest_indicator_data(ticker, "rsi", "d", rows=1)
        daily_stochastic = indicator_service.get_latest_indicator_data(ticker, "stochastic", "d", rows=1)
        daily_volume_5d = indicator_service.get_latest_indicator_data(ticker, "volume_ratio_5d", "d", rows=1)
        daily_volume_20d = indicator_service.get_latest_indicator_data(ticker, "volume_ratio_20d", "d", rows=1)
        
        # 크로스오버 감지
        daily_crossovers = indicator_service.detect_crossovers(ticker, "d", days_back=30)
        weekly_crossovers = indicator_service.detect_crossovers(ticker, "w", days_back=30)
        
        # 데이터가 없으면 오류 반환
        if daily_ohlcv is None or len(daily_ohlcv) == 0:
            return jsonify({"error": f"No indicator data found for {ticker}"}), 404
        
        # 최신 데이터 추출
        latest_data = {}
        latest_date = daily_ohlcv.index[-1].strftime('%Y-%m-%d')
        
        # OHLCV 데이터
        latest_data['date'] = latest_date
        latest_data['close'] = round(daily_ohlcv['Close'].iloc[-1], 2)
        latest_data['volume'] = int(daily_ohlcv['Volume'].iloc[-1])
        
        # EMA 데이터
        if daily_ema5 is not None and len(daily_ema5) > 0:
            latest_data['ema5'] = round(daily_ema5['EMA'].iloc[-1], 2)
        if daily_ema20 is not None and len(daily_ema20) > 0:
            latest_data['ema20'] = round(daily_ema20['EMA'].iloc[-1], 2)
        if daily_ema40 is not None and len(daily_ema40) > 0:
            latest_data['ema40'] = round(daily_ema40['EMA'].iloc[-1], 2)
        
        # MACD 데이터
        if daily_macd is not None and len(daily_macd) > 0:
            latest_data['macd'] = round(daily_macd['MACD'].iloc[-1], 4)
            latest_data['macd_signal'] = round(daily_macd['MACD_Signal'].iloc[-1], 4)
            latest_data['macd_histogram'] = round(daily_macd['MACD_Histogram'].iloc[-1], 4)
        
        # 볼린저 밴드 데이터
        if daily_bollinger is not None and len(daily_bollinger) > 0:
            latest_data['bb_upper'] = round(daily_bollinger['BB_Upper'].iloc[-1], 2)
            latest_data['bb_lower'] = round(daily_bollinger['BB_Lower'].iloc[-1], 2)
            latest_data['bb_middle'] = round(daily_bollinger['BB_Middle'].iloc[-1], 2)
        
        # RSI 데이터
        if daily_rsi is not None and len(daily_rsi) > 0:
            latest_data['rsi'] = round(daily_rsi['RSI'].iloc[-1], 2)
        
        # 스토캐스틱 데이터
        if daily_stochastic is not None and len(daily_stochastic) > 0:
            latest_data['stoch_k'] = round(daily_stochastic['Stoch_K'].iloc[-1], 2)
            latest_data['stoch_d'] = round(daily_stochastic['Stoch_D'].iloc[-1], 2)
        
        # 거래량 비율 데이터
        if daily_volume_5d is not None and len(daily_volume_5d) > 0:
            latest_data['volume_ratio_5d'] = round(daily_volume_5d['Volume_Ratio_5d'].iloc[-1], 2)
        if daily_volume_20d is not None and len(daily_volume_20d) > 0:
            latest_data['volume_ratio_20d'] = round(daily_volume_20d['Volume_Ratio_20d'].iloc[-1], 2)
        
        # 크로스오버 데이터 처리
        crossover_data = {}
        
        if daily_crossovers:
            if 'macd' in daily_crossovers:
                macd_cross = daily_crossovers['macd']
                crossover_data['daily_macd'] = {
                    'date': macd_cross['date'].strftime('%Y-%m-%d'),
                    'type': macd_cross['type'],
                    'macd': round(float(macd_cross['macd']), 4),
                    'signal': round(float(macd_cross['signal']), 4)
                }
            
            if 'ema' in daily_crossovers:
                ema_cross = daily_crossovers['ema']
                crossover_data['daily_ema'] = {
                    'date': ema_cross['date'].strftime('%Y-%m-%d'),
                    'type': ema_cross['type'],
                    'ema5': round(float(ema_cross['ema5']), 2),
                    'ema20': round(float(ema_cross['ema20']), 2),
                    'ema40': round(float(ema_cross['ema40']), 2)
                }
        
        if weekly_crossovers:
            if 'macd' in weekly_crossovers:
                macd_cross = weekly_crossovers['macd']
                crossover_data['weekly_macd'] = {
                    'date': macd_cross['date'].strftime('%Y-%m-%d'),
                    'type': macd_cross['type'],
                    'macd': round(float(macd_cross['macd']), 4),
                    'signal': round(float(macd_cross['signal']), 4)
                }
            
            if 'ema' in weekly_crossovers:
                ema_cross = weekly_crossovers['ema']
                crossover_data['weekly_ema'] = {
                    'date': ema_cross['date'].strftime('%Y-%m-%d'),
                    'type': ema_cross['type'],
                    'ema5': round(float(ema_cross['ema5']), 2),
                    'ema20': round(float(ema_cross['ema20']), 2),
                    'ema40': round(float(ema_cross['ema40']), 2)
                }
        
        return jsonify({
            'ticker': ticker,
            'latest_data': latest_data,
            'crossovers': crossover_data
        }), 200
        
    except Exception as e:
        logging.exception(f"Error getting indicator data for {ticker}")
        return jsonify({"error": f"Failed to get indicator data for {ticker}: {str(e)}"}), 500

