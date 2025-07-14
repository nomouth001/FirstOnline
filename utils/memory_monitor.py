import psutil
import logging
import threading
import time
from datetime import datetime
import os

logger = logging.getLogger(__name__)

class MemoryMonitor:
    def __init__(self, check_interval=30, warning_threshold=80, critical_threshold=90):
        """
        메모리 모니터링 시스템 초기화
        
        Args:
            check_interval (int): 메모리 체크 간격 (초)
            warning_threshold (int): 경고 임계값 (%)
            critical_threshold (int): 위험 임계값 (%)
        """
        self.check_interval = check_interval
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.monitoring = False
        self.monitor_thread = None
        self.last_warning_time = 0
        self.last_critical_time = 0
        self.warning_cooldown = 300  # 5분 쿨다운
        self.critical_cooldown = 60   # 1분 쿨다운
        
    def get_memory_info(self):
        """현재 메모리 사용량 정보 반환"""
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent,
            'swap_total': swap.total,
            'swap_used': swap.used,
            'swap_percent': swap.percent
        }
    
    def get_process_memory_info(self):
        """현재 프로세스들의 메모리 사용량 정보 반환"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'memory_info']):
            try:
                pinfo = proc.info
                if pinfo['memory_percent'] > 1.0:  # 1% 이상 메모리 사용 프로세스만
                    processes.append({
                        'pid': pinfo['pid'],
                        'name': pinfo['name'],
                        'memory_percent': pinfo['memory_percent'],
                        'memory_mb': pinfo['memory_info'].rss / 1024 / 1024
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # 메모리 사용량 순으로 정렬
        processes.sort(key=lambda x: x['memory_percent'], reverse=True)
        return processes[:10]  # 상위 10개만 반환
    
    def log_memory_status(self, level='info'):
        """메모리 상태를 로그에 기록"""
        memory_info = self.get_memory_info()
        process_info = self.get_process_memory_info()
        
        memory_gb = memory_info['total'] / (1024**3)
        used_gb = memory_info['used'] / (1024**3)
        available_gb = memory_info['available'] / (1024**3)
        
        log_message = f"""
메모리 상태 리포트 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):
- 총 메모리: {memory_gb:.2f} GB
- 사용 중: {used_gb:.2f} GB ({memory_info['percent']:.1f}%)
- 사용 가능: {available_gb:.2f} GB
- 스왑 사용: {memory_info['swap_percent']:.1f}%

메모리 사용량 상위 프로세스:"""
        
        for proc in process_info:
            log_message += f"\n- {proc['name']} (PID: {proc['pid']}): {proc['memory_mb']:.1f} MB ({proc['memory_percent']:.1f}%)"
        
        if level == 'warning':
            logger.warning(log_message)
        elif level == 'critical':
            logger.critical(log_message)
        else:
            logger.info(log_message)
    
    def check_memory_status(self):
        """메모리 상태 체크 및 필요시 알림"""
        memory_info = self.get_memory_info()
        current_time = time.time()
        
        memory_percent = memory_info['percent']
        
        if memory_percent >= self.critical_threshold:
            if current_time - self.last_critical_time > self.critical_cooldown:
                logger.critical(f"🔴 메모리 위험: 시스템 메모리 사용량이 위험 수준입니다: {memory_percent:.1f}%")
                self.log_memory_status('critical')
                self.last_critical_time = current_time
                
                # 메모리 부족 시 가비지 컬렉션 강제 실행
                import gc
                gc.collect()
                
        elif memory_percent >= self.warning_threshold:
            if current_time - self.last_warning_time > self.warning_cooldown:
                logger.warning(f"메모리 알림: 시스템 메모리 사용량이 위험 수준입니다: {memory_percent:.1f}%")
                self.log_memory_status('warning')
                self.last_warning_time = current_time
    
    def monitor_loop(self):
        """메모리 모니터링 루프"""
        logger.info(f"메모리 모니터링 시작 - 체크 간격: {self.check_interval}초")
        
        while self.monitoring:
            try:
                self.check_memory_status()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"메모리 모니터링 중 오류 발생: {e}")
                time.sleep(self.check_interval)
    
    def start_monitoring(self):
        """메모리 모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("메모리 모니터링 시작됨")
    
    def stop_monitoring(self):
        """메모리 모니터링 중지"""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)
            logger.info("메모리 모니터링 중지됨")
    
    def get_status(self):
        """현재 모니터링 상태 반환"""
        return {
            'monitoring': self.monitoring,
            'check_interval': self.check_interval,
            'warning_threshold': self.warning_threshold,
            'critical_threshold': self.critical_threshold
        }

# 전역 메모리 모니터 인스턴스
memory_monitor = MemoryMonitor()

def initialize_memory_monitoring():
    """메모리 모니터링 초기화"""
    try:
        memory_monitor.start_monitoring()
        logger.info("메모리 모니터링 초기화 완료")
        return True
    except Exception as e:
        logger.error(f"메모리 모니터링 초기화 실패: {e}")
        return False

def get_memory_status():
    """현재 메모리 상태 반환"""
    return memory_monitor.get_memory_info()

def get_process_memory_status():
    """프로세스별 메모리 상태 반환"""
    return memory_monitor.get_process_memory_info()

def log_current_memory_status():
    """현재 메모리 상태 로그 기록"""
    memory_monitor.log_memory_status()

def cleanup_memory():
    """메모리 정리 작업"""
    import gc
    gc.collect()
    logger.info("메모리 정리 작업 완료") 