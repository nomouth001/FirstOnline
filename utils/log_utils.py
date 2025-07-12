import os
import time
import logging
from typing import Generator
from pathlib import Path

logger = logging.getLogger(__name__)

class LogStreamer:
    """로그 파일을 실시간으로 스트리밍하는 클래스"""
    
    def __init__(self, log_file_path: str, max_lines: int = 1000):
        self.log_file_path = Path(log_file_path)
        self.max_lines = max_lines
        self.last_position = 0
        self.last_size = 0
        
    def get_recent_logs(self, lines: int = 50) -> list:
        """최근 로그 라인들을 반환"""
        try:
            if not self.log_file_path.exists():
                return []
                
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return [line.strip() for line in all_lines[-lines:]]
        except Exception as e:
            logger.error(f"로그 파일 읽기 오류: {e}")
            return []
    
    def tail_logs(self) -> Generator[str, None, None]:
        """로그 파일을 tail하여 새로운 라인들을 실시간으로 생성"""
        try:
            if not self.log_file_path.exists():
                # 파일이 없으면 생성될 때까지 대기
                while not self.log_file_path.exists():
                    time.sleep(1)
                    yield ""
                    
            # 파일 크기 확인
            current_size = self.log_file_path.stat().st_size
            
            # 파일이 회전되었거나 처음 시작인 경우 초기화
            if current_size < self.last_size:
                self.last_position = 0
                self.last_size = current_size
                
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                # 마지막 위치로 이동
                f.seek(self.last_position)
                
                # 새로운 라인들 읽기
                new_lines = f.readlines()
                
                for line in new_lines:
                    yield line.strip()
                    
                # 현재 위치 저장
                self.last_position = f.tell()
                self.last_size = current_size
                
        except Exception as e:
            logger.error(f"로그 tail 오류: {e}")
            yield f"오류: {e}"
    
    def follow_log_file(self) -> Generator[str, None, None]:
        """로그 파일을 계속 follow하면서 새로운 라인들을 실시간으로 생성"""
        while True:
            try:
                # 새로운 라인들 확인
                for line in self.tail_logs():
                    if line:  # 빈 라인이 아닌 경우에만 yield
                        yield line
                        
                # 잠시 대기
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"로그 follow 오류: {e}")
                yield f"오류: {e}"
                time.sleep(1)

def get_available_log_files() -> list:
    """사용 가능한 로그 파일들을 반환"""
    log_files = []
    
    # 현재 디렉토리의 로그 파일들
    current_dir = Path('.')
    for pattern in ['*.log', '*.txt']:
        for file_path in current_dir.glob(pattern):
            if file_path.is_file():
                stat = file_path.stat()
                log_files.append({
                    'name': file_path.name,
                    'path': str(file_path),
                    'size': stat.st_size,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'modified': stat.st_mtime,
                    'modified_str': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                })
    
    # logs 디렉토리가 있으면 추가
    logs_dir = Path('logs')
    if logs_dir.exists():
        for pattern in ['*.log', '*.txt']:
            for file_path in logs_dir.glob(pattern):
                if file_path.is_file():
                    stat = file_path.stat()
                    log_files.append({
                        'name': file_path.name,
                        'path': str(file_path),
                        'size': stat.st_size,
                        'size_mb': round(stat.st_size / (1024 * 1024), 2),
                        'modified': stat.st_mtime,
                        'modified_str': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                    })
    
    # 수정 시간 기준으로 정렬 (최신순)
    log_files.sort(key=lambda x: x['modified'], reverse=True)
    
    return log_files

def get_log_file_info(file_path: str) -> dict:
    """로그 파일 정보를 반환"""
    try:
        path = Path(file_path)
        if not path.exists():
            return None
            
        stat = path.stat()
        return {
            'name': path.name,
            'path': str(path),
            'size': stat.st_size,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'modified': stat.st_mtime,
            'modified_str': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
        }
    except Exception as e:
        logger.error(f"로그 파일 정보 가져오기 오류: {e}")
        return None 