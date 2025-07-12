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

def perform_gemini_analysis_with_timeout(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64, timeout_seconds=90):
    """타임아웃이 적용된 Gemini API 분석"""
    
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
    
    # ThreadPoolExecutor를 사용한 타임아웃 처리
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_perform_analysis)
            
            try:
                # 타임아웃 적용
                analysis, succeeded = future.result(timeout=timeout_seconds)
                return analysis, succeeded
                
            except FutureTimeoutError:
                logging.error(f"[{ticker}] Gemini API 분석 타임아웃 ({timeout_seconds}초 초과)")
                return f"[Gemini 분석 타임아웃] 분석 시간이 {timeout_seconds}초를 초과했습니다.", False
                
    except Exception as e:
        logging.error(f"[{ticker}] Gemini 분석 실행 중 오류: {e}")
        return f"[Gemini 분석 실패] 실행 중 오류 발생: {e}", False

def perform_gemini_analysis(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64):
    """Gemini API를 사용한 분석을 수행합니다. (타임아웃 처리 포함)"""
    return perform_gemini_analysis_with_timeout(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64, timeout_seconds=90)

def perform_openai_analysis(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64):
    """OpenAI API를 사용한 분석을 수행합니다. (현재 비활성화)"""
    # OpenAI API 분석 비활성화
    analysis = "[OpenAI 분석 비활성화됨]"
    succeeded = False
    return analysis, succeeded

def _extract_summary_from_analysis(analysis_text):
    """분석 텍스트에서 핵심 요약을 추출합니다."""
    try:
        if "**핵심 요약**" in analysis_text:
            start_idx = analysis_text.find("**핵심 요약**")
            end_idx = analysis_text.find("\n\n", start_idx)
            if end_idx == -1:
                end_idx = len(analysis_text)
            summary = analysis_text[start_idx:end_idx].strip()
            return summary
        else:
            # 핵심 요약이 없으면 첫 번째 문단을 반환
            lines = analysis_text.split('\n')
            for line in lines:
                if line.strip() and not line.startswith('**'):
                    return line.strip()
            return "요약 없음."
    except Exception as e:
        logging.error(f"Error extracting summary: {e}")
        return "요약 추출 실패."

def check_ai_service_health():
    """AI 서비스 상태 확인"""
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