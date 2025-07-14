import os
import logging
import time
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import google.generativeai as genai
from config import GOOGLE_API_KEY, GEMINI_MODEL_VERSION, GEMINI_TEXT_MODEL_VERSION

class TimeoutError(Exception):
    """타임아웃 예외 클래스"""
    pass

def timeout_handler(signum, frame):
    """타임아웃 시그널 핸들러"""
    raise TimeoutError("AI 분석 타임아웃")

def perform_gemini_analysis_with_timeout(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64, timeout_seconds=120, max_retries=3):
    """타임아웃이 적용된 Gemini API 분석 (재시도 로직 포함)"""
    
    def _perform_analysis():
        """실제 분석 수행 함수"""
        try:
            if not GOOGLE_API_KEY:
                raise ValueError("Gemini API 키가 설정되지 않았습니다.")
            
            genai.configure(api_key=GOOGLE_API_KEY)
            model_text = genai.GenerativeModel(GEMINI_TEXT_MODEL_VERSION)
            
            logging.info(f"[{ticker}] Gemini API 분석 시작 - 타임아웃: {timeout_seconds}초")
            start_time = time.time()
            
            # Gemini API 호출
            response = model_text.generate_content(common_prompt)
            
            api_time = time.time() - start_time
            logging.info(f"[{ticker}] Gemini API 분석 완료 - 소요시간: {api_time:.2f}초")
            
            if response.text:
                return response.text, True
            else:
                return "[Gemini 분석 실패: 응답이 비어있습니다.]", False
                
        except Exception as e:
            logging.error(f"[{ticker}] Gemini 분석 중 오류: {e}")
            return f"[Gemini 분석 실패] 분석 중 오류 발생: {e}", False
    
    # 재시도 로직 적용
    for attempt in range(max_retries):
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_perform_analysis)
                
                try:
                    # 타임아웃 적용
                    analysis, succeeded = future.result(timeout=timeout_seconds)
                    
                    if succeeded:
                        if attempt > 0:
                            logging.info(f"[{ticker}] Gemini API 분석 성공 (재시도 {attempt + 1}회 후)")
                        return analysis, succeeded
                    else:
                        # 분석 실패 시 재시도
                        if attempt < max_retries - 1:
                            logging.warning(f"[{ticker}] Gemini API 분석 실패, 재시도 중... ({attempt + 1}/{max_retries})")
                            time.sleep(2 ** attempt)  # 지수 백오프
                            continue
                        else:
                            return analysis, succeeded
                            
                except FutureTimeoutError:
                    if attempt < max_retries - 1:
                        logging.warning(f"[{ticker}] Gemini API 분석 타임아웃, 재시도 중... ({attempt + 1}/{max_retries})")
                        time.sleep(2 ** attempt)  # 지수 백오프
                        continue
                    else:
                        logging.error(f"[{ticker}] Gemini API 분석 타임아웃 ({timeout_seconds}초 초과) - 최대 재시도 횟수 초과")
                        return f"[Gemini 분석 타임아웃] 분석 시간이 {timeout_seconds}초를 초과했습니다. (재시도 {max_retries}회 실패)", False
                        
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"[{ticker}] Gemini 분석 실행 중 오류, 재시도 중... ({attempt + 1}/{max_retries}): {e}")
                time.sleep(2 ** attempt)  # 지수 백오프
                continue
            else:
                logging.error(f"[{ticker}] Gemini 분석 실행 중 오류 - 최대 재시도 횟수 초과: {e}")
                return f"[Gemini 분석 실패] 실행 중 오류 발생: {e} (재시도 {max_retries}회 실패)", False
    
    # 이 부분에 도달하면 안 됨
    return f"[Gemini 분석 실패] 예상치 못한 오류 발생", False

def perform_openai_analysis(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64):
    """OpenAI API를 사용한 분석을 수행합니다. (현재 비활성화)"""
    # OpenAI API 분석 비활성화
    analysis = "[OpenAI 분석 비활성화됨]"
    succeeded = False
    return analysis, succeeded

def perform_analysis_with_memory_check(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64, timeout_seconds=120):
    """메모리 체크를 포함한 AI 분석"""
    from utils.memory_monitor import get_memory_status, cleanup_memory
    
    # 분석 전 메모리 상태 체크
    memory_info = get_memory_status()
    if memory_info['percent'] > 90:
        logging.warning(f"[{ticker}] 메모리 사용률이 높습니다 ({memory_info['percent']:.1f}%). 메모리 정리 후 진행합니다.")
        cleanup_memory()
        time.sleep(1)  # 메모리 정리 후 잠시 대기
    
    # AI 분석 수행
    analysis, succeeded = perform_gemini_analysis_with_timeout(
        ticker, common_prompt, daily_b64, weekly_b64, monthly_b64, timeout_seconds
    )
    
    # 분석 후 메모리 정리
    cleanup_memory()
    
    return analysis, succeeded

def check_ai_service_health():
    """AI 서비스 상태 확인 (개선된 버전)"""
    try:
        if not GOOGLE_API_KEY:
            return False, "Gemini API 키가 설정되지 않았습니다."
        
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(GEMINI_TEXT_MODEL_VERSION)
        
        # 간단한 테스트 요청
        test_prompt = "안녕하세요. 테스트 메시지입니다."
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(model.generate_content, test_prompt)
            
            try:
                response = future.result(timeout=30)  # 30초 타임아웃
                if response.text:
                    return True, "AI 서비스 정상"
                else:
                    return False, "AI 서비스 응답 없음"
                    
            except FutureTimeoutError:
                return False, "AI 서비스 타임아웃"
                
    except Exception as e:
        return False, f"AI 서비스 오류: {e}"

def get_ai_analysis_status():
    """AI 분석 서비스 상태 정보 반환"""
    health_status, health_message = check_ai_service_health()
    
    return {
        'service_healthy': health_status,
        'service_message': health_message,
        'gemini_api_configured': bool(GOOGLE_API_KEY),
        'model_version': GEMINI_TEXT_MODEL_VERSION,
        'default_timeout': 120,
        'max_retries': 3
    } 