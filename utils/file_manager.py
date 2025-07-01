import os
import shutil
from datetime import datetime, timedelta
import logging
from config import USE_DATE_FOLDERS, DAYS_TO_KEEP, CHART_DIR, ANALYSIS_DIR, SUMMARY_DIR, DEBUG_DIR, MEMO_DIR, MULTI_SUMMARY_DIR
import tempfile
import subprocess
from typing import Union

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

def get_file_path_with_timestamp(base_dir: str, ticker: str, suffix: str, extension: str = "html") -> str:
    """타임스탬프가 포함된 파일 경로를 생성합니다."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{ticker}_{timestamp}.{extension}"
    return os.path.join(base_dir, filename)

def safe_write_file(file_path: str, content: Union[str, bytes], mode: str = 'w', encoding: str = 'utf-8') -> bool:
    """
    권한 문제를 해결하면서 안전하게 파일을 쓰는 통합 함수
    
    Args:
        file_path: 저장할 파일 경로
        content: 파일 내용 (문자열 또는 바이트)
        mode: 파일 모드 ('w', 'wb' 등)
        encoding: 인코딩 (텍스트 모드에서만 사용)
    
    Returns:
        bool: 성공 여부
    """
    try:
        # 1. 디렉토리 경로 확보
        directory = os.path.dirname(file_path)
        if directory:
            ensure_directory_with_permissions(directory)
        
        # 2. 임시 파일에 내용 작성
        is_binary = 'b' in mode
        temp_mode = 'wb' if is_binary else 'w'
        temp_encoding = None if is_binary else encoding
        
        with tempfile.NamedTemporaryFile(mode=temp_mode, encoding=temp_encoding, delete=False) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        # 3. 임시 파일을 최종 경로로 이동
        try:
            shutil.move(temp_path, file_path)
            os.chmod(file_path, 0o644)
            logging.info(f"파일 저장 성공: {file_path}")
            return True
        except PermissionError:
            # sudo를 사용한 권한 처리
            try:
                subprocess.run(['/usr/bin/sudo', 'cp', temp_path, file_path], check=True, capture_output=True)
                subprocess.run(['/usr/bin/sudo', 'chown', 'ubuntu:ubuntu', file_path], check=True, capture_output=True)
                subprocess.run(['/usr/bin/sudo', 'chmod', '644', file_path], check=True, capture_output=True)
                os.unlink(temp_path)  # 임시 파일 삭제
                logging.info(f"sudo로 파일 저장 성공: {file_path}")
                return True
            except Exception as sudo_error:
                logging.error(f"sudo 파일 저장 실패: {sudo_error}")
                # 임시 파일 정리
                try:
                    os.unlink(temp_path)
                except:
                    pass
                return False
                
    except Exception as e:
        logging.error(f"파일 저장 실패 {file_path}: {e}")
        return False

def ensure_directory_with_permissions(directory: str) -> bool:
    """
    디렉토리 생성 및 권한 확보
    
    Args:
        directory: 생성할 디렉토리 경로
    
    Returns:
        bool: 성공 여부
    """
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except PermissionError:
        try:
            subprocess.run(['/usr/bin/sudo', 'mkdir', '-p', directory], check=True, capture_output=True)
            subprocess.run(['/usr/bin/sudo', 'chown', 'ubuntu:ubuntu', directory], check=True, capture_output=True)
            subprocess.run(['/usr/bin/sudo', 'chmod', '755', directory], check=True, capture_output=True)
            logging.info(f"sudo로 디렉토리 생성: {directory}")
            return True
        except Exception as sudo_error:
            logging.error(f"sudo 디렉토리 생성 실패: {sudo_error}")
            return False
    except Exception as e:
        logging.error(f"디렉토리 생성 실패 {directory}: {e}")
        return False

def save_image_with_permissions(fig, file_path: str, **kwargs) -> bool:
    """
    matplotlib figure를 권한 처리하면서 안전하게 저장
    
    Args:
        fig: matplotlib figure 객체
        file_path: 저장할 파일 경로
        **kwargs: savefig에 전달할 추가 인자
    
    Returns:
        bool: 성공 여부
    """
    try:
        import matplotlib.pyplot as plt
        
        # 1. 디렉토리 경로 확보
        directory = os.path.dirname(file_path)
        if directory:
            ensure_directory_with_permissions(directory)
        
        # 2. 임시 파일에 이미지 저장
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_path = temp_file.name
        
        fig.savefig(temp_path, **kwargs)
        plt.close('all')
        
        # 3. 임시 파일을 최종 경로로 이동
        try:
            shutil.move(temp_path, file_path)
            os.chmod(file_path, 0o644)
            logging.info(f"이미지 저장 성공: {file_path}")
            return True
        except PermissionError:
            try:
                subprocess.run(['/usr/bin/sudo', 'cp', temp_path, file_path], check=True, capture_output=True)
                subprocess.run(['/usr/bin/sudo', 'chown', 'ubuntu:ubuntu', file_path], check=True, capture_output=True)
                subprocess.run(['/usr/bin/sudo', 'chmod', '644', file_path], check=True, capture_output=True)
                os.unlink(temp_path)
                logging.info(f"sudo로 이미지 저장 성공: {file_path}")
                return True
            except Exception as sudo_error:
                logging.error(f"sudo 이미지 저장 실패: {sudo_error}")
                try:
                    os.unlink(temp_path)
                except:
                    pass
                return False
                
    except Exception as e:
        logging.error(f"이미지 저장 실패 {file_path}: {e}")
        plt.close('all')
        return False 