import os
import csv
import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session, render_template, send_from_directory
from models import get_stock_list_path, get_analysis_summary_path, _extract_summary_from_analysis
from services.chart_service import generate_chart
from services.analysis_service import analyze_ticker_internal, analyze_ticker_internal_logic, is_valid_analysis_file, analyze_ticker_force_new
from services.progress_service import start_batch_progress, end_batch_progress, update_progress, get_current_progress, request_stop, is_stop_requested, clear_stop_request
from config import ANALYSIS_DIR, MULTI_SUMMARY_DIR, CHART_GENERATION_TIMEOUT, AI_ANALYSIS_TIMEOUT
from utils.timeout_utils import safe_chart_generation, safe_ai_analysis
import time
import glob
from utils.file_manager import get_date_folder_path, find_latest_analysis_file, get_all_analysis_dates, find_analysis_file_by_date
from services.batch_analysis_service import run_single_list_analysis, run_multiple_lists_analysis

# Blueprint 생성
analysis_bp = Blueprint('analysis', __name__)

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
    
    success, data, status_code = run_single_list_analysis(list_name, current_user)
    
    if not success:
        return jsonify({"error": data}), status_code
        
    return jsonify(data), status_code

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
        
        # 여러 리스트 분석 실행
        logging.info("Calling run_multiple_lists_analysis")
        success, result_data, status_code = run_multiple_lists_analysis(list_names, current_user)
        
        # 결과 반환
        if not success:
            logging.error(f"Analysis failed: {result_data}")
            return jsonify({"error": result_data}), status_code
        
        logging.info("Analysis completed successfully")
        return jsonify(result_data), status_code
        
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

@analysis_bp.route("/view_existing_chart/<ticker>")
def view_existing_chart(ticker):
    """기존 분석 파일을 보여줍니다."""
    try:
        ticker = ticker.upper()
        today_date_str = datetime.today().strftime("%Y%m%d")
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
            existing_file_path = os.path.join(analysis_date_folder, latest_file)
            if is_valid_analysis_file(existing_file_path):
                return send_from_directory(analysis_date_folder, latest_file)
            else:
                return f"Error: Existing analysis file is invalid for {ticker}.", 500
        else:
            return f"Error: No existing analysis file found for {ticker}.", 404
            
    except Exception as e:
        logging.exception(f"Error viewing existing chart for {ticker}")
        return f"Error: Failed to view existing chart for {ticker}: {str(e)}", 500 
    

# ==================== 파일분할 리팩토링 (롤백을 위해 주석 처리) ====================
# @analysis_bp.route("/generate_all_charts_and_analysis/<list_name>", methods=['GET', 'POST'])
# def generate_all_charts_and_analysis(list_name):
#     from flask_login import current_user
#     from models import StockList, Stock
    
#     if not current_user.is_authenticated:
#         return jsonify({"error": "Authentication required"}), 401
    
#     # 데이터베이스에서 종목 리스트 찾기
#     if current_user.is_administrator():
#         # 어드민은 모든 리스트에 접근 가능
#         stock_list = StockList.query.filter_by(name=list_name).first()
#     else:
#         # 일반 사용자는 자신의 리스트만 접근
#         stock_list = StockList.query.filter_by(name=list_name, user_id=current_user.id).first()
    
#     if not stock_list and list_name == 'default':
#         # default 리스트가 없으면 CSV 파일에서 읽기 (호환성을 위해)
#         csv_file_path = get_stock_list_path(list_name)
#         if os.path.exists(csv_file_path):
#             tickers_to_process = []
#             try:
#                 with open(csv_file_path, newline="", encoding='utf-8') as f:
#                     reader = csv.DictReader(f)
#                     for row in reader:
#                         tickers_to_process.append(row["ticker"])
#             except Exception as e:
#                 logging.exception(f"Failed to read tickers from {list_name}.csv")
#                 return jsonify({"error": f"Failed to read tickers from {list_name}.csv: {e}"}), 500
#         else:
#             return jsonify({"error": f"Stock list '{list_name}' not found."}), 404
#     elif not stock_list:
#         return jsonify({"error": f"Stock list '{list_name}' not found."}), 404
#     else:
#         # 데이터베이스에서 종목들 가져오기
#         stocks = Stock.query.filter_by(stock_list_id=stock_list.id).all()
#         tickers_to_process = [stock.ticker for stock in stocks]

#     if not tickers_to_process:
#         return jsonify({"error": f"No tickers found in list '{list_name}'."}), 400

#     results = []
#     all_summaries = {}
    
#     summary_file_path = get_analysis_summary_path(list_name)
#     total_tickers = len(tickers_to_process)
    
#     # 일괄 처리 시작 기록
#     start_batch_progress("single", total_tickers, list_name)
    
#     logging.info(f"Starting batch processing for {total_tickers} tickers in list '{list_name}'")

#     try:
#         for i, ticker in enumerate(tickers_to_process, 1):
#             # 중단 요청 확인
#             if is_stop_requested():
#                 logging.info(f"Stop requested during processing. Stopping at ticker {i-1}/{total_tickers}")
#                 return jsonify({
#                     "message": f"일괄 처리가 중단되었습니다. {i-1}개 종목이 처리되었습니다.",
#                     "individual_results": results,
#                     "summary": {
#                         "total_tickers": total_tickers,
#                         "processed": i-1,
#                         "stopped": True
#                     }
#                 }), 200
            
#             ticker_start_time = datetime.now()
#             logging.info(f"Processing ticker {i}/{total_tickers}: {ticker} from list: {list_name}")
            
#             # 진행상황 업데이트
#             update_progress(ticker=ticker, processed=i-1, total=total_tickers, list_name=list_name)
            
#             chart_generation_status = None
#             analysis_status = None
            
#             try:
#                 # 1. 차트 생성
#                 chart_start_time = datetime.now()
#                 chart_result = generate_chart(ticker)
#                 chart_duration = (datetime.now() - chart_start_time).total_seconds()
#                 chart_generation_status = "Chart generation succeeded."

#                 # 2. AI 분석 (기존 파일 유효성 확인 후 분석)
#                 analysis_start_time = datetime.now()
                
#                 # 기존 분석 파일 확인 및 유효성 검사
#                 today_date_str = datetime.today().strftime("%Y%m%d")
#                 html_file_name = f"{ticker}_{today_date_str}.html"
                
#                 # 날짜별 폴더 구조 사용
#                 analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
#                 analysis_html_path = os.path.join(analysis_date_folder, html_file_name)
                
#                 # 기존 파일이 있지만 유효하지 않으면 삭제
#                 if os.path.exists(analysis_html_path):
#                     if not is_valid_analysis_file(analysis_html_path):
#                         logging.info(f"[{ticker}] Existing analysis file is invalid, will create new one")
#                         try:
#                             os.remove(analysis_html_path)
#                             logging.info(f"[{ticker}] Removed invalid analysis file: {analysis_html_path}")
#                         except Exception as e:
#                             logging.warning(f"[{ticker}] Failed to remove invalid analysis file: {e}")
                
#                 analysis_data, analysis_status_code = analyze_ticker_internal_logic(ticker, analysis_html_path)
#                 analysis_duration = (datetime.now() - analysis_start_time).total_seconds()
                
#                 if analysis_status_code == 200 and analysis_data.get("success"):
#                     analysis_status = "AI analysis succeeded."
#                     all_summaries[ticker] = {
#                         "gemini_summary": analysis_data.get("summary_gemini", "요약 없음."),
#                         "openai_summary": "OpenAI 분석 비활성화됨",
#                         "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                     }
#                     total_duration = (datetime.now() - ticker_start_time).total_seconds()
#                     logging.info(f"Successfully processed {ticker} ({i}/{total_tickers}) in {total_duration:.2f} seconds")
#                 else:
#                     analysis_status = f"AI analysis failed: {analysis_data.get('analysis_gemini', 'Unknown error')}"
#                     logging.error(f"AI analysis failed for {ticker}: {analysis_status}")
#                     all_summaries[ticker] = {
#                         "gemini_summary": analysis_data.get("summary_gemini", "분석 실패."),
#                         "openai_summary": "OpenAI 분석 비활성화됨",
#                         "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                     }
                
#                 results.append({
#                     "ticker": ticker,
#                     "chart_status": chart_generation_status,
#                     "analysis_status": analysis_status
#                 })
                
#             except Exception as e:
#                 error_msg = f"Unexpected error processing {ticker}: {str(e)}"
#                 logging.exception(error_msg)
#                 results.append({
#                     "ticker": ticker,
#                     "chart_status": "Error",
#                     "analysis_status": error_msg
#                 })
#                 all_summaries[ticker] = {
#                     "gemini_summary": f"처리 중 오류 발생: {str(e)}",
#                     "openai_summary": "OpenAI 분석 비활성화됨",
#                     "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                 }

#         # 모든 종목 처리 후 요약 정보를 JSON 파일로 저장
#         try:
#             with open(summary_file_path, 'w', encoding='utf-8') as f:
#                 json.dump(all_summaries, f, ensure_ascii=False, indent=4)
#             logging.info(f"All summaries for list '{list_name}' saved to {summary_file_path}")
#         except Exception as e:
#             logging.exception(f"Failed to save summaries for list '{list_name}'")
#             return jsonify({"error": f"Failed to save summaries: {e}", "individual_results": results}), 500

#         # 성공/실패 통계 계산
#         success_count = sum(1 for r in results if r.get("chart_status") == "Chart generation succeeded." and r.get("analysis_status") == "AI analysis succeeded.")
#         failed_count = len(results) - success_count
        
#         logging.info(f"Batch processing completed for list '{list_name}': {success_count} successful, {failed_count} failed out of {total_tickers} total")

#         return jsonify({
#             "message": f"Successfully processed all tickers in list '{list_name}'.",
#             "individual_results": results,
#             "summary": {
#                 "total_tickers": total_tickers,
#                 "successful": success_count,
#                 "failed": failed_count,
#                 "success_rate": f"{(success_count/total_tickers)*100:.1f}%" if total_tickers > 0 else "0%"
#             }
#         }), 200
        
#     finally:
#         # 일괄 처리 종료 기록
#         end_batch_progress()
# ==============================================================================



# ==================== 파일분할 리팩토링 (롤백을 위해 주석 처리) ====================
# @analysis_bp.route("/generate_multiple_lists_analysis", methods=["POST"])
# def generate_multiple_lists_analysis():
#     from flask_login import current_user
#     from models import StockList, Stock
    
#     if not current_user.is_authenticated:
#         return jsonify({"error": "Authentication required"}), 401
    
#     try:
#     data = request.get_json()
#         selected_lists = data.get("selected_lists", [])
        
#         if not selected_lists:
#             return jsonify({"error": "No lists selected"}), 400
        
#         all_results = {}
#         all_summaries = {}
#         total_tickers = 0
        
#         # 전체 종목 수 계산 (데이터베이스 우선)
#         for list_name in selected_lists:
#             # 데이터베이스에서 먼저 찾기
#             if current_user.is_administrator():
#                 stock_list = StockList.query.filter_by(name=list_name).first()
#             else:
#                 stock_list = StockList.query.filter_by(name=list_name, user_id=current_user.id).first()
            
#             if stock_list:
#                 stocks = Stock.query.filter_by(stock_list_id=stock_list.id).all()
#                 total_tickers += len(stocks)
#             else:
#                 # CSV 파일에서 백업으로 찾기
#                 csv_file_path = get_stock_list_path(list_name)
#                 if os.path.exists(csv_file_path):
#                     try:
#                         with open(csv_file_path, newline="", encoding='utf-8') as f:
#                             reader = csv.DictReader(f)
#                             tickers = [row["ticker"] for row in reader]
#                             total_tickers += len(tickers)
#                     except Exception as e:
#                         logging.error(f"Failed to count tickers in {list_name}: {e}")
        
#         # 일괄 처리 시작 기록
#         start_batch_progress("multiple", total_tickers, f"{len(selected_lists)}개 리스트")
        
#         processed_count = 0
        
#         try:
#             for list_name in selected_lists:
#                 # 데이터베이스에서 먼저 찾기
#                 if current_user.is_administrator():
#                     stock_list = StockList.query.filter_by(name=list_name).first()
#                 else:
#                     stock_list = StockList.query.filter_by(name=list_name, user_id=current_user.id).first()
                
#                 tickers_to_process = []
                
#                 if stock_list:
#                     # 데이터베이스에서 종목들 가져오기
#                     stocks = Stock.query.filter_by(stock_list_id=stock_list.id).all()
#                     tickers_to_process = [stock.ticker for stock in stocks]
#                 else:
#                     # CSV 파일에서 백업으로 찾기
#                     csv_file_path = get_stock_list_path(list_name)
#                     if os.path.exists(csv_file_path):
#                         try:
#                             with open(csv_file_path, newline="", encoding='utf-8') as f:
#                                 reader = csv.DictReader(f)
#                                 for row in reader:
#                                     tickers_to_process.append(row["ticker"])
#                         except Exception as e:
#                             all_results[list_name] = {"error": f"Failed to read tickers from {list_name}.csv: {e}"}
#                             continue
#                     else:
#                         all_results[list_name] = {"error": f"Stock list '{list_name}' not found."}
#                         continue
                
#                 if not tickers_to_process:
#                     all_results[list_name] = {"error": f"No tickers found in list '{list_name}'."}
#                     continue
                
#                 list_results = []
#                 list_summaries = {}
                
#                 for i, ticker in enumerate(tickers_to_process, 1):
#                     # 중단 요청 확인
#                     if is_stop_requested():
#                         logging.info(f"Stop requested during multiple lists processing. Stopping at ticker {processed_count-1}/{total_tickers}")
#                         return jsonify({
#                             "message": f"여러 리스트 일괄 처리가 중단되었습니다. {processed_count-1}개 종목이 처리되었습니다.",
#                             "results": all_results,
#                             "summary": {
#                                 "total_lists": len(selected_lists),
#                                 "total_tickers": total_tickers,
#                                 "processed": processed_count-1,
#                                 "stopped": True
#                             }
#                         }), 200
                    
#                     ticker_start_time = datetime.now()
#                     logging.info(f"=== START Processing ticker {i}/{len(tickers_to_process)}: {ticker} from list: {list_name} ===")
                    
#                     # 진행상황 업데이트
#                     processed_count += 1
#                     update_progress(ticker=ticker, processed=processed_count-1, total=total_tickers, list_name=f"{list_name} ({processed_count}/{total_tickers})")
                    
#                     chart_generation_status = None
#                     analysis_status = None
                    
#                     # 타임아웃과 재시도 로직 추가
#                     max_retries = 3
#                     retry_count = 0
#                     success = False
                    
#                     while retry_count < max_retries and not success:
#                         try:
#                             logging.info(f"[{ticker}] Attempt {retry_count + 1}/{max_retries}")
                            
#                             # 1. 차트 생성 (타임아웃 적용)
#                             logging.info(f"[{ticker}] Starting chart generation...")
#                             chart_start_time = datetime.now()
                            
#                             try:
#                                 chart_result = safe_chart_generation(ticker, CHART_GENERATION_TIMEOUT)
#                                 if chart_result is None:
#                                     raise TimeoutError("Chart generation timed out")
                                
#                                 chart_generation_time = (datetime.now() - chart_start_time).total_seconds()
#                                 logging.info(f"[{ticker}] Chart generation completed successfully in {chart_generation_time:.2f} seconds")
#                                 chart_generation_status = "success"
#                             except Exception as e:
#                                 logging.error(f"[{ticker}] Chart generation failed: {str(e)}")
#                                 chart_generation_status = "failed"
#                                 raise e
                            
#                             # 2. AI 분석 (타임아웃 적용)
#                             logging.info(f"[{ticker}] Starting AI analysis...")
#                             analysis_start_time = datetime.now()
                            
#                             try:
#                                 # 기존 분석 파일 확인 및 유효성 검사
#                                 today_date_str = datetime.today().strftime("%Y%m%d")
#                                 html_file_name = f"{ticker}_{today_date_str}.html"
                                
#                                 # 날짜별 폴더 구조 사용
#                                 analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
#                                 analysis_html_path = os.path.join(analysis_date_folder, html_file_name)
                                
#                                 # 기존 파일이 있지만 유효하지 않으면 삭제
#                                 if os.path.exists(analysis_html_path):
#                                     if not is_valid_analysis_file(analysis_html_path):
#                                         logging.info(f"[{ticker}] Existing analysis file is invalid, will create new one")
#                                         try:
#                                             os.remove(analysis_html_path)
#                                             logging.info(f"[{ticker}] Removed invalid analysis file: {analysis_html_path}")
#                                         except Exception as e:
#                                             logging.warning(f"[{ticker}] Failed to remove invalid analysis file: {e}")
                                
#                                 # AI 분석에 타임아웃 적용
#                                 analysis_result = safe_ai_analysis(ticker, AI_ANALYSIS_TIMEOUT)
#                                 if analysis_result is None:
#                                     raise TimeoutError("AI analysis timed out")
                                
#                                 analysis_data, analysis_status_code = analysis_result
                                
#                                 analysis_time = (datetime.now() - analysis_start_time).total_seconds()
#                                 logging.info(f"[{ticker}] AI analysis completed with status code: {analysis_status_code} in {analysis_time:.2f} seconds")
#                                 analysis_status = "success"
                                
#                                 # 분석 결과 처리
#                                 if analysis_status_code == 200 and analysis_data.get("success"):
#                                     list_summaries[ticker] = {
#                                         "gemini_summary": analysis_data.get("summary_gemini", "요약 없음."),
#                                         "openai_summary": "OpenAI 분석 비활성화됨",
#                                         "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                                     }
#                                 else:
#                                     analysis_status = f"AI analysis failed: {analysis_data.get('analysis_gemini', 'Unknown error')}"
#                                     logging.error(f"[{ticker}] AI analysis failed for {ticker}: {analysis_status}")
#                                     list_summaries[ticker] = {
#                                         "gemini_summary": analysis_data.get("summary_gemini", "분석 실패."),
#                                         "openai_summary": "OpenAI 분석 비활성화됨",
#                                         "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                                     }
                                     
#                             except Exception as e:
#                                 logging.error(f"[{ticker}] AI analysis failed: {str(e)}")
#                                 analysis_status = "failed"
#                                 list_summaries[ticker] = {
#                                     "gemini_summary": "분석 실패.",
#                                     "openai_summary": "OpenAI 분석 비활성화됨",
#                                     "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                                 }
                            
#                             success = True
                            
#                         except Exception as e:
#                             retry_count += 1
#                             logging.error(f"[{ticker}] Attempt {retry_count} failed: {str(e)}")
                            
#                             if retry_count < max_retries:
#                                 logging.info(f"[{ticker}] Waiting 5 seconds before retry...")
#                                 time.sleep(5)
#                             else:
#                                 logging.error(f"[{ticker}] All {max_retries} attempts failed for {ticker}")
#                                 chart_generation_status = "failed"
#                                 analysis_status = "failed"
#                                 list_summaries[ticker] = {
#                                     "gemini_summary": "처리 실패.",
#                                     "openai_summary": "OpenAI 분석 비활성화됨",
#                                     "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                                 }
                        
#                         # 결과 기록
#                         list_results.append({
#                             "ticker": ticker,
#                             "chart_status": chart_generation_status,
#                             "analysis_status": analysis_status
#                         })
                        
#                         total_duration = (datetime.now() - ticker_start_time).total_seconds()
#                         logging.info(f"=== END Processing ticker {i}/{len(tickers_to_process)}: {ticker} from list: {list_name} (Total time: {total_duration:.2f}s) ===")
                        
#                         # 처리 시간이 너무 오래 걸리는 경우 경고
#                         if total_duration > 300:  # 5분 이상
#                             logging.warning(f"[{ticker}] WARNING: Processing took {total_duration:.2f} seconds (>5 minutes)")
                
#                 all_results[list_name] = list_results
#                 all_summaries[list_name] = list_summaries
                
#                 # 개별 리스트 요약 저장
#                 summary_file_path = get_analysis_summary_path(list_name)
#                 try:
#                     with open(summary_file_path, 'w', encoding='utf-8') as f:
#                         json.dump(list_summaries, f, ensure_ascii=False, indent=4)
#                     logging.info(f"Summaries for list '{list_name}' saved to {summary_file_path}")
#                 except Exception as e:
#                     logging.exception(f"Failed to save summaries for list '{list_name}'")
            
#             # 전체 요약을 세션에 저장
#             session['multiple_lists_summary'] = all_summaries
#             session['multiple_lists_results'] = all_results
            
#             # 성공/실패 통계 계산
#             total_success = 0
#             total_failed = 0
#             for list_name, results in all_results.items():
#                 if isinstance(results, list):
#                     success_count = sum(1 for r in results if r.get("chart_status") == "Chart generation succeeded." and r.get("analysis_status") == "AI analysis succeeded.")
#                     failed_count = len(results) - success_count
#                     total_success += success_count
#                     total_failed += failed_count
            
#             logging.info(f"Multiple lists batch processing completed: {total_success} successful, {total_failed} failed out of {total_tickers} total")
            
#             return jsonify({
#                 "message": f"Successfully processed {len(selected_lists)} lists.",
#                 "results": all_results,
#                 "summary": {
#                     "total_lists": len(selected_lists),
#                     "total_tickers": total_tickers,
#                     "successful": total_success,
#                     "failed": total_failed,
#                     "success_rate": f"{(total_success/total_tickers)*100:.1f}%" if total_tickers > 0 else "0%"
#                 }
#             }), 200
            
#         finally:
#             # 일괄 처리 종료 기록
#             end_batch_progress()
            
#     except Exception as e:
#         logging.exception("Error in generate_multiple_lists_analysis")
#         return jsonify({"error": f"Failed to process multiple lists: {str(e)}"}), 500
# ==============================================================================

