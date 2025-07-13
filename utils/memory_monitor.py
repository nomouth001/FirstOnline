import psutil
import logging
import os
import time
import threading
from datetime import datetime
from typing import Dict, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MemoryStats:
    """메모리 통계 정보"""
    timestamp: datetime
    total_memory: float  # MB
    used_memory: float   # MB
    available_memory: float  # MB
    memory_percent: float  # %
    process_memory: float  # MB
    process_percent: float  # %
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_memory_mb': round(self.total_memory, 2),
            'used_memory_mb': round(self.used_memory, 2),
            'available_memory_mb': round(self.available_memory, 2),
            'memory_percent': round(self.memory_percent, 2),
            'process_memory_mb': round(self.process_memory, 2),
            'process_percent': round(self.process_percent, 2)
        }

class MemoryMonitor:
    """메모리 사용량 모니터링 클래스"""
    
    def __init__(self, 
                 warning_threshold: float = 70.0,  # 경고 임계치 (%) - 80%에서 70%로 낮춤
                 critical_threshold: float = 85.0,  # 위험 임계치 (%) - 90%에서 85%로 낮춤
                 check_interval: int = 30):  # 체크 간격 (초) - 60초에서 30초로 단축
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.check_interval = check_interval
        self.process = psutil.Process()
        self._monitoring = False
        self._monitor_thread = None
        self.last_stats = None
        self.alert_callbacks = []
        
    def get_memory_stats(self) -> MemoryStats:
        """현재 메모리 통계 반환"""
        try:
            # 시스템 메모리 정보
            memory = psutil.virtual_memory()
            
            # 프로세스 메모리 정보
            process_memory = self.process.memory_info()
            
            stats = MemoryStats(
                timestamp=datetime.now(),
                total_memory=memory.total / (1024 * 1024),  # MB
                used_memory=memory.used / (1024 * 1024),    # MB
                available_memory=memory.available / (1024 * 1024),  # MB
                memory_percent=memory.percent,
                process_memory=process_memory.rss / (1024 * 1024),  # MB
                process_percent=self.process.memory_percent()
            )
            
            self.last_stats = stats
            return stats
            
        except Exception as e:
            logger.error(f"메모리 통계 수집 실패: {e}")
            return None
    
    def check_memory_usage(self) -> Dict:
        """메모리 사용량 체크 및 알림"""
        stats = self.get_memory_stats()
        if not stats:
            return {'status': 'error', 'message': '메모리 통계 수집 실패'}
        
        result = {
            'status': 'ok',
            'stats': stats.to_dict(),
            'alerts': []
        }
        
        # 시스템 메모리 체크
        if stats.memory_percent >= self.critical_threshold:
            alert = {
                'level': 'critical',
                'type': 'system_memory',
                'message': f'시스템 메모리 사용량이 위험 수준입니다: {stats.memory_percent:.1f}%',
                'value': stats.memory_percent
            }
            result['alerts'].append(alert)
            result['status'] = 'critical'
            self._trigger_alert(alert)
            
        elif stats.memory_percent >= self.warning_threshold:
            alert = {
                'level': 'warning',
                'type': 'system_memory',
                'message': f'시스템 메모리 사용량이 높습니다: {stats.memory_percent:.1f}%',
                'value': stats.memory_percent
            }
            result['alerts'].append(alert)
            if result['status'] == 'ok':
                result['status'] = 'warning'
            self._trigger_alert(alert)
        
        # 프로세스 메모리 체크 (500MB 이상 시 경고)
        if stats.process_memory > 500:
            alert = {
                'level': 'warning',
                'type': 'process_memory',
                'message': f'프로세스 메모리 사용량이 높습니다: {stats.process_memory:.1f}MB',
                'value': stats.process_memory
            }
            result['alerts'].append(alert)
            if result['status'] == 'ok':
                result['status'] = 'warning'
            self._trigger_alert(alert)
        
        return result
    
    def _trigger_alert(self, alert: Dict):
        """알림 트리거"""
        logger.warning(f"메모리 알림: {alert['message']}")
        
        # 등록된 콜백 실행
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"알림 콜백 실행 실패: {e}")
    
    def add_alert_callback(self, callback: Callable):
        """알림 콜백 추가"""
        self.alert_callbacks.append(callback)
    
    def start_monitoring(self):
        """백그라운드 모니터링 시작"""
        if self._monitoring:
            logger.warning("메모리 모니터링이 이미 실행 중입니다.")
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"메모리 모니터링 시작 - 체크 간격: {self.check_interval}초")
    
    def stop_monitoring(self):
        """백그라운드 모니터링 중지"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("메모리 모니터링 중지")
    
    def _monitor_loop(self):
        """모니터링 루프"""
        while self._monitoring:
            try:
                self.check_memory_usage()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"메모리 모니터링 루프 오류: {e}")
                time.sleep(self.check_interval)
    
    def get_memory_info_for_logging(self) -> str:
        """로깅용 메모리 정보 문자열"""
        stats = self.get_memory_stats()
        if not stats:
            return "메모리 정보 수집 실패"
        
        return (f"시스템 메모리: {stats.memory_percent:.1f}% "
                f"({stats.used_memory:.1f}/{stats.total_memory:.1f}MB), "
                f"프로세스 메모리: {stats.process_memory:.1f}MB")

# 전역 메모리 모니터 인스턴스
_memory_monitor = None

def get_memory_monitor() -> MemoryMonitor:
    """전역 메모리 모니터 인스턴스 반환"""
    global _memory_monitor
    if _memory_monitor is None:
        _memory_monitor = MemoryMonitor()
    return _memory_monitor

def init_memory_monitoring():
    """메모리 모니터링 초기화"""
    monitor = get_memory_monitor()
    
    # 로그 알림 콜백 추가
    def log_alert(alert):
        level = alert['level']
        message = alert['message']
        if level == 'critical':
            logger.critical(f"🔴 메모리 위험: {message}")
        elif level == 'warning':
            logger.warning(f"🟡 메모리 경고: {message}")
    
    monitor.add_alert_callback(log_alert)
    monitor.start_monitoring()
    
    logger.info("메모리 모니터링 초기화 완료")

def log_memory_usage(context: str = ""):
    """현재 메모리 사용량 로그"""
    monitor = get_memory_monitor()
    memory_info = monitor.get_memory_info_for_logging()
    
    if context:
        logger.info(f"[{context}] {memory_info}")
    else:
        logger.info(f"메모리 사용량: {memory_info}")

def check_memory_before_analysis(ticker: str) -> bool:
    """분석 전 메모리 체크 (더 엄격한 기준 적용)"""
    monitor = get_memory_monitor()
    result = monitor.check_memory_usage()
    
    # 메모리 사용량 통계
    stats = result.get('stats', {})
    memory_percent = stats.get('memory_percent', 100)  # 기본값을 100%로 설정하여 오류 시 안전하게 중단
    process_memory = stats.get('process_memory_mb', 0)
    
    # 더 엄격한 기준으로 체크
    if result['status'] == 'critical' or memory_percent > 85:
        logger.error(f"[{ticker}] 메모리 부족으로 분석 중단: {memory_percent:.1f}%")
        return False
    elif result['status'] == 'warning' or memory_percent > 70:
        # 경고 상태에서도 프로세스 메모리가 높으면 중단
        if process_memory > 400:  # 400MB 이상이면 중단 (기존 500MB)
            logger.error(f"[{ticker}] 프로세스 메모리 과다로 분석 중단: {process_memory:.1f}MB")
            return False
        logger.warning(f"[{ticker}] 메모리 사용량 경고: {memory_percent:.1f}%, 프로세스: {process_memory:.1f}MB")
    
    # 시스템 상태 확인 (CPU 부하 체크)
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        if cpu_percent > 90:  # CPU 사용률이 90% 이상이면 중단
            logger.error(f"[{ticker}] CPU 과부하로 분석 중단: {cpu_percent:.1f}%")
            return False
        elif cpu_percent > 75:  # CPU 사용률이 75% 이상이면 경고
            logger.warning(f"[{ticker}] CPU 사용률 높음: {cpu_percent:.1f}%")
    except Exception as e:
        logger.error(f"CPU 상태 확인 중 오류: {e}")
    
    return True

def get_memory_status_for_admin() -> Dict:
    """관리자 페이지용 메모리 상태"""
    monitor = get_memory_monitor()
    result = monitor.check_memory_usage()
    
    if result['status'] == 'error':
        return result
    
    stats = result['stats']
    return {
        'status': result['status'],
        'system_memory_percent': stats['memory_percent'],
        'system_memory_used': stats['used_memory_mb'],
        'system_memory_total': stats['total_memory_mb'],
        'process_memory': stats['process_memory_mb'],
        'process_memory_percent': stats['process_percent'],
        'alerts': result['alerts'],
        'timestamp': stats['timestamp']
    } 