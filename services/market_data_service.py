"""
시장 데이터 다운로드 및 처리 서비스
Yahoo Finance, Alpha Vantage 등 다양한 데이터 소스 지원
"""

import logging
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from config import ALTERNATIVE_APIS


def normalize_alpha_vantage_data(data_json, ticker):
    """
    Alpha Vantage API 응답을 yfinance 형식으로 변환
    """
    try:
        # Time Series 데이터 추출
        time_series_key = None
        for key in data_json.keys():
            if 'Time Series' in key:
                time_series_key = key
                break
        
        if not time_series_key:
            logging.error(f"[{ticker}] No time series data found in Alpha Vantage response")
            return pd.DataFrame()
        
        time_series = data_json[time_series_key]
        
        # 데이터 변환
        data_list = []
        for date_str, values in time_series.items():
            row = {
                'Date': pd.to_datetime(date_str),
                'Open': float(values.get('1. open', 0)),
                'High': float(values.get('2. high', 0)),
                'Low': float(values.get('3. low', 0)),
                'Close': float(values.get('4. close', 0)),
                'Volume': int(float(values.get('5. volume', 0)))
            }
            data_list.append(row)
        
        # DataFrame 생성
        df = pd.DataFrame(data_list)
        df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)  # 날짜 순으로 정렬
        
        logging.info(f"[{ticker}] Alpha Vantage data normalized. Shape: {df.shape}")
        return df
        
    except Exception as e:
        logging.error(f"[{ticker}] Error normalizing Alpha Vantage data: {e}")
        return pd.DataFrame()


def download_from_alpha_vantage(ticker, max_retries=3):
    """
    Alpha Vantage API에서 데이터 다운로드
    """
    api_key = ALTERNATIVE_APIS['ALPHA_VANTAGE']['API_KEY']
    base_url = ALTERNATIVE_APIS['ALPHA_VANTAGE']['BASE_URL']
    
    if not api_key:
        logging.error(f"[{ticker}] Alpha Vantage API key not configured")
        return pd.DataFrame()
    
    for attempt in range(max_retries):
        try:
            logging.info(f"[{ticker}] Downloading from Alpha Vantage (attempt {attempt + 1}/{max_retries})...")
            
            # API 요청 파라미터
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': ticker,
                'outputsize': 'full',  # 최대 20년 데이터
                'apikey': api_key
            }
            
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data_json = response.json()
            
            # API 오류 체크
            if 'Error Message' in data_json:
                logging.error(f"[{ticker}] Alpha Vantage API error: {data_json['Error Message']}")
                return pd.DataFrame()
            
            if 'Note' in data_json:
                logging.warning(f"[{ticker}] Alpha Vantage rate limit: {data_json['Note']}")
                if attempt < max_retries - 1:
                    time.sleep(60)  # 1분 대기
                    continue
                return pd.DataFrame()
            
            # 데이터 정규화
            df = normalize_alpha_vantage_data(data_json, ticker)
            
            if not df.empty:
                logging.info(f"[{ticker}] Alpha Vantage data downloaded successfully. Shape: {df.shape}")
                return df
            
        except Exception as e:
            logging.error(f"[{ticker}] Alpha Vantage download attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            
    return pd.DataFrame()


def download_from_yahoo_finance(ticker, start_date, end_date, max_retries=3, delay=2):
    """
    Yahoo Finance에서 데이터 다운로드 (개선된 retry 로직 포함)
    """
    for attempt in range(max_retries):
        try:
            logging.info(f"[{ticker}] Downloading chart data (attempt {attempt + 1}/{max_retries})...")
            
            # 첫 번째 시도가 아니면 더 긴 지연 시간 적용
            if attempt > 0:
                wait_time = delay * (5 ** attempt)  # 10, 50초로 지연 시간 대폭 증가
                logging.info(f"[{ticker}] Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            
            # User-Agent 헤더 추가하여 브라우저로 위장
            stock = yf.Ticker(ticker)
            stock_data = stock.history(start=start_date, end=end_date, auto_adjust=False)
            
            if not stock_data.empty:
                logging.info(f"[{ticker}] Chart data downloaded successfully. Shape: {stock_data.shape}")
                return stock_data
            else:
                logging.warning(f"[{ticker}] Empty chart data received on attempt {attempt + 1}")
                
        except Exception as e:
            error_msg = str(e).lower()
            logging.warning(f"[{ticker}] Chart data download attempt {attempt + 1} failed: {str(e)}")
            
            # 429 오류나 rate limit 관련 오류인 경우 더 긴 대기
            if '429' in error_msg or 'rate' in error_msg or 'too many' in error_msg:
                if attempt < max_retries - 1:
                    wait_time = delay * (5 ** attempt)  # 429 오류 시 더 긴 대기 (2, 10, 50초)
                    logging.info(f"[{ticker}] Rate limit detected, waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"[{ticker}] Rate limit exceeded, all attempts failed")
                    raise e
            else:
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)  # 일반 오류 시 지수 백오프
                    logging.info(f"[{ticker}] Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"[{ticker}] All download attempts failed")
                    raise e
    
    return pd.DataFrame()  # 빈 DataFrame 반환


def download_stock_data_with_fallback(ticker, start_date, end_date):
    """
    Yahoo Finance 시도 → 실패 시 Alpha Vantage 폴백
    """
    # 1. Yahoo Finance 시도
    logging.info(f"[{ticker}] Trying Yahoo Finance first...")
    try:
        df = download_from_yahoo_finance(ticker, start_date, end_date, max_retries=2, delay=5)
        if not df.empty:
            logging.info(f"[{ticker}] Yahoo Finance successful")
            return df
    except Exception as e:
        logging.warning(f"[{ticker}] Yahoo Finance failed: {e}")
    
    # 2. Alpha Vantage 폴백
    logging.info(f"[{ticker}] Falling back to Alpha Vantage...")
    df = download_from_alpha_vantage(ticker)
    
    if not df.empty:
        # 요청된 날짜 범위로 필터링
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        logging.info(f"[{ticker}] Alpha Vantage fallback successful. Final shape: {df.shape}")
    else:
        logging.error(f"[{ticker}] Both Yahoo Finance and Alpha Vantage failed")
    
    return df


# 레거시 호환성을 위한 별칭
download_stock_data_with_retry = download_from_yahoo_finance 