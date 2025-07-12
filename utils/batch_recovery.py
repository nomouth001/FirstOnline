import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class BatchState:
    """배치 작업 상태 정보"""
    batch_id: str
    batch_type: str  # 'single' or 'multiple'
    user_id: int
    list_names: List[str]
    total_tickers: int
    processed_tickers: int
    current_ticker: Optional[str]
    failed_tickers: List[str]
    start_time: str
    last_update_time: str
    status: str  # 'running', 'completed', 'failed', 'stopped'
    error_message: Optional[str] = None
    recovery_count: int = 0
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'BatchState':
        return cls(**data)

class BatchRecoveryManager:
    """배치 프로세스 복구 관리자"""
    
    def __init__(self, state_dir: str = "batch_states"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        self.max_recovery_attempts = 3
        self.recovery_timeout_hours = 2
        
    def save_batch_state(self, batch_state: BatchState):
        """배치 상태 저장"""
        try:
            state_file = self.state_dir / f"{batch_state.batch_id}.json"
            batch_state.last_update_time = datetime.now().isoformat()
            
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(batch_state.to_dict(), f, indent=2, ensure_ascii=False)
                
            logger.debug(f"배치 상태 저장 완료: {batch_state.batch_id}")
            
        except Exception as e:
            logger.error(f"배치 상태 저장 실패: {e}")
    
    def load_batch_state(self, batch_id: str) -> Optional[BatchState]:
        """배치 상태 로드"""
        try:
            state_file = self.state_dir / f"{batch_id}.json"
            
            if not state_file.exists():
                return None
                
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            return BatchState.from_dict(data)
            
        except Exception as e:
            logger.error(f"배치 상태 로드 실패: {e}")
            return None
    
    def get_running_batches(self) -> List[BatchState]:
        """실행 중인 배치 목록 반환"""
        running_batches = []
        
        try:
            for state_file in self.state_dir.glob("*.json"):
                try:
                    batch_state = self.load_batch_state(state_file.stem)
                    if batch_state and batch_state.status == 'running':
                        running_batches.append(batch_state)
                except Exception as e:
                    logger.warning(f"배치 상태 파일 처리 실패: {state_file} - {e}")
                    
        except Exception as e:
            logger.error(f"실행 중인 배치 조회 실패: {e}")
            
        return running_batches
    
    def get_recoverable_batches(self) -> List[BatchState]:
        """복구 가능한 배치 목록 반환"""
        recoverable_batches = []
        cutoff_time = datetime.now() - timedelta(hours=self.recovery_timeout_hours)
        
        for batch_state in self.get_running_batches():
            try:
                last_update = datetime.fromisoformat(batch_state.last_update_time)
                
                # 마지막 업데이트가 오래된 경우 복구 대상
                if (last_update < cutoff_time and 
                    batch_state.recovery_count < self.max_recovery_attempts):
                    recoverable_batches.append(batch_state)
                    
            except Exception as e:
                logger.warning(f"배치 복구 가능성 체크 실패: {batch_state.batch_id} - {e}")
                
        return recoverable_batches
    
    def mark_batch_completed(self, batch_id: str, success: bool = True, error_message: str = None):
        """배치 완료 표시"""
        try:
            batch_state = self.load_batch_state(batch_id)
            if batch_state:
                batch_state.status = 'completed' if success else 'failed'
                batch_state.error_message = error_message
                batch_state.last_update_time = datetime.now().isoformat()
                self.save_batch_state(batch_state)
                
                # 완료된 배치 상태 파일 정리 (선택적)
                if success:
                    self.cleanup_old_states(days=7)
                    
        except Exception as e:
            logger.error(f"배치 완료 표시 실패: {e}")
    
    def cleanup_old_states(self, days: int = 7):
        """오래된 배치 상태 파일 정리"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            for state_file in self.state_dir.glob("*.json"):
                try:
                    batch_state = self.load_batch_state(state_file.stem)
                    if batch_state and batch_state.status in ['completed', 'failed']:
                        last_update = datetime.fromisoformat(batch_state.last_update_time)
                        
                        if last_update < cutoff_time:
                            state_file.unlink()
                            logger.info(f"오래된 배치 상태 파일 삭제: {state_file.name}")
                            
                except Exception as e:
                    logger.warning(f"배치 상태 파일 정리 실패: {state_file} - {e}")
                    
        except Exception as e:
            logger.error(f"배치 상태 파일 정리 실패: {e}")
    
    def create_recovery_task(self, batch_state: BatchState) -> Dict:
        """복구 작업 생성"""
        try:
            # 복구 횟수 증가
            batch_state.recovery_count += 1
            batch_state.status = 'running'
            batch_state.last_update_time = datetime.now().isoformat()
            
            # 실패한 티커들을 제외하고 남은 티커들 계산
            remaining_tickers = batch_state.total_tickers - batch_state.processed_tickers
            
            recovery_task = {
                'batch_id': batch_state.batch_id,
                'batch_type': batch_state.batch_type,
                'user_id': batch_state.user_id,
                'list_names': batch_state.list_names,
                'processed_tickers': batch_state.processed_tickers,
                'remaining_tickers': remaining_tickers,
                'failed_tickers': batch_state.failed_tickers,
                'recovery_count': batch_state.recovery_count,
                'original_start_time': batch_state.start_time
            }
            
            # 업데이트된 상태 저장
            self.save_batch_state(batch_state)
            
            logger.info(f"복구 작업 생성: {batch_state.batch_id} (시도 {batch_state.recovery_count}/{self.max_recovery_attempts})")
            
            return recovery_task
            
        except Exception as e:
            logger.error(f"복구 작업 생성 실패: {e}")
            return None
    
    def get_batch_summary(self, batch_id: str) -> Dict:
        """배치 요약 정보 반환"""
        try:
            batch_state = self.load_batch_state(batch_id)
            if not batch_state:
                return {'error': '배치 상태를 찾을 수 없습니다.'}
            
            start_time = datetime.fromisoformat(batch_state.start_time)
            last_update = datetime.fromisoformat(batch_state.last_update_time)
            
            return {
                'batch_id': batch_state.batch_id,
                'batch_type': batch_state.batch_type,
                'status': batch_state.status,
                'total_tickers': batch_state.total_tickers,
                'processed_tickers': batch_state.processed_tickers,
                'failed_tickers': len(batch_state.failed_tickers),
                'progress_percent': round((batch_state.processed_tickers / batch_state.total_tickers) * 100, 1),
                'start_time': batch_state.start_time,
                'last_update_time': batch_state.last_update_time,
                'duration_minutes': round((last_update - start_time).total_seconds() / 60, 1),
                'recovery_count': batch_state.recovery_count,
                'error_message': batch_state.error_message
            }
            
        except Exception as e:
            logger.error(f"배치 요약 생성 실패: {e}")
            return {'error': f'배치 요약 생성 실패: {e}'}

# 전역 복구 관리자 인스턴스
_recovery_manager = None

def get_recovery_manager() -> BatchRecoveryManager:
    """전역 복구 관리자 인스턴스 반환"""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = BatchRecoveryManager()
    return _recovery_manager

def start_batch_tracking(batch_id: str, batch_type: str, user_id: int, list_names: List[str], total_tickers: int):
    """배치 추적 시작"""
    try:
        recovery_manager = get_recovery_manager()
        
        batch_state = BatchState(
            batch_id=batch_id,
            batch_type=batch_type,
            user_id=user_id,
            list_names=list_names,
            total_tickers=total_tickers,
            processed_tickers=0,
            current_ticker=None,
            failed_tickers=[],
            start_time=datetime.now().isoformat(),
            last_update_time=datetime.now().isoformat(),
            status='running'
        )
        
        recovery_manager.save_batch_state(batch_state)
        logger.info(f"배치 추적 시작: {batch_id}")
        
    except Exception as e:
        logger.error(f"배치 추적 시작 실패: {e}")

def update_batch_progress(batch_id: str, current_ticker: str, processed_count: int, failed_tickers: List[str] = None):
    """배치 진행상황 업데이트"""
    try:
        recovery_manager = get_recovery_manager()
        batch_state = recovery_manager.load_batch_state(batch_id)
        
        if batch_state:
            batch_state.current_ticker = current_ticker
            batch_state.processed_tickers = processed_count
            if failed_tickers:
                batch_state.failed_tickers = failed_tickers
            batch_state.last_update_time = datetime.now().isoformat()
            
            recovery_manager.save_batch_state(batch_state)
            
    except Exception as e:
        logger.error(f"배치 진행상황 업데이트 실패: {e}")

def end_batch_tracking(batch_id: str, success: bool = True, error_message: str = None):
    """배치 추적 종료"""
    try:
        recovery_manager = get_recovery_manager()
        recovery_manager.mark_batch_completed(batch_id, success, error_message)
        logger.info(f"배치 추적 종료: {batch_id} (성공: {success})")
        
    except Exception as e:
        logger.error(f"배치 추적 종료 실패: {e}")

def check_and_recover_batches():
    """중단된 배치 검사 및 복구"""
    try:
        recovery_manager = get_recovery_manager()
        recoverable_batches = recovery_manager.get_recoverable_batches()
        
        recovery_tasks = []
        for batch_state in recoverable_batches:
            recovery_task = recovery_manager.create_recovery_task(batch_state)
            if recovery_task:
                recovery_tasks.append(recovery_task)
                
        if recovery_tasks:
            logger.info(f"복구 가능한 배치 {len(recovery_tasks)}개 발견")
            
        return recovery_tasks
        
    except Exception as e:
        logger.error(f"배치 복구 검사 실패: {e}")
        return []

def get_batch_status(batch_id: str) -> Dict:
    """배치 상태 조회"""
    try:
        recovery_manager = get_recovery_manager()
        return recovery_manager.get_batch_summary(batch_id)
        
    except Exception as e:
        logger.error(f"배치 상태 조회 실패: {e}")
        return {'error': f'배치 상태 조회 실패: {e}'}

def get_all_batch_status() -> List[Dict]:
    """모든 배치 상태 조회"""
    try:
        recovery_manager = get_recovery_manager()
        running_batches = recovery_manager.get_running_batches()
        
        all_status = []
        for batch_state in running_batches:
            status = recovery_manager.get_batch_summary(batch_state.batch_id)
            all_status.append(status)
            
        return all_status
        
    except Exception as e:
        logger.error(f"모든 배치 상태 조회 실패: {e}")
        return [] 