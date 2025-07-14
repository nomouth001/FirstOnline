import os
import psutil
import subprocess
import logging
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class ProcessMonitor:
    def __init__(self, check_interval=60):
        """
        프로세스 모니터링 및 재시작 시스템
        
        Args:
            check_interval (int): 프로세스 체크 간격 (초)
        """
        self.check_interval = check_interval
        self.monitoring = False
        self.monitor_thread = None
        self.processes_to_monitor = {}
        self.restart_attempts = {}
        self.max_restart_attempts = 3
        self.restart_cooldown = 30  # 재시작 간격 (초)
        
    def add_process(self, name: str, command: str, working_dir: str = None, env: Dict = None):
        """모니터링할 프로세스 추가"""
        self.processes_to_monitor[name] = {
            'command': command,
            'working_dir': working_dir or os.getcwd(),
            'env': env or os.environ.copy(),
            'pid': None,
            'last_restart': 0,
            'restart_count': 0
        }
        self.restart_attempts[name] = 0
        logger.info(f"프로세스 모니터링 추가: {name} - {command}")
    
    def find_process_by_command(self, command_pattern: str) -> Optional[psutil.Process]:
        """명령어 패턴으로 프로세스 찾기"""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if command_pattern in cmdline:
                        return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def is_process_running(self, name: str) -> bool:
        """프로세스 실행 상태 확인"""
        process_info = self.processes_to_monitor.get(name)
        if not process_info:
            return False
        
        # PID로 확인
        if process_info['pid']:
            try:
                proc = psutil.Process(process_info['pid'])
                return proc.is_running()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                process_info['pid'] = None
        
        # 명령어로 확인
        command = process_info['command']
        proc = self.find_process_by_command(command)
        if proc:
            process_info['pid'] = proc.pid
            return True
        
        return False
    
    def start_process(self, name: str) -> bool:
        """프로세스 시작"""
        process_info = self.processes_to_monitor.get(name)
        if not process_info:
            logger.error(f"모니터링되지 않는 프로세스: {name}")
            return False
        
        try:
            logger.info(f"프로세스 시작: {name} - {process_info['command']}")
            
            # 작업 디렉토리 변경
            original_cwd = os.getcwd()
            os.chdir(process_info['working_dir'])
            
            # 프로세스 시작
            proc = subprocess.Popen(
                process_info['command'],
                shell=True,
                env=process_info['env'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # 새로운 세션 생성
            )
            
            # 원래 디렉토리로 복원
            os.chdir(original_cwd)
            
            process_info['pid'] = proc.pid
            process_info['last_restart'] = time.time()
            process_info['restart_count'] += 1
            
            logger.info(f"프로세스 시작 완료: {name} (PID: {proc.pid})")
            return True
            
        except Exception as e:
            logger.error(f"프로세스 시작 실패: {name} - {e}")
            return False
    
    def stop_process(self, name: str) -> bool:
        """프로세스 중지"""
        process_info = self.processes_to_monitor.get(name)
        if not process_info:
            return False
        
        try:
            if process_info['pid']:
                proc = psutil.Process(process_info['pid'])
                proc.terminate()
                proc.wait(timeout=10)
                logger.info(f"프로세스 중지 완료: {name}")
                process_info['pid'] = None
                return True
        except Exception as e:
            logger.error(f"프로세스 중지 실패: {name} - {e}")
        
        return False
    
    def restart_process(self, name: str) -> bool:
        """프로세스 재시작"""
        current_time = time.time()
        process_info = self.processes_to_monitor.get(name)
        
        if not process_info:
            return False
        
        # 재시작 쿨다운 체크
        if current_time - process_info['last_restart'] < self.restart_cooldown:
            logger.warning(f"프로세스 재시작 쿨다운 중: {name}")
            return False
        
        # 최대 재시작 횟수 체크
        if self.restart_attempts[name] >= self.max_restart_attempts:
            logger.error(f"프로세스 최대 재시작 횟수 초과: {name} ({self.max_restart_attempts}회)")
            return False
        
        logger.info(f"프로세스 재시작 시도: {name} (시도 {self.restart_attempts[name] + 1}/{self.max_restart_attempts})")
        
        # 기존 프로세스 중지
        self.stop_process(name)
        time.sleep(2)  # 잠시 대기
        
        # 새 프로세스 시작
        if self.start_process(name):
            self.restart_attempts[name] += 1
            logger.info(f"프로세스 재시작 성공: {name}")
            return True
        else:
            self.restart_attempts[name] += 1
            logger.error(f"프로세스 재시작 실패: {name}")
            return False
    
    def check_and_restart_processes(self):
        """모든 프로세스 상태 확인 및 재시작"""
        for name in self.processes_to_monitor:
            if not self.is_process_running(name):
                logger.warning(f"프로세스 중단 감지: {name}")
                self.restart_process(name)
            else:
                # 프로세스가 정상 실행 중이면 재시작 카운터 리셋
                if self.restart_attempts[name] > 0:
                    self.restart_attempts[name] = 0
                    logger.info(f"프로세스 안정화: {name} - 재시작 카운터 리셋")
    
    def monitor_loop(self):
        """모니터링 루프"""
        logger.info(f"프로세스 모니터링 시작 - 체크 간격: {self.check_interval}초")
        
        while self.monitoring:
            try:
                self.check_and_restart_processes()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"프로세스 모니터링 중 오류: {e}")
                time.sleep(self.check_interval)
    
    def start_monitoring(self):
        """모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("프로세스 모니터링 시작됨")
    
    def stop_monitoring(self):
        """모니터링 중지"""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)
            logger.info("프로세스 모니터링 중지됨")
    
    def get_process_status(self) -> Dict:
        """프로세스 상태 정보 반환"""
        status = {}
        for name, info in self.processes_to_monitor.items():
            status[name] = {
                'running': self.is_process_running(name),
                'pid': info['pid'],
                'restart_count': info['restart_count'],
                'restart_attempts': self.restart_attempts[name],
                'last_restart': datetime.fromtimestamp(info['last_restart']).isoformat() if info['last_restart'] else None
            }
        return status

# 전역 프로세스 모니터 인스턴스
process_monitor = ProcessMonitor()

def initialize_process_monitoring():
    """프로세스 모니터링 초기화"""
    try:
        # Celery 워커 모니터링 추가
        # venv 내의 celery 실행 파일 경로를 명시적으로 지정하여 경로 문제 해결
        project_root = os.getcwd()  # systemd의 WorkingDirectory 설정을 신뢰
        celery_executable = os.path.join(project_root, 'venv', 'bin', 'celery')

        process_monitor.add_process(
            name="celery_worker",
            command=f"{celery_executable} -A celery_app worker --loglevel=info",
            working_dir=project_root
        )
        
        # Gunicorn 모니터링 추가 (필요시) -> systemd가 관리하므로 제거
        # process_monitor.add_process(
        #     name="gunicorn",
        #     command="gunicorn -c gunicorn_config.py app:app",
        #     working_dir=os.getcwd()
        # )
        
        # 모니터링 시작
        process_monitor.start_monitoring()
        logger.info("프로세스 모니터링 초기화 완료")
        return True
        
    except Exception as e:
        logger.error(f"프로세스 모니터링 초기화 실패: {e}")
        return False

def get_process_status():
    """프로세스 상태 반환"""
    return process_monitor.get_process_status()

def restart_process(name: str):
    """특정 프로세스 재시작"""
    return process_monitor.restart_process(name)

def add_process_to_monitor(name: str, command: str, working_dir: str = None):
    """모니터링할 프로세스 추가"""
    process_monitor.add_process(name, command, working_dir)

def stop_process_monitoring():
    """프로세스 모니터링 중지"""
    process_monitor.stop_monitoring() 