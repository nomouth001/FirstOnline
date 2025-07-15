"""
시장 데이터 다운로드 및 처리 서비스
Yahoo Finance, Alpha Vantage 등 다양한 데이터 소스 지원
"""

import os
import csv
import json
import logging
import time
import requests
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from config import ALTERNATIVE_APIS

# 커스텀 예외 클래스 추가
class RateLimitError(Exception):
    """Rate limit 오류를 위한 커스텀 예외"""
    pass

class YahooFinanceError(Exception):
    """Yahoo Finance 특정 오류를 위한 커스텀 예외"""
    pass


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


def is_korean_stock(ticker):
    """
    한국 주식 여부 확인
    """
    return ticker.endswith('.KS') or ticker.endswith('.KQ')

def normalize_twelve_data_response(data_json, ticker):
    """
    Twelve Data API 응답을 yfinance 형식으로 변환
    """
    try:
        # 데이터 유효성 검사
        if 'status' in data_json and data_json['status'] != 'ok':
            logging.error(f"[{ticker}] Twelve Data API error: {data_json.get('message', 'Unknown error')}")
            return pd.DataFrame()
        
        if 'values' not in data_json:
            logging.error(f"[{ticker}] No values in Twelve Data response")
            return pd.DataFrame()
        
        values = data_json['values']
        if not values:
            logging.error(f"[{ticker}] Empty values in Twelve Data response")
            return pd.DataFrame()
        
        # 데이터 변환
        data_list = []
        for item in values:
            try:
                row = {
                    'Date': pd.to_datetime(item['datetime']),
                    'Open': float(item['open']),
                    'High': float(item['high']),
                    'Low': float(item['low']),
                    'Close': float(item['close']),
                    'Volume': int(float(item['volume'])) if item['volume'] else 0
                }
                data_list.append(row)
            except (KeyError, ValueError) as e:
                logging.warning(f"[{ticker}] Error parsing Twelve Data item: {e}")
                continue
        
        if not data_list:
            logging.error(f"[{ticker}] No valid data points from Twelve Data")
            return pd.DataFrame()
        
        # DataFrame 생성
        df = pd.DataFrame(data_list)
        df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)  # 날짜 순으로 정렬
        
        logging.info(f"[{ticker}] Twelve Data normalized successfully. Shape: {df.shape}")
        return df
        
    except Exception as e:
        logging.error(f"[{ticker}] Error normalizing Twelve Data response: {e}")
        return pd.DataFrame()

def download_from_twelve_data(ticker, max_retries=3):
    """
    Twelve Data API에서 데이터 다운로드
    """
    api_key = ALTERNATIVE_APIS['TWELVE_DATA']['API_KEY']
    base_url = ALTERNATIVE_APIS['TWELVE_DATA']['BASE_URL']
    
    if not api_key:
        logging.error(f"[{ticker}] Twelve Data API key not configured")
        return pd.DataFrame()
    
    logging.info(f"[{ticker}] Downloading from Twelve Data...")
    
    for attempt in range(max_retries):
        try:
            # API 요청 파라미터
            params = {
                'symbol': ticker,
                'interval': '1day',
                'outputsize': 5000,  # 충분한 데이터 요청
                'apikey': api_key
            }
            
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data_json = response.json()
            
            # API 오류 체크
            if 'code' in data_json:
                error_code = data_json['code']
                error_message = data_json.get('message', 'Unknown error')
                
                if error_code == 429:
                    logging.warning(f"[{ticker}] Twelve Data rate limit exceeded: {error_message}")
                    return pd.DataFrame()  # 빈 DataFrame 반환하여 다음 API로 폴백
                elif error_code == 400:
                    logging.error(f"[{ticker}] Twelve Data API error: {error_message}")
                    return pd.DataFrame()
                else:
                    logging.error(f"[{ticker}] Twelve Data API error {error_code}: {error_message}")
                    if attempt < max_retries - 1:
                        time.sleep(5)
                        continue
                    return pd.DataFrame()
            
            # 데이터 정규화
            df = normalize_twelve_data_response(data_json, ticker)
            
            if not df.empty:
                logging.info(f"[{ticker}] Twelve Data download successful. Shape: {df.shape}")
                return df
            else:
                logging.warning(f"[{ticker}] Empty DataFrame from Twelve Data")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return pd.DataFrame()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"[{ticker}] Twelve Data request error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return pd.DataFrame()
        except Exception as e:
            logging.error(f"[{ticker}] Twelve Data download error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return pd.DataFrame()
    
    return pd.DataFrame()

def convert_ticker_for_alpha_vantage(ticker):
    """
    Alpha Vantage용 심볼 변환
    한국 주식: .KS, .KQ 형태 그대로 지원
    """
    # Alpha Vantage는 한국 주식을 .KS, .KQ 형태로 지원
    # 별도 변환 없이 그대로 사용
    return ticker

def download_from_finance_data_reader(ticker, start_date, end_date, max_retries=3):
    """
    FinanceDataReader에서 데이터 다운로드
    """
    logging.info(f"[{ticker}] Downloading from FinanceDataReader...")
    
    for attempt in range(max_retries):
        try:
            # 한국 종목의 경우 .KS, .KQ 접미사 제거
            fdr_ticker = ticker
            if ticker.endswith('.KS') or ticker.endswith('.KQ'):
                fdr_ticker = ticker[:-3]
                logging.info(f"[{ticker}] Converting to FinanceDataReader format: {fdr_ticker}")
            
            # FinanceDataReader로 데이터 다운로드
            df = fdr.DataReader(fdr_ticker, start_date, end_date)
            
            if not df.empty:
                # 컬럼명 정규화 (yfinance 형식에 맞게)
                if 'Adj Close' not in df.columns and 'Close' in df.columns:
                    df['Adj Close'] = df['Close']
                
                # 필요한 컬럼만 선택
                required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                available_columns = [col for col in required_columns if col in df.columns]
                
                if available_columns:
                    df_filtered = df[available_columns].copy()
                    logging.info(f"[{ticker}] FinanceDataReader download successful. Shape: {df_filtered.shape}")
                    return df_filtered
                else:
                    logging.warning(f"[{ticker}] No required columns found in FinanceDataReader data")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return pd.DataFrame()
            else:
                logging.warning(f"[{ticker}] Empty DataFrame from FinanceDataReader")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return pd.DataFrame()
                
        except Exception as e:
            logging.error(f"[{ticker}] FinanceDataReader download error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return pd.DataFrame()
    
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
    
    # 한국 주식은 상위 레벨에서 미리 필터링되므로 여기서는 제거
    
    # 심볼 변환
    alpha_ticker = convert_ticker_for_alpha_vantage(ticker)
    logging.info(f"[{ticker}] Converting to Alpha Vantage format: {alpha_ticker}")
    
    for attempt in range(max_retries):
        try:
            logging.info(f"[{ticker}] Downloading from Alpha Vantage (attempt {attempt + 1}/{max_retries})...")
            
            # API 요청 파라미터
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': alpha_ticker,
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


class RateLimitError(Exception):
    """429 Rate Limit 에러를 나타내는 사용자 정의 예외"""
    pass

def download_from_yahoo_finance(ticker, start_date, end_date, max_retries=3, delay=2):
    """
    Yahoo Finance에서 데이터 다운로드 (429 에러 시 즉시 폴백)
    HTTP 상태코드 기반 오류 처리 개선
    """
    for attempt in range(max_retries):
        try:
            logging.info(f"[{ticker}] Downloading chart data (attempt {attempt + 1}/{max_retries})...")
            
            # 첫 번째 시도가 아니면 지연 시간 적용 (429 에러가 아닌 경우만)
            if attempt > 0:
                wait_time = delay * (2 ** attempt)  # 일반 오류 시 지수 백오프 (4, 8초)
                logging.info(f"[{ticker}] Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            
            # User-Agent 헤더 추가하여 브라우저로 위장
            stock = yf.Ticker(ticker)
            
            # yfinance 내부에서 발생하는 HTTP 오류를 직접 캐치하기 위해 세션 확인
            try:
                stock_data = stock.history(start=start_date, end=end_date, auto_adjust=False)
            except Exception as yf_error:
                # yfinance 내부 오류를 분석하여 HTTP 상태코드 추출
                error_str = str(yf_error)
                
                # HTTP 429 오류 직접 감지
                if '429' in error_str or 'Too Many Requests' in error_str:
                    logging.warning(f"[{ticker}] HTTP 429 (Too Many Requests) detected from Yahoo Finance")
                    raise RateLimitError(f"Yahoo Finance rate limit exceeded: {error_str}")
                
                # JSON 파싱 오류가 429와 함께 발생하는 경우
                if 'Expecting value: line 1 column 1' in error_str:
                    logging.warning(f"[{ticker}] JSON parsing error detected - likely due to rate limiting")
                    # 이 경우 로그에서 HTTP 상태코드 확인을 위해 추가 정보 출력
                    logging.warning(f"[{ticker}] Full error details: {error_str}")
                    raise RateLimitError(f"Yahoo Finance JSON parsing error (likely rate limit): {error_str}")
                
                # 기타 yfinance 오류는 다시 발생시킴
                raise yf_error
            
            if not stock_data.empty:
                logging.info(f"[{ticker}] Chart data downloaded successfully. Shape: {stock_data.shape}")
                return stock_data
            else:
                logging.warning(f"[{ticker}] Empty chart data received on attempt {attempt + 1}")
                
        except RateLimitError:
            # Rate limit 오류는 즉시 다음 API로 폴백
            raise
        except Exception as e:
            error_msg = str(e).lower()
            logging.warning(f"[{ticker}] Chart data download attempt {attempt + 1} failed: {str(e)}")
            
            # 추가적인 rate limit 관련 키워드 검사
            if any(keyword in error_msg for keyword in ['429', 'rate', 'too many', 'quota', 'limit']):
                logging.warning(f"[{ticker}] Rate limit detected in error message, switching to next API immediately")
                raise RateLimitError(f"Yahoo Finance rate limit exceeded: {str(e)}")
            else:
                # 다른 에러의 경우 기존 시퀀스 유지
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)  # 일반 오류 시 지수 백오프
                    logging.info(f"[{ticker}] Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"[{ticker}] All download attempts failed")
                    raise YahooFinanceError(f"Yahoo Finance download failed after {max_retries} attempts: {str(e)}")
    
    return pd.DataFrame()  # 빈 DataFrame 반환


def download_stock_data_with_fallback(ticker, start_date, end_date):
    """
    미국 종목: Yahoo Finance → Twelve Data → Alpha Vantage → FinanceDataReader → 포기
    한국 종목: Yahoo Finance → FinanceDataReader → 포기
    """
    # 한국 종목인지 확인
    if is_korean_stock(ticker):
        logging.info(f"[{ticker}] Korean stock detected, using Yahoo Finance → FinanceDataReader fallback")
        return download_stock_data_korean_fallback(ticker, start_date, end_date)
    else:
        logging.info(f"[{ticker}] US stock detected, using Yahoo Finance priority fallback")
        return download_stock_data_us_fallback(ticker, start_date, end_date)

def download_stock_data_korean_fallback(ticker, start_date, end_date):
    """
    한국 종목: Yahoo Finance → FinanceDataReader → 포기
    """
    # 1. Yahoo Finance 시도
    logging.info(f"[{ticker}] Trying Yahoo Finance for Korean stock...")
    try:
        df = download_from_yahoo_finance(ticker, start_date, end_date, max_retries=2, delay=5)
        if not df.empty:
            logging.info(f"[{ticker}] Yahoo Finance successful")
            return df
    except RateLimitError as e:
        # 429 에러 시 FinanceDataReader로 넘어감
        logging.warning(f"[{ticker}] Yahoo Finance rate limit (429), switching to FinanceDataReader")
        logging.warning(f"[{ticker}] Rate limit details: {e}")
    except Exception as e:
        # 다른 에러의 경우에도 FinanceDataReader로 넘어감
        logging.warning(f"[{ticker}] Yahoo Finance failed: {e}")
    
    # 2. FinanceDataReader 시도
    logging.info(f"[{ticker}] Trying FinanceDataReader for Korean stock...")
    df = download_from_finance_data_reader(ticker, start_date, end_date)
    if not df.empty:
        logging.info(f"[{ticker}] FinanceDataReader successful. Final shape: {df.shape}")
        return df
    else:
        logging.info(f"[{ticker}] FinanceDataReader failed")
    
    # 3. 모든 API 실패
    logging.error(f"[{ticker}] ❌ 종목분석 진행불가: 모든 데이터 소스 실패")
    return pd.DataFrame()

def download_stock_data_us_fallback(ticker, start_date, end_date):
    """
    미국 종목: Yahoo Finance → Twelve Data → Alpha Vantage → FinanceDataReader → 포기
    """
    # 1. Yahoo Finance 시도
    logging.info(f"[{ticker}] Trying Yahoo Finance first...")
    try:
        df = download_from_yahoo_finance(ticker, start_date, end_date, max_retries=2, delay=5)
        if not df.empty:
            logging.info(f"[{ticker}] Yahoo Finance successful")
            return df
    except RateLimitError as e:
        # 429 에러 시 바로 다음 소스로 넘어감 (기다리거나 재시도 안함)
        logging.warning(f"[{ticker}] Yahoo Finance rate limit (429), switching to Twelve Data")
        logging.warning(f"[{ticker}] Rate limit details: {e}")
    except Exception as e:
        # 다른 에러는 기존 알고리즘 유지 (재시도 등)
        logging.warning(f"[{ticker}] Yahoo Finance failed: {e}")
    
    # 2. Twelve Data 폴백
    logging.info(f"[{ticker}] Trying Twelve Data...")
    df = download_from_twelve_data(ticker)
    if not df.empty:
        # 요청된 날짜 범위로 필터링
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        logging.info(f"[{ticker}] Twelve Data successful. Final shape: {df.shape}")
        return df
    else:
        logging.info(f"[{ticker}] Twelve Data failed, trying Alpha Vantage...")
    
    # 3. Alpha Vantage 시도
    df = download_from_alpha_vantage(ticker)
    if not df.empty:
        # 요청된 날짜 범위로 필터링
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        logging.info(f"[{ticker}] Alpha Vantage successful. Final shape: {df.shape}")
        return df
    else:
        logging.info(f"[{ticker}] Alpha Vantage failed, trying FinanceDataReader...")
    
    # 4. FinanceDataReader 마지막 시도
    df = download_from_finance_data_reader(ticker, start_date, end_date)
    if not df.empty:
        logging.info(f"[{ticker}] FinanceDataReader successful. Final shape: {df.shape}")
        return df
    else:
        logging.info(f"[{ticker}] FinanceDataReader failed")
    
    # 5. 모든 API 실패
    logging.error(f"[{ticker}] ❌ 종목분석 진행불가: 모든 데이터 소스 실패")
    return pd.DataFrame()


# 레거시 호환성을 위한 별칭
download_stock_data_with_retry = download_from_yahoo_finance 