import os
import shutil
from datetime import datetime, timedelta
import logging
import glob
import pytz
from config import USE_DATE_FOLDERS, DAYS_TO_KEEP, CHART_DIR, ANALYSIS_DIR, SUMMARY_DIR, DEBUG_DIR, MEMO_DIR, MULTI_SUMMARY_DIR

def get_date_folder_path(base_dir, date_str=None):
    """날짜별 폴더 경로를 생성합니다."""
    if not USE_DATE_FOLDERS:
        return base_dir
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    date_folder = os.path.join(base_dir, date_str)
    os.makedirs(date_folder, exist_ok=True)
    return date_folder

def cleanup_old_files():
    """오래된 파일들을 정리합니다."""
    if not USE_DATE_FOLDERS:
        return
    
    cutoff_date = datetime.now() - timedelta(days=DAYS_TO_KEEP)
    cutoff_str = cutoff_date.strftime("%Y%m%d")
    
    dirs_to_clean = [CHART_DIR, ANALYSIS_DIR, SUMMARY_DIR, DEBUG_DIR, MEMO_DIR, MULTI_SUMMARY_DIR]
    
    for base_dir in dirs_to_clean:
        if not os.path.exists(base_dir):
            continue
            
        for folder_name in os.listdir(base_dir):
            folder_path = os.path.join(base_dir, folder_name)
            
            # 폴더가 아니면 건너뛰기
            if not os.path.isdir(folder_path):
                continue
                
            # 날짜 형식이 아니면 건너뛰기
            if not folder_name.isdigit() or len(folder_name) != 8:
                continue
                
            # 오래된 폴더 삭제
            if folder_name < cutoff_str:
                try:
                    shutil.rmtree(folder_path)
                    logging.info(f"Deleted old folder: {folder_path}")
                except Exception as e:
                    logging.error(f"Failed to delete folder {folder_path}: {e}")

def get_file_count_by_date():
    """날짜별 파일 개수를 반환합니다."""
    stats = {}
    
    dirs_to_check = [CHART_DIR, ANALYSIS_DIR, SUMMARY_DIR, DEBUG_DIR, MEMO_DIR, MULTI_SUMMARY_DIR]
    
    for base_dir in dirs_to_check:
        if not os.path.exists(base_dir):
            continue
            
        for folder_name in os.listdir(base_dir):
            folder_path = os.path.join(base_dir, folder_name)
            
            if os.path.isdir(folder_path):
                file_count = len([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])
                if folder_name not in stats:
                    stats[folder_name] = {}
                stats[folder_name][base_dir.split('/')[-1]] = file_count
    
    return stats

def create_file_summary():
    """파일 현황 요약을 생성합니다."""
    stats = get_file_count_by_date()
    
    summary = "📁 파일 현황 요약\n"
    summary += "=" * 50 + "\n"
    
    total_files = 0
    for date, dirs in sorted(stats.items(), reverse=True):
        summary += f"\n📅 {date[:4]}-{date[4:6]}-{date[6:8]}\n"
        date_total = 0
        for dir_name, count in dirs.items():
            summary += f"  📂 {dir_name}: {count}개 파일\n"
            date_total += count
        summary += f"  📊 총 {date_total}개 파일\n"
        total_files += date_total
    
    summary += f"\n🎯 전체 총 {total_files}개 파일\n"
    
    return summary

def migrate_debug_files_to_date_folders():
    """기존 루트 폴더의 debug 파일들을 날짜별 폴더로 이동합니다."""
    if not os.path.exists(DEBUG_DIR):
        return
    
    moved_count = 0
    error_count = 0
    
    for filename in os.listdir(DEBUG_DIR):
        file_path = os.path.join(DEBUG_DIR, filename)
        
        # 파일이 아니면 건너뛰기
        if not os.path.isfile(file_path):
            continue
        
        # debug 파일 패턴 확인 (ticker_지표_debug_날짜.txt)
        if not filename.endswith('.txt') or '_debug_' not in filename:
            continue
        
        try:
            # 파일명에서 날짜 추출
            parts = filename.split('_debug_')
            if len(parts) != 2:
                continue
            
            date_part = parts[1].replace('.txt', '')
            if not date_part.isdigit() or len(date_part) != 8:
                continue
            
            # 날짜별 폴더 생성 및 파일 이동
            target_folder = get_date_folder_path(DEBUG_DIR, date_part)
            target_path = os.path.join(target_folder, filename)
            
            # 대상 파일이 이미 존재하면 건너뛰기
            if os.path.exists(target_path):
                logging.info(f"Debug file already exists in target folder, skipping: {filename}")
                continue
            
            # 파일 이동
            shutil.move(file_path, target_path)
            logging.info(f"Moved debug file: {filename} -> {target_folder}")
            moved_count += 1
            
        except Exception as e:
            logging.error(f"Failed to move debug file {filename}: {e}")
            error_count += 1
    
    if moved_count > 0:
        logging.info(f"Debug file migration completed: {moved_count} files moved, {error_count} errors")
    
    return moved_count, error_count 

def get_latest_file_info(ticker, file_type):
    """
    특정 종목의 최신 파일 정보를 반환합니다.
    
    :param ticker: 종목 코드
    :param file_type: 'chart' 또는 'analysis'
    :return: {'exists': bool, 'timestamp': datetime or None, 'file_path': str or None}
    """
    if file_type == 'chart':
        base_dir = CHART_DIR
        # 모든 차트 파일 패턴 검색 (daily, weekly, monthly)
        patterns = [f"{ticker}_daily_*.png", f"{ticker}_weekly_*.png", f"{ticker}_monthly_*.png"]
    elif file_type == 'analysis':
        base_dir = ANALYSIS_DIR
        patterns = [f"{ticker}_*.html"]
    else:
        return {'exists': False, 'timestamp': None, 'file_path': None}
    
    try:
        all_files = []
        
        if USE_DATE_FOLDERS:
            # 날짜별 폴더에서 검색
            if os.path.exists(base_dir):
                for folder_name in os.listdir(base_dir):
                    folder_path = os.path.join(base_dir, folder_name)
                    if os.path.isdir(folder_path):
                        for pattern in patterns:
                            folder_files = glob.glob(os.path.join(folder_path, pattern))
                            all_files.extend(folder_files)
        else:
            # 단일 폴더에서 검색
            for pattern in patterns:
                files = glob.glob(os.path.join(base_dir, pattern))
                all_files.extend(files)
        
        if not all_files:
            return {'exists': False, 'timestamp': None, 'file_path': None}
        
        # 가장 최근 파일 찾기
        latest_file = max(all_files, key=os.path.getmtime)
        timestamp = datetime.fromtimestamp(os.path.getmtime(latest_file))
        
        return {
            'exists': True,
            'timestamp': timestamp,
            'file_path': latest_file
        }
        
    except Exception as e:
        logging.error(f"Error getting latest file info for {ticker} ({file_type}): {e}")
        return {'exists': False, 'timestamp': None, 'file_path': None}

def is_us_stock(ticker):
    """
    미국 주식인지 판단합니다.
    한국 주식은 숫자로만 구성되어 있고, 미국 주식은 알파벳을 포함합니다.
    """
    return not ticker.isdigit()

def get_button_status(ticker, file_timestamp):
    """
    주식 시장 시간대에 따른 버튼 상태를 결정합니다.
    
    :param ticker: 종목 코드
    :param file_timestamp: 파일 생성 시간 (datetime)
    :return: 'green' 또는 'normal'
    """
    if not file_timestamp:
        return 'normal'
    
    try:
        # 현재 시간을 timezone-aware로 만들기 (서버는 EST)
        est = pytz.timezone('US/Eastern')
        now = est.localize(datetime.now())
        
        # file_timestamp가 timezone-naive인 경우 서버 시간대(EST)로 간주
        if file_timestamp.tzinfo is None:
            file_timestamp = est.localize(file_timestamp)
        
        if is_us_stock(ticker):
            # 미국 주식 - EST 시간대 기준
            est = pytz.timezone('US/Eastern')
            now_est = now.astimezone(est) if now.tzinfo else est.localize(now)
            file_time_est = file_timestamp.astimezone(est)
            
            current_hour = now_est.hour
            current_minute = now_est.minute
            
            # 시장 시간 체크: 오전 9:30 ~ 오후 4:00
            market_open = current_hour > 9 or (current_hour == 9 and current_minute >= 30)
            market_close = current_hour < 16
            is_market_hours = market_open and market_close
            
            # 절대 시간 차이 계산 (시간대 무관)
            now_utc = now.astimezone(pytz.UTC) if now.tzinfo else pytz.UTC.localize(now)
            file_utc = file_timestamp.astimezone(pytz.UTC)
            absolute_time_diff = abs((now_utc - file_utc).total_seconds() / 3600)
            
            if is_market_hours:
                # 시장 시간 중: 1시간 이내 생성된 파일이면 초록색
                return 'green' if absolute_time_diff <= 1 else 'normal'
            else:
                # 시장 시간 외: 파일이 시장 시간 외에 생성되었으면 초록색
                file_hour = file_time_est.hour
                file_minute = file_time_est.minute
                file_market_open = file_hour > 9 or (file_hour == 9 and file_minute >= 30)
                file_market_close = file_hour < 16
                file_is_market_hours = file_market_open and file_market_close
                
                return 'normal' if file_is_market_hours else 'green'
        
        else:
            # 한국 주식 - KST 시간대 기준
            kst = pytz.timezone('Asia/Seoul')
            now_kst = now.astimezone(kst) if now.tzinfo else kst.localize(now)
            file_time_kst = file_timestamp.astimezone(kst)
            
            current_hour = now_kst.hour
            
            # 시장 시간 체크: 오전 9:00 ~ 오후 3:30
            is_market_hours = 9 <= current_hour < 15 or (current_hour == 15 and now_kst.minute <= 30)
            
            if is_market_hours:
                # 시장 시간 중: 1시간 이내 생성된 파일이면 초록색
                time_diff = (now_kst - file_time_kst).total_seconds() / 3600  # 시간 단위
                return 'green' if time_diff <= 1 else 'normal'
            else:
                # 시장 시간 외: 파일이 시장 시간 외에 생성되었으면 초록색
                file_hour = file_time_kst.hour
                file_is_market_hours = 9 <= file_hour < 15 or (file_hour == 15 and file_time_kst.minute <= 30)
                
                return 'normal' if file_is_market_hours else 'green'
                
    except Exception as e:
        logging.error(f"Error determining button status for {ticker}: {e}")
        return 'normal'

def get_stock_file_status(ticker):
    """
    종목의 차트와 분석 파일 상태를 종합적으로 반환합니다.
    
    :param ticker: 종목 코드
    :return: dict with chart and analysis info
    """
    try:
        chart_info = get_latest_file_info(ticker, 'chart')
        analysis_info = get_latest_file_info(ticker, 'analysis')
        
        return {
            'chart': {
                'exists': chart_info['exists'],
                'timestamp': chart_info['timestamp'],
                'formatted_time': chart_info['timestamp'].strftime('%Y-%m-%d %H:%M') if chart_info['timestamp'] else 'N/A',
                'button_status': get_button_status(ticker, chart_info['timestamp'])
            },
            'analysis': {
                'exists': analysis_info['exists'],
                'timestamp': analysis_info['timestamp'],
                'formatted_time': analysis_info['timestamp'].strftime('%Y-%m-%d %H:%M') if analysis_info['timestamp'] else 'N/A',
                'button_status': get_button_status(ticker, analysis_info['timestamp'])
            },
            'is_us_stock': is_us_stock(ticker)
        }
    except Exception as e:
        logging.error(f"Error getting stock file status for {ticker}: {e}")
        # 오류 발생 시 기본값 반환
        return {
            'chart': {
                'exists': False,
                'timestamp': None,
                'formatted_time': 'N/A',
                'button_status': 'normal'
            },
            'analysis': {
                'exists': False,
                'timestamp': None,
                'formatted_time': 'N/A',
                'button_status': 'normal'
            },
            'is_us_stock': is_us_stock(ticker)
        } 

def find_latest_chart_files(ticker):
    """
    특정 종목의 최신 차트 파일들을 찾습니다.
    USE_DATE_FOLDERS 설정에 따라 자동으로 적절한 검색 방식을 선택합니다.
    
    :param ticker: 종목 코드
    :return: dict with Daily, Weekly, Monthly chart paths
    """
    charts = {"Daily": None, "Weekly": None, "Monthly": None}
    
    for label in ["Daily", "Weekly", "Monthly"]:
        chart_files = []
        
        if os.path.exists(CHART_DIR):
            if USE_DATE_FOLDERS:
                # 날짜별 폴더 구조에서 검색
                for date_folder in os.listdir(CHART_DIR):
                    date_folder_path = os.path.join(CHART_DIR, date_folder)
                    if os.path.isdir(date_folder_path) and date_folder.isdigit() and len(date_folder) == 8:
                        # 해당 날짜 폴더에서 차트 파일 검색
                        folder_chart_files = [f for f in os.listdir(date_folder_path) 
                                            if f.startswith(f"{ticker}_{label.lower()}_") and f.endswith(".png")]
                        for cf in folder_chart_files:
                            chart_files.append((date_folder, cf))
            else:
                # 단일 폴더 구조에서 검색
                all_files = [f for f in os.listdir(CHART_DIR) 
                           if f.startswith(f"{ticker}_{label.lower()}_") and f.endswith(".png")]
                for cf in all_files:
                    chart_files.append((None, cf))  # 폴더 없음을 나타내기 위해 None 사용
        
        # 가장 최신 파일 찾기
        latest_file = None
        latest_date_in_files = None

        for date_folder, cf in chart_files:
            try:
                parts = cf.split('_')
                if len(parts) >= 3:
                    file_date_str = parts[2].split('.')[0]
                    file_date = datetime.strptime(file_date_str, "%Y%m%d")
                    if latest_date_in_files is None or file_date > latest_date_in_files:
                        latest_date_in_files = file_date
                        latest_file = (date_folder, cf)
            except ValueError:
                continue

        if latest_file:
            date_folder, cf = latest_file
            if USE_DATE_FOLDERS and date_folder:
                charts[label] = os.path.join(CHART_DIR, date_folder, cf)
            else:
                charts[label] = os.path.join(CHART_DIR, cf)
    
    return charts 

def find_latest_analysis_file(ticker):
    """
    특정 종목의 최신 분석 파일을 찾습니다.
    USE_DATE_FOLDERS 설정에 따라 자동으로 적절한 검색 방식을 선택합니다.
    
    :param ticker: 종목 코드
    :return: 최신 분석 파일 경로 또는 None
    """
    analysis_files = []
    
    if os.path.exists(ANALYSIS_DIR):
        if USE_DATE_FOLDERS:
            # 날짜별 폴더 구조에서 검색
            for date_folder in os.listdir(ANALYSIS_DIR):
                date_folder_path = os.path.join(ANALYSIS_DIR, date_folder)
                if os.path.isdir(date_folder_path) and date_folder.isdigit() and len(date_folder) == 8:
                    folder_files = [f for f in os.listdir(date_folder_path) 
                                  if f.startswith(f"{ticker}_") and f.endswith(".html")]
                    for af in folder_files:
                        analysis_files.append((date_folder, af))
        else:
            # 단일 폴더 구조에서 검색
            all_files = [f for f in os.listdir(ANALYSIS_DIR) 
                       if f.startswith(f"{ticker}_") and f.endswith(".html")]
            for af in all_files:
                analysis_files.append((None, af))
    
    # 가장 최신 파일 찾기
    latest_file = None
    latest_date = None
    
    for date_folder, af in analysis_files:
        try:
            # 파일명에서 날짜 추출 (ticker_YYYYMMDD.html)
            parts = af.split('_')
            if len(parts) >= 2:
                file_date_str = parts[1].split('.')[0]
                file_date = datetime.strptime(file_date_str, "%Y%m%d")
                if latest_date is None or file_date > latest_date:
                    latest_date = file_date
                    latest_file = (date_folder, af)
        except ValueError:
            continue
    
    if latest_file:
        date_folder, af = latest_file
        if USE_DATE_FOLDERS and date_folder:
            return os.path.join(ANALYSIS_DIR, date_folder, af)
        else:
            return os.path.join(ANALYSIS_DIR, af)
    
    return None 

def get_all_analysis_dates(ticker):
    """
    특정 종목의 모든 분석 파일 날짜들을 반환합니다.
    USE_DATE_FOLDERS 설정에 따라 자동으로 적절한 검색 방식을 선택합니다.
    
    :param ticker: 종목 코드
    :return: 날짜 정보 리스트 (최신순)
    """
    dates = []
    
    if os.path.exists(ANALYSIS_DIR):
        if USE_DATE_FOLDERS:
            # 날짜별 폴더 구조에서 검색
            for date_folder in os.listdir(ANALYSIS_DIR):
                date_folder_path = os.path.join(ANALYSIS_DIR, date_folder)
                if os.path.isdir(date_folder_path) and date_folder.isdigit() and len(date_folder) == 8:
                    analysis_files = [f for f in os.listdir(date_folder_path) 
                                    if f.startswith(f"{ticker}_") and f.endswith(".html")]
                    
                    for file in analysis_files:
                        try:
                            # 파일명에서 날짜 추출 (예: AAPL_20241201.html -> 20241201)
                            date_str = file.replace(f"{ticker}_", "").replace(".html", "")
                            date_obj = datetime.strptime(date_str, "%Y%m%d")
                            dates.append({
                                "date_str": date_str,
                                "date_formatted": date_obj.strftime("%Y-%m-%d"),
                                "file_name": file,
                                "folder": date_folder
                            })
                        except ValueError:
                            continue
        else:
            # 단일 폴더 구조에서 검색
            analysis_files = [f for f in os.listdir(ANALYSIS_DIR) 
                            if f.startswith(f"{ticker}_") and f.endswith(".html")]
            
            for file in analysis_files:
                try:
                    # 파일명에서 날짜 추출 (예: AAPL_20241201.html -> 20241201)
                    date_str = file.replace(f"{ticker}_", "").replace(".html", "")
                    date_obj = datetime.strptime(date_str, "%Y%m%d")
                    dates.append({
                        "date_str": date_str,
                        "date_formatted": date_obj.strftime("%Y-%m-%d"),
                        "file_name": file,
                        "folder": None  # 단일 폴더이므로 None
                    })
                except ValueError:
                    continue
    
    # 날짜순으로 정렬 (최신순)
    dates.sort(key=lambda x: x["date_str"], reverse=True)
    
    return dates 

def find_analysis_file_by_date(ticker, date_str):
    """
    특정 날짜의 분석 파일을 찾습니다.
    USE_DATE_FOLDERS 설정에 따라 자동으로 적절한 검색 방식을 선택합니다.
    
    :param ticker: 종목 코드
    :param date_str: 날짜 문자열 (YYYYMMDD)
    :return: 분석 파일 경로 또는 None
    """
    html_file_name = f"{ticker}_{date_str}.html"
    
    if USE_DATE_FOLDERS:
        # 날짜별 폴더 구조에서 검색
        date_folder_path = os.path.join(ANALYSIS_DIR, date_str)
        analysis_html_path = os.path.join(date_folder_path, html_file_name)
    else:
        # 단일 폴더 구조에서 검색
        analysis_html_path = os.path.join(ANALYSIS_DIR, html_file_name)
    
    if os.path.exists(analysis_html_path):
        return analysis_html_path
    
    return None 