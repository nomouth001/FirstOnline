import os
import logging

def load_ai_prompt_template():
    """AI 분석용 프롬프트 템플릿을 파일에서 로드합니다."""
    try:
        prompt_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ai_analysis_prompt.txt')
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logging.error("AI 프롬프트 파일을 찾을 수 없습니다: ai_analysis_prompt.txt")
        return None
    except Exception as e:
        logging.error(f"AI 프롬프트 파일 로드 중 오류 발생: {e}")
        return None 