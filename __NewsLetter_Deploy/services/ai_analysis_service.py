import os
import logging
import google.generativeai as genai
from config import GOOGLE_API_KEY, GEMINI_MODEL_VERSION, GEMINI_TEXT_MODEL_VERSION

def perform_gemini_analysis(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64):
    """Gemini API를 사용한 분석을 수행합니다."""
    analysis = "[Gemini 분석 실패: 분석을 시작할 수 없습니다.]"
    succeeded = False
    
    try:
        if not GOOGLE_API_KEY:
            raise ValueError("Gemini API 키가 설정되지 않았습니다.")
        
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL_VERSION)
        
        # 이미지가 있는 경우에만 이미지 분석 수행
        if daily_b64 and weekly_b64 and monthly_b64:
            # 일봉 차트 이미지로 분석
            daily_image_data = {
                "mime_type": "image/png",
                "data": daily_b64
            }
            
            prompt_with_daily = f"{common_prompt}\n\n위의 지표 데이터와 함께 다음 일봉 차트 이미지를 분석해주세요."
            response_daily = model.generate_content([prompt_with_daily, daily_image_data])
            
            if response_daily.text:
                analysis = response_daily.text
                succeeded = True
                logging.info(f"Gemini analysis completed successfully for {ticker}")
            else:
                analysis = "[Gemini 분석 실패: 응답이 비어있습니다.]"
                
        else:
            # 이미지가 없는 경우 텍스트만으로 분석
            model_text = genai.GenerativeModel(GEMINI_TEXT_MODEL_VERSION)
            response = model_text.generate_content(common_prompt)
            
            if response.text:
                analysis = response.text
                succeeded = True
                logging.info(f"Gemini text analysis completed successfully for {ticker}")
            else:
                analysis = "[Gemini 분석 실패: 응답이 비어있습니다.]"
                
    except ValueError as val_e:
        logging.exception(f"Configuration or data error for Gemini API for {ticker}: {val_e}")
        analysis = f"[Gemini 분석 실패] 설정 또는 데이터 오류: {val_e}"
    except Exception as e:
        logging.exception(f"Gemini analysis failed for {ticker}")
        analysis = f"[Gemini 분석 실패] 분석 중 알 수 없는 오류 발생: {e}"
    
    return analysis, succeeded

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