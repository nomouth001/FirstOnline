import os
import json
import logging
from datetime import datetime, timedelta
import yfinance as yf

class DataCacheService:
    """Yahoo Finance 데이터 캐싱 서비스"""
    
    def __init__(self, cache_dir='cache'):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
    def _get_cache_filename(self, ticker, data_type='daily'):
        """캐시 파일명 생성"""
        return os.path.join(self.cache_dir, f"{ticker}_{data_type}_cache.json")
    
    def _is_cache_valid(self, cache_file, hours=6):
        """캐시가 유효한지 확인 (6시간 기본)"""
        if not os.path.exists(cache_file):
            return False
            
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            cache_time = datetime.fromisoformat(cache_data['cached_at'])
            expiry_time = cache_time + timedelta(hours=hours)
            
            return datetime.now() < expiry_time
        except Exception as e:
            logging.error(f"캐시 유효성 검사 실패: {e}")
            return False
    
    def get_cached_data(self, ticker, start_date=None):
        """캐시된 데이터 반환"""
        cache_file = self._get_cache_filename(ticker)
        
        # 캐시가 유효하면 캐시 데이터 반환
        if self._is_cache_valid(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                logging.info(f"[{ticker}] 캐시된 데이터 사용 (캐시 시간: {cache_data['cached_at']})")
                
                # JSON을 DataFrame으로 변환
                import pandas as pd
                df = pd.DataFrame(cache_data['data'])
                if not df.empty:
                    df.index = pd.to_datetime(df.index)
                    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                
                return df, True  # 캐시 데이터, 캐시 사용됨
                
            except Exception as e:
                logging.error(f"캐시 데이터 로드 실패: {e}")
        
        # 캐시가 없거나 만료된 경우 새로 다운로드
        return self._download_and_cache(ticker, start_date)
    
    def _download_and_cache(self, ticker, start_date=None):
        """데이터 다운로드 및 캐싱"""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=5 * 365 + 30)
        
        try:
            logging.info(f"[{ticker}] Yahoo Finance에서 새 데이터 다운로드 중...")
            
            # 재시도 로직
            import time
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    df = yf.download(
                        ticker,
                        start=start_date,
                        end=datetime.now() + timedelta(days=1),
                        auto_adjust=False,
                        progress=False,
                        keepna=True
                    )
                    
                    if not df.empty:
                        logging.info(f"[{ticker}] 데이터 다운로드 성공 (시도 {attempt + 1})")
                        break
                    else:
                        raise ValueError("Empty DataFrame")
                        
                except Exception as retry_error:
                    logging.warning(f"[{ticker}] 다운로드 시도 {attempt + 1} 실패: {retry_error}")
                    if attempt < max_retries - 1:
                        logging.info(f"[{ticker}] {retry_delay}초 대기 후 재시도...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        # 모든 시도 실패 - 오래된 캐시라도 사용
                        return self._get_expired_cache(ticker)
            
            # 다운로드 성공 시 캐싱
            if not df.empty:
                self._save_cache(ticker, df)
                return df, False  # 새로운 데이터, 캐시 사용 안됨
            else:
                # 빈 데이터인 경우 오래된 캐시 사용
                return self._get_expired_cache(ticker)
                
        except Exception as e:
            logging.error(f"[{ticker}] 데이터 다운로드 실패: {e}")
            # 오래된 캐시라도 사용 시도
            return self._get_expired_cache(ticker)
    
    def _save_cache(self, ticker, df):
        """데이터를 캐시에 저장"""
        try:
            cache_file = self._get_cache_filename(ticker)
            
            # DataFrame을 JSON 호환 형태로 변환
            cache_data = {
                'ticker': ticker,
                'cached_at': datetime.now().isoformat(),
                'data': df.to_dict('index')
            }
            
            # 인덱스(날짜)를 문자열로 변환
            cache_data['data'] = {
                str(date): values for date, values in cache_data['data'].items()
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logging.info(f"[{ticker}] 데이터 캐시 저장 완료")
            
        except Exception as e:
            logging.error(f"[{ticker}] 캐시 저장 실패: {e}")
    
    def _get_expired_cache(self, ticker):
        """만료된 캐시라도 사용 (API 실패 시 fallback)"""
        cache_file = self._get_cache_filename(ticker)
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                logging.warning(f"[{ticker}] API 실패로 인해 만료된 캐시 데이터 사용")
                
                import pandas as pd
                df = pd.DataFrame(cache_data['data'])
                if not df.empty:
                    df.index = pd.to_datetime(df.index)
                    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                
                return df, True  # 만료된 캐시, 캐시 사용됨
                
            except Exception as e:
                logging.error(f"만료된 캐시 로드 실패: {e}")
        
        # 캐시도 없는 경우 빈 DataFrame 반환
        import pandas as pd
        return pd.DataFrame(), False
    
    def clear_cache(self, ticker=None):
        """캐시 삭제"""
        if ticker:
            cache_file = self._get_cache_filename(ticker)
            if os.path.exists(cache_file):
                os.remove(cache_file)
                logging.info(f"[{ticker}] 캐시 삭제 완료")
        else:
            # 모든 캐시 삭제
            for file in os.listdir(self.cache_dir):
                if file.endswith('_cache.json'):
                    os.remove(os.path.join(self.cache_dir, file))
            logging.info("모든 캐시 삭제 완료")

# 전역 인스턴스
data_cache_service = DataCacheService() 