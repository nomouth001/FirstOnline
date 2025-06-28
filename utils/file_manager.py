import os
import shutil
from datetime import datetime, timedelta
import logging
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