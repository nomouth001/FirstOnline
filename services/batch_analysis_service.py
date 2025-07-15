import os
import csv
import json
import logging
from datetime import datetime, timedelta
import time
from flask_login import current_user
from flask import current_app
from models import StockList, Stock, get_stock_list_path, get_analysis_summary_path, _extract_summary_from_analysis
from services.chart_service import generate_chart
from services.progress_service import start_batch_progress, end_batch_progress, update_progress, is_stop_requested
from utils.file_manager import get_date_folder_path
from utils.timeout_utils import safe_ai_analysis
from utils.batch_recovery import start_batch_tracking, update_batch_progress, end_batch_tracking, check_and_recover_batches, get_batch_status
from utils.memory_monitor import get_memory_status, log_current_memory_status, cleanup_memory
from config import ANALYSIS_DIR, MULTI_SUMMARY_DIR, CHART_GENERATION_TIMEOUT, AI_ANALYSIS_TIMEOUT

# Constants
CHART_DIR = "static/charts"

def should_reuse_existing_files(ticker):
    """1시간 이내에 생성된 차트와 분석 파일이 모두 존재하는지 확인"""
    try:
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        today_date_str = now.strftime("%Y%m%d")
        
        # 차트 파일 확인
        chart_date_folder = get_date_folder_path(CHART_DIR, today_date_str)
        chart_files = [
            f"{ticker}_daily_{today_date_str}.png",
            f"{ticker}_weekly_{today_date_str}.png", 
            f"{ticker}_monthly_{today_date_str}.png"
        ]
        
        chart_exists = True
        for chart_file in chart_files:
            chart_path = os.path.join(chart_date_folder, chart_file)
            if not os.path.exists(chart_path):
                chart_exists = False
                break
            
            # 파일 생성 시간 확인
            file_mtime = datetime.fromtimestamp(os.path.getmtime(chart_path))
            if file_mtime < one_hour_ago:
                chart_exists = False
                break
        
        # 분석 파일 확인
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        analysis_file = f"{ticker}_{today_date_str}.html"
        analysis_path = os.path.join(analysis_date_folder, analysis_file)
        
        analysis_exists = False
        if os.path.exists(analysis_path):
            file_mtime = datetime.fromtimestamp(os.path.getmtime(analysis_path))
            if file_mtime >= one_hour_ago:
                analysis_exists = True
        
        return chart_exists and analysis_exists
        
    except Exception as e:
        logging.error(f"Error checking existing files for {ticker}: {e}")
        return False

def extract_existing_summary(ticker):
    """기존 분석 파일에서 요약 추출"""
    try:
        today_date_str = datetime.now().strftime("%Y%m%d")
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        analysis_file = f"{ticker}_{today_date_str}.html"
        analysis_path = os.path.join(analysis_date_folder, analysis_file)
        
        if not os.path.exists(analysis_path):
            return None
        
        with open(analysis_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # HTML에서 텍스트 추출
        import re
        text_content = re.sub(r'<[^>]+>', '', html_content)
        text_content = re.sub(r'\s+', ' ', text_content).strip()
        
        # 요약 추출
        summary = _extract_summary_from_analysis(text_content, 3)
        if summary and summary != "요약 없음.":
            return {
                "gemini_summary": summary,
                "openai_summary": "OpenAI 분석 비활성화됨",
                "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        return None
        
    except Exception as e:
        logging.error(f"Error extracting existing summary for {ticker}: {e}")
        return None

def extract_new_summary(ticker):
    """새로 생성된 분석 파일에서 요약 추출"""
    try:
        today_date_str = datetime.now().strftime("%Y%m%d")
        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
        analysis_file = f"{ticker}_{today_date_str}.html"
        analysis_path = os.path.join(analysis_date_folder, analysis_file)
        
        if not os.path.exists(analysis_path):
            return None
        
        with open(analysis_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # HTML에서 텍스트 추출
        import re
        text_content = re.sub(r'<[^>]+>', '', html_content)
        text_content = re.sub(r'\s+', ' ', text_content).strip()
        
        # 요약 추출
        summary = _extract_summary_from_analysis(text_content, 3)
        if summary and summary != "요약 없음.":
            return {
                "gemini_summary": summary,
                "openai_summary": "OpenAI 분석 비활성화됨",
                "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        return None
        
    except Exception as e:
        logging.error(f"Error extracting new summary for {ticker}: {e}")
        return None

def _process_tickers_batch(tickers_to_process, user, progress_id, summary_filename, progress_callback=None):
    """
    Processes a list of tickers for chart generation and AI analysis.
    Includes timeout, retries, and stop requests.
    
    Args:
        progress_callback: Optional callback function to update progress (current, total, message)
    """
    results = []
    all_summaries = {}
    total_tickers = len(tickers_to_process)
    
    # progress_id에 따라 타입 결정
    batch_type = "multiple" if progress_id.startswith("multi_") else "single"
    start_batch_progress(batch_type, total_tickers, progress_id)
    
    # 배치 복구 추적 시작
    list_names = [progress_id] if batch_type == "single" else progress_id.split("_")[-1].split(",")
    start_batch_tracking(progress_id, batch_type, user.id, list_names, total_tickers)
    
    logging.info(f"Starting batch processing ({batch_type}) for {total_tickers} tickers for '{progress_id}'")

    try:
        # 서버 부하 방지를 위한 처리 제한 (최대 30개 종목만 연속 처리 후 재시작)
        max_continuous_processing = 30
        processing_count = 0
        
        for i, ticker in enumerate(tickers_to_process, 1):
            if is_stop_requested():
                logging.info(f"Stop requested. Stopping at ticker {i-1}/{total_tickers}")
                return True, {
                    "message": f"Batch processing was stopped. {i-1} tickers were processed.",
                    "individual_results": results,
                    "summary": {"total_tickers": total_tickers, "processed": i-1, "stopped": True}
                }, 200, all_summaries

            logging.info(f"Processing ticker {i}/{total_tickers}: {ticker} from list(s): {progress_id}")
            update_progress(ticker=ticker, processed=i, total=total_tickers, list_name=progress_id)
            
            # Celery 작업 진행 상황 업데이트
            if progress_callback:
                progress_callback(i-1, total_tickers, f"처리 중: {ticker} ({i}/{total_tickers})")
            
            # 서버 부하 방지: 연속 처리 종목 수 제한
            processing_count += 1
            if processing_count >= max_continuous_processing:
                logging.info(f"서버 부하 방지를 위해 잠시 휴식 (처리 종목: {processing_count}개)")
                time.sleep(30)  # 30초 휴식
                processing_count = 0
                
                # 휴식 후 메모리 상태 로깅
                log_current_memory_status()
            
            # 메모리 체크 (더 엄격하게)
            memory_info = get_memory_status()
            if memory_info['percent'] > 90:
                logging.error(f"[{ticker}] 메모리 부족으로 배치 처리 중단 ({memory_info['percent']:.1f}%)")
                cleanup_memory()
                end_batch_tracking(progress_id, False, "메모리 부족")
                return False, {"error": "메모리 부족으로 배치 처리가 중단되었습니다."}, 500, {}
            
            # 메모리 사용량 로그
            log_current_memory_status()

            max_retries = 3
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                if is_stop_requested():
                    logging.info(f"[{ticker}] Stop requested during retry loop.")
                    break

                try:
                    # AI Analysis with timeout (차트 생성은 내부에서 처리)
                    from services.analysis_service import analyze_ticker_internal_logic
                    analysis_result = safe_ai_analysis(
                        analyze_ticker_internal_logic, 
                        AI_ANALYSIS_TIMEOUT, 
                        ticker=ticker
                    )
                    if analysis_result is None:
                        raise TimeoutError("AI analysis timed out")

                    # 분석 완료 후 짧은 휴식 (서버 부하 방지)
                    time.sleep(3)

                    analysis_data, analysis_status_code = analysis_result
                    
                    if analysis_status_code == 200 and analysis_data.get("success"):
                        analysis_status = "AI analysis succeeded."
                        # Summary extraction requires reading the analysis html file
                        today_date_str = datetime.today().strftime("%Y%m%d")
                        analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
                        html_file_name = f"{ticker}_{today_date_str}.html"
                        analysis_html_path = os.path.join(analysis_date_folder, html_file_name)
                        
                        # Read HTML file and extract text content
                        try:
                            if os.path.exists(analysis_html_path):
                                with open(analysis_html_path, 'r', encoding='utf-8') as f:
                                    html_content = f.read()
                                
                                # Extract text from HTML (simple approach - remove HTML tags)
                                import re
                                text_content = re.sub(r'<[^>]+>', '', html_content)
                                text_content = re.sub(r'\s+', ' ', text_content).strip()
                                
                                summary = _extract_summary_from_analysis(text_content, 3)
                                if summary and summary != "요약 없음.":
                                    all_summaries[ticker] = {
                                        "gemini_summary": summary,
                                        "openai_summary": "OpenAI 분석 비활성화됨",
                                        "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    }
                                    logging.info(f"[{ticker}] Summary extracted successfully")
                                else:
                                    logging.warning(f"[{ticker}] No summary extracted from analysis")
                            else:
                                logging.warning(f"[{ticker}] Analysis HTML file not found: {analysis_html_path}")
                        except Exception as e:
                            logging.error(f"[{ticker}] Failed to extract summary: {e}")
                            all_summaries[ticker] = {
                                "gemini_summary": "요약 추출 실패",
                                "openai_summary": "OpenAI 분석 비활성화됨",
                                "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                    else:
                        analysis_status = f"AI analysis failed: {analysis_data.get('analysis_gemini', 'Unknown error')}"
                        # 실패한 경우에도 요약 저장
                        all_summaries[ticker] = {
                            "gemini_summary": "분석 실패",
                            "openai_summary": "OpenAI 분석 비활성화됨",
                            "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                    
                    results.append({"ticker": ticker, "status": analysis_status})
                    success = True

                except Exception as e:
                    retry_count += 1
                    logging.error(f"[{ticker}] Attempt {retry_count}/{max_retries} failed: {e}")
                    if retry_count < max_retries:
                        time.sleep(5) # Wait 5 seconds before retrying
                    else:
                        logging.error(f"[{ticker}] All {max_retries} retries failed.")
                        results.append({"ticker": ticker, "status": "Failed after retries", "error": str(e)})
                        # 재시도 실패 시에도 요약 저장
                        all_summaries[ticker] = {
                            "gemini_summary": "처리 실패",
                            "openai_summary": "OpenAI 분석 비활성화됨",
                            "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }

            if is_stop_requested():
                break

        # Save the consolidated summary (even if empty or failed)
        if summary_filename:
            summary_dir = MULTI_SUMMARY_DIR if summary_filename.startswith("multi_") else os.path.dirname(get_analysis_summary_path("dummy"))
            if not os.path.exists(summary_dir):
                os.makedirs(summary_dir)
            
            # For single list analysis, use the same format as get_analysis_summary_path
            if summary_filename.startswith("multi_"):
                final_summary_name = summary_filename
            else:
                final_summary_name = f"{summary_filename}_analysis_results.json"
            
            summary_file_path = os.path.join(summary_dir, final_summary_name)

            try:
                with open(summary_file_path, 'w', encoding='utf-8') as f:
                    json.dump(all_summaries, f, ensure_ascii=False, indent=4)
                logging.info(f"Consolidated summary saved to {summary_file_path} with {len(all_summaries)} entries")
            except Exception as e:
                logging.exception(f"Failed to save consolidated summary for {summary_filename}")

        # 통계 계산
        total_successful = sum(1 for result in results if result.get("success"))
        total_failed = len(results) - total_successful
        success_rate = f"{(total_successful / len(results) * 100):.1f}%" if results else "0%"
        
        return True, {
            "individual_results": results,
            "summary": {
                "total_tickers": len(results),
                "processed": len(results),
                "successful": total_successful,
                "failed": total_failed,
                "success_rate": success_rate,
                "stopped": is_stop_requested()
            }
        }, 200, all_summaries

    finally:
        end_batch_progress()
        # 배치 복구 추적 종료
        try:
            end_batch_tracking(progress_id, True)
        except Exception as e:
            logging.error(f"배치 추적 종료 중 오류: {e}")
        logging.info(f"Batch processing finished for '{progress_id}'")

def run_single_list_analysis(list_name, user):
    if not user.is_authenticated:
        return False, "Authentication required", 401

    # 관리자는 모든 리스트에 접근 가능, 일반 사용자는 자신의 리스트와 공개 리스트만 접근 가능
    if user.is_admin:
        stock_list = StockList.query.filter(StockList.name == list_name).first()
    else:
        stock_list = StockList.query.filter(StockList.name == list_name, (StockList.user_id == user.id) | (StockList.is_public == True)).first()

    if not stock_list:
        return False, f"Stock list '{list_name}' not found or you don't have permission.", 404

    tickers_to_process = [stock.ticker for stock in stock_list.stocks]

    if not tickers_to_process:
        return False, f"No tickers found in list '{list_name}'.", 400

    success, data, status_code, _ = _process_tickers_batch(tickers_to_process, user, list_name, list_name)
    return success, data, status_code

def run_multiple_lists_analysis(list_names, user):
    if not user.is_authenticated:
        return False, "Authentication required", 401
    
    # 관리자는 모든 리스트에 접근 가능, 일반 사용자는 자신의 리스트와 공개 리스트만 접근 가능
    if user.is_admin:
        accessible_lists = StockList.query.filter(StockList.name.in_(list_names)).all()
    else:
        accessible_lists = StockList.query.filter(StockList.name.in_(list_names), (StockList.user_id == user.id) | (StockList.is_public == True)).all()

    if len(accessible_lists) != len(list_names):
        found_names = {l.name for l in accessible_lists}
        missing = set(list_names) - found_names
        logging.warning(f"User {user.id} tried to access non-existent or private lists: {missing}")

    if not accessible_lists:
        return False, "No accessible lists found.", 404

def run_multiple_lists_analysis_with_user_id(list_names, user_id, user_is_admin):
    """Flask 컨텍스트 없이 사용할 수 있는 다중 리스트 분석 함수"""
    from models import User
    
    # 사용자 정보 확인
    user = User.query.get(user_id)
    if not user:
        return False, "User not found", 404
    
    # 관리자는 모든 리스트에 접근 가능, 일반 사용자는 자신의 리스트와 공개 리스트만 접근 가능
    if user_is_admin:
        accessible_lists = StockList.query.filter(StockList.name.in_(list_names)).all()
    else:
        accessible_lists = StockList.query.filter(StockList.name.in_(list_names), (StockList.user_id == user_id) | (StockList.is_public == True)).all()

    if len(accessible_lists) != len(list_names):
        found_names = {l.name for l in accessible_lists}
        missing = set(list_names) - found_names
        logging.warning(f"User {user_id} tried to access non-existent or private lists: {missing}")

    if not accessible_lists:
        return False, "No accessible lists found.", 404

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    progress_id = f"multi_{timestamp}"
    summary_filename = f"multi_summary_{timestamp}.json"
    
    # 전체 처리할 종목 수 계산 (중복 포함)
    total_tickers_count = sum(len(stock_list.stocks) for stock_list in accessible_lists)
    
    logging.info(f"Starting multiple lists analysis for {len(accessible_lists)} lists with {total_tickers_count} total tickers")
    
    # 진행률 초기화
    start_batch_progress(progress_id, total_tickers_count, "multiple")
    
    try:
        all_summaries = {}
        list_results = {}
        processed_count = 0
        
        # 각 리스트별로 순차 처리
        for list_idx, stock_list in enumerate(accessible_lists):
            list_name = stock_list.name
            list_tickers = [stock.ticker for stock in stock_list.stocks]
            
            if not list_tickers:
                logging.warning(f"List '{list_name}' has no tickers, skipping")
                list_results[list_name] = {"tickers": [], "status": "empty"}
                continue
            
            logging.info(f"Processing list {list_idx + 1}/{len(accessible_lists)}: '{list_name}' with {len(list_tickers)} tickers")
            list_results[list_name] = {"tickers": [], "status": "processing"}
            
            # 각 리스트의 종목별 처리
            for ticker_idx, ticker in enumerate(list_tickers):
                if is_stop_requested():
                    logging.info(f"Stop requested while processing {ticker} in list {list_name}")
                    break
                
                processed_count += 1
                current_list_info = f"{list_name} ({ticker_idx + 1}/{len(list_tickers)})"
                
                # 진행률 업데이트
                update_progress(ticker, processed_count, total_tickers_count, current_list_info)
                
                try:
                    # 1시간 이내 기존 파일 확인
                    should_reuse = should_reuse_existing_files(ticker)
                    
                    if should_reuse:
                        logging.info(f"[{ticker}] Reusing existing files (within 1 hour)")
                        # 기존 파일에서 요약 추출
                        summary = extract_existing_summary(ticker)
                        if summary:
                            all_summaries[ticker] = summary
                            list_results[list_name]["tickers"].append({
                                "ticker": ticker, 
                                "status": "reused_existing", 
                                "summary": summary
                            })
                        else:
                            # 기존 파일이 있지만 요약 추출 실패
                            all_summaries[ticker] = {
                                "gemini_summary": "기존 파일 존재하나 요약 추출 실패",
                                "openai_summary": "OpenAI 분석 비활성화됨",
                                "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            list_results[list_name]["tickers"].append({
                                "ticker": ticker, 
                                "status": "reused_but_summary_failed", 
                                "summary": all_summaries[ticker]
                            })
                        continue
                    
                    # 새로운 분석 수행
                    max_retries = 3
                    retry_count = 0
                    success = False
                    
                    while retry_count < max_retries and not success:
                        if is_stop_requested():
                            logging.info(f"[{ticker}] Stop requested during retry loop.")
                            break

                        try:
                            # AI Analysis with timeout (차트 생성은 내부에서 처리)
                            from services.analysis_service import analyze_ticker_internal_logic
                            analysis_result = safe_ai_analysis(
                                analyze_ticker_internal_logic, 
                                AI_ANALYSIS_TIMEOUT, 
                                ticker=ticker
                            )
                            if analysis_result is None:
                                raise TimeoutError("AI analysis timed out")

                            analysis_data, analysis_status_code = analysis_result
                            
                            if analysis_status_code == 200 and analysis_data.get("success"):
                                # 요약 추출
                                summary = extract_new_summary(ticker)
                                if summary:
                                    all_summaries[ticker] = summary
                                    list_results[list_name]["tickers"].append({
                                        "ticker": ticker, 
                                        "status": "newly_analyzed", 
                                        "summary": summary
                                    })
                                    logging.info(f"[{ticker}] New analysis completed successfully")
                                else:
                                    # 분석은 성공했지만 요약 추출 실패
                                    all_summaries[ticker] = {
                                        "gemini_summary": "분석 완료하나 요약 추출 실패",
                                        "openai_summary": "OpenAI 분석 비활성화됨",
                                        "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    }
                                    list_results[list_name]["tickers"].append({
                                        "ticker": ticker, 
                                        "status": "analyzed_but_summary_failed", 
                                        "summary": all_summaries[ticker]
                                    })
                            else:
                                # 분석 실패
                                all_summaries[ticker] = {
                                    "gemini_summary": "분석 실패",
                                    "openai_summary": "OpenAI 분석 비활성화됨",
                                    "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                list_results[list_name]["tickers"].append({
                                    "ticker": ticker, 
                                    "status": "analysis_failed", 
                                    "summary": all_summaries[ticker]
                                })
                            
                            success = True

                        except Exception as e:
                            retry_count += 1
                            logging.error(f"[{ticker}] Attempt {retry_count}/{max_retries} failed: {e}")
                            if retry_count < max_retries:
                                time.sleep(5)  # Wait 5 seconds before retrying
                            else:
                                logging.error(f"[{ticker}] All {max_retries} retries failed.")
                                # 재시도 실패
                                all_summaries[ticker] = {
                                    "gemini_summary": "처리 실패 (재시도 한계 초과)",
                                    "openai_summary": "OpenAI 분석 비활성화됨",
                                    "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                list_results[list_name]["tickers"].append({
                                    "ticker": ticker, 
                                    "status": "failed_after_retries", 
                                    "error": str(e),
                                    "summary": all_summaries[ticker]
                                })

                except Exception as e:
                    logging.error(f"[{ticker}] Unexpected error: {e}")
                    all_summaries[ticker] = {
                        "gemini_summary": "예상치 못한 오류 발생",
                        "openai_summary": "OpenAI 분석 비활성화됨",
                        "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    list_results[list_name]["tickers"].append({
                        "ticker": ticker, 
                        "status": "unexpected_error", 
                        "error": str(e),
                        "summary": all_summaries[ticker]
                    })

                if is_stop_requested():
                    break
            
            # 리스트 처리 완료
            list_results[list_name]["status"] = "completed"
            logging.info(f"Completed processing list '{list_name}' with {len(list_results[list_name]['tickers'])} tickers")
            
            if is_stop_requested():
                break

        # 통합 요약 파일 저장
        summary_dir = MULTI_SUMMARY_DIR
        if not os.path.exists(summary_dir):
            os.makedirs(summary_dir)
        
        summary_file_path = os.path.join(summary_dir, summary_filename)
        
        # 리스트별로 정리된 최종 결과 구조
        final_data = {
            "timestamp": timestamp,
            "total_lists": len(accessible_lists),
            "total_tickers": total_tickers_count,
            "processed_tickers": processed_count,
            "all_summaries": all_summaries,
            "list_results": list_results
        }
        
        try:
            with open(summary_file_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=4)
            logging.info(f"Consolidated summary saved to {summary_file_path} with {len(all_summaries)} entries")
        except Exception as e:
            logging.exception(f"Failed to save consolidated summary for {summary_filename}")

        # 개별 리스트별 요약 파일도 생성
        for list_name, result in list_results.items():
            individual_summaries = {}
            for ticker_info in result["tickers"]:
                ticker = ticker_info["ticker"]
                if ticker in all_summaries:
                    individual_summaries[ticker] = all_summaries[ticker]
            
            if individual_summaries:
                individual_summary_path = get_analysis_summary_path(list_name)
                summary_dir = os.path.dirname(individual_summary_path)
                if not os.path.exists(summary_dir):
                    os.makedirs(summary_dir)
                
                try:
                    with open(individual_summary_path, 'w', encoding='utf-8') as f:
                        json.dump(individual_summaries, f, ensure_ascii=False, indent=4)
                    logging.info(f"Individual list summary saved for '{list_name}' to {individual_summary_path} with {len(individual_summaries)} entries")
                except Exception as e:
                    logging.error(f"Failed to save individual summary for list '{list_name}': {e}")

        # 통계 계산
        total_successful = sum(1 for ticker_info in 
                              [ticker for result in list_results.values() 
                               for ticker in result["tickers"]] 
                              if ticker_info["status"] in ["reused_existing", "newly_analyzed"])
        total_failed = processed_count - total_successful
        success_rate = f"{(total_successful / processed_count * 100):.1f}%" if processed_count > 0 else "0%"
        
        return True, {
            "message": f"Multiple lists analysis completed for {len(accessible_lists)} lists",
            "summary_file": summary_file_path,
            "list_results": list_results,
            "all_summaries": all_summaries,
            "summary": {
                "total_lists": len(accessible_lists),
                "total_tickers": total_tickers_count,
                "processed": processed_count,
                "successful": total_successful,
                "failed": total_failed,
                "success_rate": success_rate,
                "stopped": is_stop_requested()
            }
        }, 200

    finally:
        end_batch_progress()
        logging.info(f"Multiple lists batch processing finished for '{progress_id}'")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    progress_id = f"multi_{timestamp}"
    summary_filename = f"multi_summary_{timestamp}.json"
    
    # 전체 처리할 종목 수 계산 (중복 포함)
    total_tickers_count = sum(len(stock_list.stocks) for stock_list in accessible_lists)
    
    logging.info(f"Starting multiple lists analysis for {len(accessible_lists)} lists with {total_tickers_count} total tickers")
    
    # 진행률 초기화
    start_batch_progress(progress_id, total_tickers_count, "multiple")
    
    try:
        all_summaries = {}
        list_results = {}
        processed_count = 0
        
        # 각 리스트별로 순차 처리
        for list_idx, stock_list in enumerate(accessible_lists):
            list_name = stock_list.name
            list_tickers = [stock.ticker for stock in stock_list.stocks]
            
            if not list_tickers:
                logging.warning(f"List '{list_name}' has no tickers, skipping")
                list_results[list_name] = {"tickers": [], "status": "empty"}
                continue
            
            logging.info(f"Processing list {list_idx + 1}/{len(accessible_lists)}: '{list_name}' with {len(list_tickers)} tickers")
            list_results[list_name] = {"tickers": [], "status": "processing"}
            
            # 각 리스트의 종목별 처리
            for ticker_idx, ticker in enumerate(list_tickers):
                if is_stop_requested():
                    logging.info(f"Stop requested while processing {ticker} in list {list_name}")
                    break
                
                processed_count += 1
                current_list_info = f"{list_name} ({ticker_idx + 1}/{len(list_tickers)})"
                
                # 진행률 업데이트
                update_progress(ticker, processed_count, total_tickers_count, current_list_info)
                
                try:
                    # 1시간 이내 기존 파일 확인
                    should_reuse = should_reuse_existing_files(ticker)
                    
                    if should_reuse:
                        logging.info(f"[{ticker}] Reusing existing files (within 1 hour)")
                        # 기존 파일에서 요약 추출
                        summary = extract_existing_summary(ticker)
                        if summary:
                            all_summaries[ticker] = summary
                            list_results[list_name]["tickers"].append({
                                "ticker": ticker, 
                                "status": "reused_existing", 
                                "summary": summary
                            })
                        else:
                            # 기존 파일이 있지만 요약 추출 실패
                            all_summaries[ticker] = {
                                "gemini_summary": "기존 파일 존재하나 요약 추출 실패",
                                "openai_summary": "OpenAI 분석 비활성화됨",
                                "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            list_results[list_name]["tickers"].append({
                                "ticker": ticker, 
                                "status": "reused_but_summary_failed", 
                                "summary": all_summaries[ticker]
                            })
                        continue
                    
                    # 새로운 분석 수행
                    max_retries = 3
                    retry_count = 0
                    success = False
                    
                    while retry_count < max_retries and not success:
                        if is_stop_requested():
                            logging.info(f"[{ticker}] Stop requested during retry loop.")
                            break

                        try:
                            # AI Analysis with timeout (차트 생성은 내부에서 처리)
                            from services.analysis_service import analyze_ticker_internal_logic
                            analysis_result = safe_ai_analysis(
                                analyze_ticker_internal_logic, 
                                AI_ANALYSIS_TIMEOUT, 
                                ticker=ticker
                            )
                            if analysis_result is None:
                                raise TimeoutError("AI analysis timed out")

                            analysis_data, analysis_status_code = analysis_result
                            
                            if analysis_status_code == 200 and analysis_data.get("success"):
                                # 요약 추출
                                summary = extract_new_summary(ticker)
                                if summary:
                                    all_summaries[ticker] = summary
                                    list_results[list_name]["tickers"].append({
                                        "ticker": ticker, 
                                        "status": "newly_analyzed", 
                                        "summary": summary
                                    })
                                    logging.info(f"[{ticker}] New analysis completed successfully")
                                else:
                                    # 분석은 성공했지만 요약 추출 실패
                                    all_summaries[ticker] = {
                                        "gemini_summary": "분석 완료하나 요약 추출 실패",
                                        "openai_summary": "OpenAI 분석 비활성화됨",
                                        "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    }
                                    list_results[list_name]["tickers"].append({
                                        "ticker": ticker, 
                                        "status": "analyzed_but_summary_failed", 
                                        "summary": all_summaries[ticker]
                                    })
                            else:
                                # 분석 실패
                                all_summaries[ticker] = {
                                    "gemini_summary": "분석 실패",
                                    "openai_summary": "OpenAI 분석 비활성화됨",
                                    "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                list_results[list_name]["tickers"].append({
                                    "ticker": ticker, 
                                    "status": "analysis_failed", 
                                    "summary": all_summaries[ticker]
                                })
                            
                            success = True

                        except Exception as e:
                            retry_count += 1
                            logging.error(f"[{ticker}] Attempt {retry_count}/{max_retries} failed: {e}")
                            if retry_count < max_retries:
                                time.sleep(5)  # Wait 5 seconds before retrying
                            else:
                                logging.error(f"[{ticker}] All {max_retries} retries failed.")
                                # 재시도 실패
                                all_summaries[ticker] = {
                                    "gemini_summary": "처리 실패 (재시도 한계 초과)",
                                    "openai_summary": "OpenAI 분석 비활성화됨",
                                    "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                list_results[list_name]["tickers"].append({
                                    "ticker": ticker, 
                                    "status": "failed_after_retries", 
                                    "error": str(e),
                                    "summary": all_summaries[ticker]
                                })

                except Exception as e:
                    logging.error(f"[{ticker}] Unexpected error: {e}")
                    all_summaries[ticker] = {
                        "gemini_summary": "예상치 못한 오류 발생",
                        "openai_summary": "OpenAI 분석 비활성화됨",
                        "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    list_results[list_name]["tickers"].append({
                        "ticker": ticker, 
                        "status": "unexpected_error", 
                        "error": str(e),
                        "summary": all_summaries[ticker]
                    })

                if is_stop_requested():
                    break
            
            # 리스트 처리 완료
            list_results[list_name]["status"] = "completed"
            logging.info(f"Completed processing list '{list_name}' with {len(list_results[list_name]['tickers'])} tickers")
            
            if is_stop_requested():
                break

        # 통합 요약 파일 저장
        summary_dir = MULTI_SUMMARY_DIR
        if not os.path.exists(summary_dir):
            os.makedirs(summary_dir)
        
        summary_file_path = os.path.join(summary_dir, summary_filename)
        
        # 리스트별로 정리된 최종 결과 구조
        final_data = {
            "timestamp": timestamp,
            "total_lists": len(accessible_lists),
            "total_tickers": total_tickers_count,
            "processed_tickers": processed_count,
            "all_summaries": all_summaries,
            "list_results": list_results
        }
        
        try:
            with open(summary_file_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=4)
            logging.info(f"Consolidated summary saved to {summary_file_path} with {len(all_summaries)} entries")
        except Exception as e:
            logging.exception(f"Failed to save consolidated summary for {summary_filename}")

        # 개별 리스트별 요약 파일도 생성
        for list_name, result in list_results.items():
            individual_summaries = {}
            for ticker_info in result["tickers"]:
                ticker = ticker_info["ticker"]
                if ticker in all_summaries:
                    individual_summaries[ticker] = all_summaries[ticker]
            
            if individual_summaries:
                individual_summary_path = get_analysis_summary_path(list_name)
                summary_dir = os.path.dirname(individual_summary_path)
                if not os.path.exists(summary_dir):
                    os.makedirs(summary_dir)
                
                try:
                    with open(individual_summary_path, 'w', encoding='utf-8') as f:
                        json.dump(individual_summaries, f, ensure_ascii=False, indent=4)
                    logging.info(f"Individual list summary saved for '{list_name}' to {individual_summary_path} with {len(individual_summaries)} entries")
                except Exception as e:
                    logging.error(f"Failed to save individual summary for list '{list_name}': {e}")

        # 통계 계산
        total_successful = sum(1 for ticker_info in 
                              [ticker for result in list_results.values() 
                               for ticker in result["tickers"]] 
                              if ticker_info["status"] in ["reused_existing", "newly_analyzed"])
        total_failed = processed_count - total_successful
        success_rate = f"{(total_successful / processed_count * 100):.1f}%" if processed_count > 0 else "0%"
        
        return True, {
            "message": f"Multiple lists analysis completed for {len(accessible_lists)} lists",
            "summary_file": summary_file_path,
            "list_results": list_results,
            "all_summaries": all_summaries,
            "summary": {
                "total_lists": len(accessible_lists),
                "total_tickers": total_tickers_count,
                "processed": processed_count,
                "successful": total_successful,
                "failed": total_failed,
                "success_rate": success_rate,
                "stopped": is_stop_requested()
            }
        }, 200

    finally:
        end_batch_progress()
        logging.info(f"Multiple lists batch processing finished for '{progress_id}'") 