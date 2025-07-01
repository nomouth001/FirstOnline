import os
import base64
import logging
import pandas as pd
import yfinance as yf
import ta
from ta.volatility import BollingerBands
from ta.trend import IchimokuIndicator
from datetime import datetime, timedelta
import google.generativeai as genai
import requests
from flask import render_template, current_app
from config import ANALYSIS_DIR, DEBUG_DIR, GOOGLE_API_KEY, CHART_DIR, GEMINI_MODEL_VERSION
from utils.file_manager import get_date_folder_path
from models import _extract_summary_from_analysis
import json
import numpy as np
from tasks.newsletter_tasks import run_bulk_analysis_for_user

logger = logging.getLogger(__name__)

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

def is_valid_analysis_file(file_path):
    """
    기존 분석 파일이 유효한 AI 분석을 포함하고 있는지 확인합니다.
    """
    try:
        if not os.path.exists(file_path):
            return False
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # AI 분석이 제대로 되어 있는지 확인
        # Gemini 분석이 실패 메시지가 아니고, 실제 분석 내용이 있는지 확인
        if "[Gemini 분석 실패" in content or "[Gemini 분석 실패]" in content:
            return False
            
        # OpenAI 분석이 실패 메시지가 아니고, 실제 분석 내용이 있는지 확인
        if "[OpenAI 분석 실패" in content or "[OpenAI 분석 실패]" in content:
            return False
            
        # 분석 내용이 너무 짧으면 유효하지 않음
        if len(content) < 100:
            return False
            
        # 실제 분석 내용이 있는지 확인 (핵심 요약 등)
        if "**핵심 요약**" not in content and "요약" not in content:
            return False
            
        return True
        
    except Exception as e:
        logging.error(f"Error checking analysis file validity: {e}")
        return False

def analyze_ticker_internal(ticker):
    """
    내부 API 호출용 분석 함수. JSON 응답만 반환합니다.
    """
    ticker = ticker.upper()
    
    today_date_str = datetime.today().strftime("%Y%m%d")
    html_file_name = f"{ticker}_{today_date_str}.html"
    analysis_html_path = os.path.join(ANALYSIS_DIR, html_file_name)

    # 기존 분석 파일 확인 및 유효성 검사
    if os.path.exists(analysis_html_path):
        if is_valid_analysis_file(analysis_html_path):
            # 유효한 기존 파일이 있으면 사용자에게 확인 요청
            return {
                "analysis_gemini": "[기존 파일 존재]",
                "analysis_openai": "[기존 파일 존재]",
                "summary_gemini": "기존 파일 존재",
                "summary_openai": "기존 파일 존재",
                "success": False,
                "existing_file": True,
                "file_path": analysis_html_path,
                "message": f"{ticker} 종목의 {today_date_str} 분석 파일이 이미 존재합니다. 새로 생성하시겠습니까?"
            }, 409  # 409 Conflict 상태 코드 사용
        else:
            # 기존 파일이 있지만 유효하지 않으면 새로 생성
            logging.info(f"[{ticker}] Existing analysis file is invalid, will create new one")
            try:
                os.remove(analysis_html_path)
                logging.info(f"[{ticker}] Removed invalid analysis file: {analysis_html_path}")
            except Exception as e:
                logging.warning(f"[{ticker}] Failed to remove invalid analysis file: {e}")

    # 기존 파일이 없거나 유효하지 않으면 새로 생성
    return analyze_ticker_internal_logic(ticker, analysis_html_path)

def analyze_ticker_internal_logic(ticker, analysis_html_path):
    """
    analyze_ticker_internal의 실제 분석 로직을 담당하는 함수
    """
    logging.info(f"[{ticker}] Starting AI analysis process...")
    charts = {
        "Daily": None, "Weekly": None, "Monthly": None
    }
    
    display_date = datetime.today().strftime("%Y-%m-%d")

    # 차트 이미지 경로 설정 (최신 날짜 파일 찾기)
    logging.info(f"[{ticker}] Looking for chart files...")
    found_all_charts = True
    for label in ["Daily", "Weekly", "Monthly"]:
        # 날짜별 폴더 구조를 고려하여 모든 날짜 폴더에서 차트 파일 검색
        chart_files = []
        if os.path.exists(CHART_DIR):
            for date_folder in os.listdir(CHART_DIR):
                date_folder_path = os.path.join(CHART_DIR, date_folder)
                if os.path.isdir(date_folder_path) and date_folder.isdigit() and len(date_folder) == 8:
                    # 해당 날짜 폴더에서 차트 파일 검색
                    folder_chart_files = [f for f in os.listdir(date_folder_path) 
                                        if f.startswith(f"{ticker}_{label.lower()}_") and f.endswith(".png")]
                    for cf in folder_chart_files:
                        chart_files.append((date_folder, cf))
        
        latest_file = None
        latest_date_in_files = None

        for date_folder, cf in chart_files:
            try:
                parts = cf.split('_')
                if len(parts) >= 3:
                    file_date_str = parts[2].split('.')[0]
                    file_date = datetime.strptime(file_date_str, "%Y%m%d")
                    if latest_date_in_files is None or file_date > latest_date_in_files:
                        latest_date_in_files = file_date
                        latest_file = (date_folder, cf)
            except ValueError:
                continue

        if latest_file:
            date_folder, cf = latest_file
            charts[label] = os.path.join(CHART_DIR, date_folder, cf)
            # 현재 차트 파일의 날짜를 기준으로 display_date를 업데이트
            if latest_date_in_files:
                 display_date = latest_date_in_files.strftime("%Y-%m-%d")
            logging.info(f"[{ticker}] Found {label} chart: {cf}")
        else:
            found_all_charts = False
            logging.warning(f"[{ticker}] No {label} chart found")
            # 차트 이미지가 없으면 JSON 반환
            return {
                "analysis_gemini": "[차트 이미지 없음]",
                "analysis_openai": "[차트 이미지 없음]",
                "summary_gemini": "차트 이미지 없음",
                "summary_openai": "차트 이미지 없음",
                "success": False
            }, 404

    logging.info(f"[{ticker}] Chart files found: Daily={charts['Daily'] is not None}, Weekly={charts['Weekly'] is not None}, Monthly={charts['Monthly'] is not None}")

    # 이미지 인코딩 함수
    def encode_image(path):
        # path가 None일 경우 빈 문자열 반환
        if path is None:
            return ""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    logging.info(f"[{ticker}] Encoding chart images...")
    daily_b64 = encode_image(charts["Daily"])
    weekly_b64 = encode_image(charts["Weekly"])
    monthly_b64 = encode_image(charts["Monthly"])
    logging.info(f"[{ticker}] Chart images encoded successfully")

    # 공통 프롬프트 생성 (AI 분석 재시도 시에도 동일하게 사용)
    try:
        logging.info(f"[{ticker}] Starting data preparation and indicator calculation...")
        data_end_date = datetime.strptime(display_date, "%Y-%m-%d")
        data_fetch_start_date = data_end_date - timedelta(days=5*365 + 60)

        logging.info(f"[{ticker}] Downloading stock data from yfinance...")
        stock_data_full = yf.Ticker(ticker).history(start=data_fetch_start_date, end=data_end_date + timedelta(days=1), auto_adjust=False)
        logging.info(f"[{ticker}] Stock data downloaded. Shape: {stock_data_full.shape}")
        
        if stock_data_full.empty:
             raise ValueError(f"No stock data found for {ticker} for indicator calculation up to {data_end_date.strftime('%Y-%m-%d')}.")

        if stock_data_full.index.tz is not None:
            stock_data_full.index = stock_data_full.index.tz_localize(None)

        stock_data = stock_data_full[stock_data_full.index <= data_end_date]
        if stock_data.empty:
             raise ValueError(f"Filtered stock data up to {data_end_date.strftime('%Y-%m-%d')} is empty.")

        logging.info(f"[{ticker}] Stock data filtered. Shape: {stock_data.shape}")

        def safe_last_value(series):
            return series.iloc[-1] if not series.empty and not series.isnull().all() else float('nan')

        def get_key_data_points(df, num_points=30):
            """주요 데이터 포인트 추출 (최신값 + 과거 주요 지점들)"""
            if df.empty:
                return []
            
            # 최신 데이터
            latest_data = {
                'date': df.index[-1].strftime('%Y-%m-%d'),
                'close': df['Close'].iloc[-1],
                'volume': df['Volume'].iloc[-1] if 'Volume' in df.columns else None,
                'ema5': df['EMA5'].iloc[-1] if 'EMA5' in df.columns else None,
                'ema20': df['EMA20'].iloc[-1] if 'EMA20' in df.columns else None,
                'ema40': df['EMA40'].iloc[-1] if 'EMA40' in df.columns else None,
                'macd': df['MACD_TA'].iloc[-1] if 'MACD_TA' in df.columns else None,
                'macd_signal': df['MACD_Signal_TA'].iloc[-1] if 'MACD_Signal_TA' in df.columns else None,
                'macd_hist': df['MACD_Hist_TA'].iloc[-1] if 'MACD_Hist_TA' in df.columns else None,
                'bb_upper': df['BB_Upper'].iloc[-1] if 'BB_Upper' in df.columns else None,
                'bb_lower': df['BB_Lower'].iloc[-1] if 'BB_Lower' in df.columns else None,
                'bb_ma': df['BB_MA'].iloc[-1] if 'BB_MA' in df.columns else None,
                'ichimoku_conv': df['Ichimoku_Conversion'].iloc[-1] if 'Ichimoku_Conversion' in df.columns else None,
                'ichimoku_base': df['Ichimoku_Base'].iloc[-1] if 'Ichimoku_Base' in df.columns else None,
                'ichimoku_spana': df['Ichimoku_SpanA'].iloc[-1] if 'Ichimoku_SpanA' in df.columns else None,
                'ichimoku_spanb': df['Ichimoku_SpanB'].iloc[-1] if 'Ichimoku_SpanB' in df.columns else None,
                'ichimoku_lag': df['Ichimoku_Lagging'].iloc[-1] if 'Ichimoku_Lagging' in df.columns else None
            }
            
            # 과거 주요 지점들 (최근 30개 데이터 포인트)
            historical_points = []
            step = max(1, len(df) // num_points)
            
            for i in range(0, len(df), step):
                if i < len(df) - 1:  # 최신값은 제외
                    point = {
                        'date': df.index[i].strftime('%Y-%m-%d'),
                        'close': df['Close'].iloc[i],
                        'volume': df['Volume'].iloc[i] if 'Volume' in df.columns else None,
                        'ema5': df['EMA5'].iloc[i] if 'EMA5' in df.columns else None,
                        'ema20': df['EMA20'].iloc[i] if 'EMA20' in df.columns else None,
                        'ema40': df['EMA40'].iloc[i] if 'EMA40' in df.columns else None,
                        'macd': df['MACD_TA'].iloc[i] if 'MACD_TA' in df.columns else None,
                        'macd_signal': df['MACD_Signal_TA'].iloc[i] if 'MACD_Signal_TA' in df.columns else None,
                        'macd_hist': df['MACD_Hist_TA'].iloc[i] if 'MACD_Hist_TA' in df.columns else None,
                        'bb_upper': df['BB_Upper'].iloc[i] if 'BB_Upper' in df.columns else None,
                        'bb_lower': df['BB_Lower'].iloc[i] if 'BB_Lower' in df.columns else None,
                        'bb_ma': df['BB_MA'].iloc[i] if 'BB_MA' in df.columns else None,
                        'ichimoku_conv': df['Ichimoku_Conversion'].iloc[i] if 'Ichimoku_Conversion' in df.columns else None,
                        'ichimoku_base': df['Ichimoku_Base'].iloc[i] if 'Ichimoku_Base' in df.columns else None,
                        'ichimoku_spana': df['Ichimoku_SpanA'].iloc[i] if 'Ichimoku_SpanA' in df.columns else None,
                        'ichimoku_spanb': df['Ichimoku_SpanB'].iloc[i] if 'Ichimoku_SpanB' in df.columns else None,
                        'ichimoku_lag': df['Ichimoku_Lagging'].iloc[i] if 'Ichimoku_Lagging' in df.columns else None
                    }
                    historical_points.append(point)
            
            return [latest_data] + historical_points[-29:]  # 최신값 + 과거 29개 지점

        def get_ohlcv_data_points(df, num_points=30):
            """OHLCV 데이터만 추출 (원본 주가 데이터)"""
            if df.empty:
                return []
            
            # 최근 30개 데이터 포인트 추출
            data_points = []
            start_idx = max(0, len(df) - num_points)
            
            for i in range(start_idx, len(df)):
                point = {
                    'date': df.index[i].strftime('%Y-%m-%d'),
                    'open': df['Open'].iloc[i],
                    'high': df['High'].iloc[i], 
                    'low': df['Low'].iloc[i],
                    'close': df['Close'].iloc[i],
                    'volume': df['Volume'].iloc[i] if 'Volume' in df.columns else 0
                }
                data_points.append(point)
            
            return data_points

        def format_ohlcv_data(data_points, timeframe):
            """OHLCV 데이터를 문자열로 포맷팅"""
            if not data_points:
                return f"[{timeframe} 데이터 없음]"
            
            result = []
            for point in data_points:
                point_str = f"{point['date']}: 시가 {point['open']:.2f}, 고가 {point['high']:.2f}, 저가 {point['low']:.2f}, 종가 {point['close']:.2f}, 거래량 {point['volume']:,.0f}"
                result.append(point_str)
            
            return '\n'.join(result)

        daily_start_limit = data_end_date - timedelta(days=90)
        daily_df = stock_data[stock_data.index >= daily_start_limit].copy()
        
        if daily_df.empty or len(daily_df) < 40:
             raise ValueError(f"Insufficient daily data ({len(daily_df)} points) for indicators up to {data_end_date.strftime('%Y-%m-%d')}.")

        daily_df['EMA5'] = ta.trend.ema_indicator(daily_df['Close'], window=5)
        daily_df['EMA20'] = ta.trend.ema_indicator(daily_df['Close'], window=20)
        daily_df['EMA40'] = ta.trend.ema_indicator(daily_df['Close'], window=40)
        # MACD (ta)
        daily_df['MACD_TA'] = ta.trend.macd(daily_df['Close'])
        daily_df['MACD_Signal_TA'] = ta.trend.macd_signal(daily_df['Close'])
        daily_df['MACD_Hist_TA'] = ta.trend.macd_diff(daily_df['Close'])

        # 볼린저 밴드 계산 추가
        bollinger = BollingerBands(close=daily_df["Close"], window=20, window_dev=2)
        daily_df["BB_Upper"] = bollinger.bollinger_hband()
        daily_df["BB_Lower"] = bollinger.bollinger_lband()
        daily_df["BB_MA"] = bollinger.bollinger_mavg()

        # 일목균형표 계산
        daily_ichimoku = IchimokuIndicator(high=daily_df["High"], low=daily_df["Low"])
        daily_df["Ichimoku_Conversion"] = daily_ichimoku.ichimoku_conversion_line()
        daily_df["Ichimoku_Base"] = daily_ichimoku.ichimoku_base_line()
        daily_df["Ichimoku_SpanA"] = daily_ichimoku.ichimoku_a()
        daily_df["Ichimoku_SpanB"] = daily_ichimoku.ichimoku_b()
        # 후행스팬은 종가를 26일 뒤로 이동
        daily_df["Ichimoku_Lagging"] = daily_df["Close"].shift(26)

        daily_df.dropna(subset=['EMA40', 'MACD_Hist_TA', 'BB_Upper', 'BB_Lower', 'BB_MA'], inplace=True)
        if daily_df.empty:
            raise ValueError("Daily DataFrame became empty after indicator calculation and NaN drop.")

        weekly_df_resampled = stock_data.resample('W').agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna().copy()
        weekly_start_limit = data_end_date - timedelta(weeks=52*2 + 4)
        weekly_df = weekly_df_resampled[weekly_df_resampled.index >= weekly_start_limit].copy()
        
        if weekly_df.empty or len(weekly_df) < 40:
            raise ValueError(f"Insufficient weekly data ({len(weekly_df)} points) for indicators up to {data_end_date.strftime('%Y-%m-%d')}.")

        weekly_df['EMA5'] = ta.trend.ema_indicator(weekly_df['Close'], window=5)
        weekly_df['EMA20'] = ta.trend.ema_indicator(weekly_df['Close'], window=20)
        weekly_df['EMA40'] = ta.trend.ema_indicator(weekly_df['Close'], window=40)
        # MACD (ta)
        weekly_df['MACD_TA'] = ta.trend.macd(weekly_df['Close'])
        weekly_df['MACD_Signal_TA'] = ta.trend.macd_signal(weekly_df['Close'])
        weekly_df['MACD_Hist_TA'] = ta.trend.macd_diff(weekly_df['Close'])

        weekly_bollinger = BollingerBands(close=weekly_df["Close"], window=20, window_dev=2)
        weekly_df["BB_Upper"] = weekly_bollinger.bollinger_hband()
        weekly_df["BB_Lower"] = weekly_bollinger.bollinger_lband()
        weekly_df["BB_MA"] = weekly_bollinger.bollinger_mavg()

        # 일목균형표 계산
        weekly_ichimoku = IchimokuIndicator(high=weekly_df["High"], low=weekly_df["Low"])
        weekly_df["Ichimoku_Conversion"] = weekly_ichimoku.ichimoku_conversion_line()
        weekly_df["Ichimoku_Base"] = weekly_ichimoku.ichimoku_base_line()
        weekly_df["Ichimoku_SpanA"] = weekly_ichimoku.ichimoku_a()
        weekly_df["Ichimoku_SpanB"] = weekly_ichimoku.ichimoku_b()
        # 후행스팬은 종가를 26일 뒤로 이동
        weekly_df["Ichimoku_Lagging"] = weekly_df["Close"].shift(26)

        weekly_df.dropna(subset=['EMA40', 'MACD_Hist_TA', 'BB_Upper', 'BB_Lower', 'BB_MA'], inplace=True)
        if weekly_df.empty:
            raise ValueError("Weekly DataFrame became empty after indicator calculation and NaN drop.")

        monthly_df_resampled = stock_data.resample('M').agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna().copy()
        monthly_start_limit = data_end_date - timedelta(weeks=52*5 + 8)
        monthly_df = monthly_df_resampled[monthly_df_resampled.index >= monthly_start_limit].copy()
        
        if monthly_df.empty or len(monthly_df) < 40:
            raise ValueError(f"Insufficient monthly data ({len(monthly_df)} points) for indicators up to {data_end_date.strftime('%Y-%m-%d')}.")

        monthly_df['EMA5'] = ta.trend.ema_indicator(monthly_df['Close'], window=5)
        monthly_df['EMA20'] = ta.trend.ema_indicator(monthly_df['Close'], window=20)
        monthly_df['EMA40'] = ta.trend.ema_indicator(monthly_df['Close'], window=40)
        # MACD (ta)
        monthly_df['MACD_TA'] = ta.trend.macd(monthly_df['Close'])
        monthly_df['MACD_Signal_TA'] = ta.trend.macd_signal(monthly_df['Close'])
        monthly_df['MACD_Hist_TA'] = ta.trend.macd_diff(monthly_df['Close'])

        monthly_bollinger = BollingerBands(close=monthly_df["Close"], window=20, window_dev=2)
        monthly_df["BB_Upper"] = monthly_bollinger.bollinger_hband()
        monthly_df["BB_Lower"] = monthly_bollinger.bollinger_lband()
        monthly_df["BB_MA"] = monthly_bollinger.bollinger_mavg()

        # 일목균형표 계산
        monthly_ichimoku = IchimokuIndicator(high=monthly_df["High"], low=monthly_df["Low"])
        monthly_df["Ichimoku_Conversion"] = monthly_ichimoku.ichimoku_conversion_line()
        monthly_df["Ichimoku_Base"] = monthly_ichimoku.ichimoku_base_line()
        monthly_df["Ichimoku_SpanA"] = monthly_ichimoku.ichimoku_a()
        monthly_df["Ichimoku_SpanB"] = monthly_ichimoku.ichimoku_b()
        # 후행스팬은 종가를 26일 뒤로 이동
        monthly_df["Ichimoku_Lagging"] = monthly_df["Close"].shift(26)

        monthly_df.dropna(subset=['EMA40', 'MACD_Hist_TA', 'BB_Upper', 'BB_Lower', 'BB_MA'], inplace=True)
        if monthly_df.empty:
            raise ValueError("Monthly DataFrame became empty after indicator calculation and NaN drop.")

        # 주요 데이터 포인트 추출
        daily_data_points = get_key_data_points(daily_df, 30)
        weekly_data_points = get_key_data_points(weekly_df, 30)
        monthly_data_points = get_key_data_points(monthly_df, 30)

        # 데이터 포인트를 문자열로 변환하는 함수
        def format_data_points(data_points, timeframe):
            if not data_points:
                return f"[{timeframe} 데이터 없음]"
            
            result = []
            for i, point in enumerate(data_points):
                if i == 0:
                    prefix = f"**최신 ({timeframe})**: "
                else:
                    prefix = f"**{point['date']} ({timeframe})**: "
                
                point_str = f"{prefix}종가: {point['close']:.2f}"
                if point.get('volume') is not None:
                    point_str += f", 거래량: {point['volume']:,.0f}"
                if point['ema5'] is not None:
                    point_str += f", EMA5: {point['ema5']:.2f}"
                if point['ema20'] is not None:
                    point_str += f", EMA20: {point['ema20']:.2f}"
                if point['ema40'] is not None:
                    point_str += f", EMA40: {point['ema40']:.2f}"
                if point['macd'] is not None:
                    point_str += f", MACD: {point['macd']:.2f}"
                if point['macd_signal'] is not None:
                    point_str += f", MACD_Signal: {point['macd_signal']:.2f}"
                if point['macd_hist'] is not None:
                    point_str += f", MACD_Hist: {point['macd_hist']:.2f}"
                if point['bb_upper'] is not None:
                    point_str += f", BB_Upper: {point['bb_upper']:.2f}"
                if point['bb_lower'] is not None:
                    point_str += f", BB_Lower: {point['bb_lower']:.2f}"
                if point['bb_ma'] is not None:
                    point_str += f", BB_MA: {point['bb_ma']:.2f}"
                if point['ichimoku_conv'] is not None:
                    point_str += f", Ichimoku_Conv: {point['ichimoku_conv']:.2f}"
                if point['ichimoku_base'] is not None:
                    point_str += f", Ichimoku_Base: {point['ichimoku_base']:.2f}"
                if point['ichimoku_spana'] is not None:
                    point_str += f", Ichimoku_SpanA: {point['ichimoku_spana']:.2f}"
                if point['ichimoku_spanb'] is not None:
                    point_str += f", Ichimoku_SpanB: {point['ichimoku_spanb']:.2f}"
                if point['ichimoku_lag'] is not None:
                    point_str += f", Ichimoku_Lag: {point['ichimoku_lag']:.2f}"
                
                result.append(point_str)
            
            return "\n".join(result)

        current_close = safe_last_value(stock_data['Close'])

        # 거래량 데이터 추출
        volume_daily = safe_last_value(daily_df['Volume'])
        volume_weekly = safe_last_value(weekly_df['Volume'])
        volume_monthly = safe_last_value(monthly_df['Volume'])

        # 개별 지표 값들 계산 (원래 방식)
        ema_daily_5 = safe_last_value(daily_df['EMA5'])
        ema_daily_20 = safe_last_value(daily_df['EMA20'])
        ema_daily_40 = safe_last_value(daily_df['EMA40'])
        macd_line_daily = safe_last_value(daily_df['MACD_TA'])
        macd_signal_daily = safe_last_value(daily_df['MACD_Signal_TA'])
        macd_hist_daily = safe_last_value(daily_df['MACD_Hist_TA'])
        bb_upper_daily = safe_last_value(daily_df['BB_Upper'])
        bb_lower_daily = safe_last_value(daily_df['BB_Lower'])
        bb_ma_daily = safe_last_value(daily_df['BB_MA'])
        ichimoku_conv_daily = safe_last_value(daily_df['Ichimoku_Conversion'])
        ichimoku_base_daily = safe_last_value(daily_df['Ichimoku_Base'])
        ichimoku_spana_daily = safe_last_value(daily_df['Ichimoku_SpanA'])
        ichimoku_spanb_daily = safe_last_value(daily_df['Ichimoku_SpanB'])
        ichimoku_lag_daily = safe_last_value(daily_df['Ichimoku_Lagging'])

        ema_weekly_5 = safe_last_value(weekly_df['EMA5'])
        ema_weekly_20 = safe_last_value(weekly_df['EMA20'])
        ema_weekly_40 = safe_last_value(weekly_df['EMA40'])
        macd_line_weekly = safe_last_value(weekly_df['MACD_TA'])
        macd_signal_weekly = safe_last_value(weekly_df['MACD_Signal_TA'])
        macd_hist_weekly = safe_last_value(weekly_df['MACD_Hist_TA'])
        bb_upper_weekly = safe_last_value(weekly_df['BB_Upper'])
        bb_lower_weekly = safe_last_value(weekly_df['BB_Lower'])
        bb_ma_weekly = safe_last_value(weekly_df['BB_MA'])
        ichimoku_conv_weekly = safe_last_value(weekly_df['Ichimoku_Conversion'])
        ichimoku_base_weekly = safe_last_value(weekly_df['Ichimoku_Base'])
        ichimoku_spana_weekly = safe_last_value(weekly_df['Ichimoku_SpanA'])
        ichimoku_spanb_weekly = safe_last_value(weekly_df['Ichimoku_SpanB'])
        ichimoku_lag_weekly = safe_last_value(weekly_df['Ichimoku_Lagging'])

        ema_monthly_5 = safe_last_value(monthly_df['EMA5'])
        ema_monthly_20 = safe_last_value(monthly_df['EMA20'])
        ema_monthly_40 = safe_last_value(monthly_df['EMA40'])
        macd_line_monthly = safe_last_value(monthly_df['MACD_TA'])
        macd_signal_monthly = safe_last_value(monthly_df['MACD_Signal_TA'])
        macd_hist_monthly = safe_last_value(monthly_df['MACD_Hist_TA'])
        bb_upper_monthly = safe_last_value(monthly_df['BB_Upper'])
        bb_lower_monthly = safe_last_value(monthly_df['BB_Lower'])
        bb_ma_monthly = safe_last_value(monthly_df['BB_MA'])
        ichimoku_conv_monthly = safe_last_value(monthly_df['Ichimoku_Conversion'])
        ichimoku_base_monthly = safe_last_value(monthly_df['Ichimoku_Base'])
        ichimoku_spana_monthly = safe_last_value(monthly_df['Ichimoku_SpanA'])
        ichimoku_spanb_monthly = safe_last_value(monthly_df['Ichimoku_SpanB'])
        ichimoku_lag_monthly = safe_last_value(monthly_df['Ichimoku_Lagging'])

        # 프롬프트 템플릿 로드
        prompt_template = load_ai_prompt_template()
        if prompt_template is None:
            raise ValueError("AI 프롬프트 템플릿을 로드할 수 없습니다.")
        
        # 시계열 데이터를 문자열로 포맷팅
        daily_time_series = format_data_points(daily_data_points, "일봉")
        weekly_time_series = format_data_points(weekly_data_points, "주봉")
        monthly_time_series = format_data_points(monthly_data_points, "월봉")

        # OHLCV 원본 데이터 추출 (지표 계산 전 원본 주가 데이터)
        daily_ohlcv_data_points = get_ohlcv_data_points(stock_data[stock_data.index >= daily_start_limit], 30)
        weekly_ohlcv_data_points = get_ohlcv_data_points(weekly_df_resampled[weekly_df_resampled.index >= weekly_start_limit], 30)
        monthly_ohlcv_data_points = get_ohlcv_data_points(monthly_df_resampled[monthly_df_resampled.index >= monthly_start_limit], 30)

        # OHLCV 데이터를 문자열로 포맷팅
        daily_ohlcv_data = format_ohlcv_data(daily_ohlcv_data_points, "일봉")
        weekly_ohlcv_data = format_ohlcv_data(weekly_ohlcv_data_points, "주봉")
        monthly_ohlcv_data = format_ohlcv_data(monthly_ohlcv_data_points, "월봉")

        # 프롬프트 템플릿에 실제 데이터 삽입
        common_prompt = prompt_template.format(
            ticker=ticker,
            display_date=display_date,
            current_close=current_close,
            volume_daily=volume_daily,
            volume_weekly=volume_weekly,
            volume_monthly=volume_monthly,
            ema_daily_5=ema_daily_5,
            ema_daily_20=ema_daily_20,
            ema_daily_40=ema_daily_40,
            macd_line_daily=macd_line_daily,
            macd_signal_daily=macd_signal_daily,
            macd_hist_daily=macd_hist_daily,
            bb_upper_daily=bb_upper_daily,
            bb_lower_daily=bb_lower_daily,
            bb_ma_daily=bb_ma_daily,
            ichimoku_conv_daily=ichimoku_conv_daily,
            ichimoku_base_daily=ichimoku_base_daily,
            ichimoku_spana_daily=ichimoku_spana_daily,
            ichimoku_spanb_daily=ichimoku_spanb_daily,
            ichimoku_lag_daily=ichimoku_lag_daily,
            ema_weekly_5=ema_weekly_5,
            ema_weekly_20=ema_weekly_20,
            ema_weekly_40=ema_weekly_40,
            macd_line_weekly=macd_line_weekly,
            macd_signal_weekly=macd_signal_weekly,
            macd_hist_weekly=macd_hist_weekly,
            bb_upper_weekly=bb_upper_weekly,
            bb_lower_weekly=bb_lower_weekly,
            bb_ma_weekly=bb_ma_weekly,
            ichimoku_conv_weekly=ichimoku_conv_weekly,
            ichimoku_base_weekly=ichimoku_base_weekly,
            ichimoku_spana_weekly=ichimoku_spana_weekly,
            ichimoku_spanb_weekly=ichimoku_spanb_weekly,
            ichimoku_lag_weekly=ichimoku_lag_weekly,
            ema_monthly_5=ema_monthly_5,
            ema_monthly_20=ema_monthly_20,
            ema_monthly_40=ema_monthly_40,
            macd_line_monthly=macd_line_monthly,
            macd_signal_monthly=macd_signal_monthly,
            macd_hist_monthly=macd_hist_monthly,
            bb_upper_monthly=bb_upper_monthly,
            bb_lower_monthly=bb_lower_monthly,
            bb_ma_monthly=bb_ma_monthly,
            ichimoku_conv_monthly=ichimoku_conv_monthly,
            ichimoku_base_monthly=ichimoku_base_monthly,
            ichimoku_spana_monthly=ichimoku_spana_monthly,
            ichimoku_spanb_monthly=ichimoku_spanb_monthly,
            ichimoku_lag_monthly=ichimoku_lag_monthly,
            daily_time_series=daily_time_series,
            weekly_time_series=weekly_time_series,
            monthly_time_series=monthly_time_series,
            daily_ohlcv_data=daily_ohlcv_data,
            weekly_ohlcv_data=weekly_ohlcv_data,
            monthly_ohlcv_data=monthly_ohlcv_data
        )

        # --- ALL INDICATORS DEBUG OUTPUT ---
        # 현재 날짜를 YYYYMMDD 형식으로 가져오기
        current_date_str = datetime.now().strftime("%Y%m%d")
        
        # EMA 디버그 파일
        ema_debug_lines = []
        ema_debug_lines.append(f"[EMA DEBUG] Ticker: {ticker}\n")
        ema_debug_lines.append("[Daily EMA for Chart]")
        for idx in daily_df.index:
            ema_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, EMA5: {daily_df.loc[idx, 'EMA5']:.2f}, EMA20: {daily_df.loc[idx, 'EMA20']:.2f}, EMA40: {daily_df.loc[idx, 'EMA40']:.2f}")
        ema_debug_lines.append("\n[Weekly EMA for Chart]")
        for idx in weekly_df.index:
            ema_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, EMA5: {weekly_df.loc[idx, 'EMA5']:.2f}, EMA20: {weekly_df.loc[idx, 'EMA20']:.2f}, EMA40: {weekly_df.loc[idx, 'EMA40']:.2f}")
        ema_debug_lines.append("\n[Monthly EMA for Chart]")
        for idx in monthly_df.index:
            ema_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, EMA5: {monthly_df.loc[idx, 'EMA5']:.2f}, EMA20: {monthly_df.loc[idx, 'EMA20']:.2f}, EMA40: {monthly_df.loc[idx, 'EMA40']:.2f}")
        ema_debug_lines.append("\n[EMA values sent to AI (actual .2f formatted values)]")
        ema_debug_lines.append(f"AI receives - Daily: EMA5: {ema_daily_5:.2f}, EMA20: {ema_daily_20:.2f}, EMA40: {ema_daily_40:.2f}")
        ema_debug_lines.append(f"AI receives - Weekly: EMA5: {ema_weekly_5:.2f}, EMA20: {ema_weekly_20:.2f}, EMA40: {ema_weekly_40:.2f}")
        ema_debug_lines.append(f"AI receives - Monthly: EMA5: {ema_monthly_5:.2f}, EMA20: {ema_monthly_20:.2f}, EMA40: {ema_monthly_40:.2f}")
        debug_folder = get_date_folder_path(DEBUG_DIR, current_date_str)
        ema_debug_path = os.path.join(debug_folder, f"{ticker}_ema_debug_{current_date_str}.txt")
        with open(ema_debug_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ema_debug_lines))

        # MACD 디버그 파일
        macd_debug_lines = []
        macd_debug_lines.append(f"[MACD DEBUG] Ticker: {ticker}\n")
        macd_debug_lines.append("[Daily MACD for Chart]")
        for idx in daily_df.index:
            macd_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, MACD: {daily_df.loc[idx, 'MACD_TA']:.2f}, Signal: {daily_df.loc[idx, 'MACD_Signal_TA']:.2f}, Hist: {daily_df.loc[idx, 'MACD_Hist_TA']:.2f}")
        macd_debug_lines.append("\n[Weekly MACD for Chart]")
        for idx in weekly_df.index:
            macd_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, MACD: {weekly_df.loc[idx, 'MACD_TA']:.2f}, Signal: {weekly_df.loc[idx, 'MACD_Signal_TA']:.2f}, Hist: {weekly_df.loc[idx, 'MACD_Hist_TA']:.2f}")
        macd_debug_lines.append("\n[Monthly MACD for Chart]")
        for idx in monthly_df.index:
            macd_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, MACD: {monthly_df.loc[idx, 'MACD_TA']:.2f}, Signal: {monthly_df.loc[idx, 'MACD_Signal_TA']:.2f}, Hist: {monthly_df.loc[idx, 'MACD_Hist_TA']:.2f}")
        macd_debug_lines.append("\n[MACD values sent to AI (actual .2f formatted values)]")
        macd_debug_lines.append(f"AI receives - Daily: MACD: {macd_line_daily:.2f}, Signal: {macd_signal_daily:.2f}, Hist: {macd_hist_daily:.2f}")
        macd_debug_lines.append(f"AI receives - Weekly: MACD: {macd_line_weekly:.2f}, Signal: {macd_signal_weekly:.2f}, Hist: {macd_hist_weekly:.2f}")
        macd_debug_lines.append(f"AI receives - Monthly: MACD: {macd_line_monthly:.2f}, Signal: {macd_signal_monthly:.2f}, Hist: {macd_hist_monthly:.2f}")
        macd_debug_path = os.path.join(debug_folder, f"{ticker}_macd_debug_{current_date_str}.txt")
        with open(macd_debug_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(macd_debug_lines))

        # 볼린저 밴드 디버그 파일
        bb_debug_lines = []
        bb_debug_lines.append(f"[Bollinger Bands DEBUG] Ticker: {ticker}\n")
        bb_debug_lines.append("[Daily Bollinger Bands for Chart]")
        for idx in daily_df.index:
            bb_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, BB_Upper: {daily_df.loc[idx, 'BB_Upper']:.2f}, BB_Lower: {daily_df.loc[idx, 'BB_Lower']:.2f}, BB_MA: {daily_df.loc[idx, 'BB_MA']:.2f}")
        bb_debug_lines.append("\n[Weekly Bollinger Bands for Chart]")
        for idx in weekly_df.index:
            bb_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, BB_Upper: {weekly_df.loc[idx, 'BB_Upper']:.2f}, BB_Lower: {weekly_df.loc[idx, 'BB_Lower']:.2f}, BB_MA: {weekly_df.loc[idx, 'BB_MA']:.2f}")
        bb_debug_lines.append("\n[Monthly Bollinger Bands for Chart]")
        for idx in monthly_df.index:
            bb_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, BB_Upper: {monthly_df.loc[idx, 'BB_Upper']:.2f}, BB_Lower: {monthly_df.loc[idx, 'BB_Lower']:.2f}, BB_MA: {monthly_df.loc[idx, 'BB_MA']:.2f}")
        bb_debug_lines.append("\n[Bollinger Bands values sent to AI (actual .2f formatted values)]")
        bb_debug_lines.append(f"AI receives - Daily: BB_Upper: {bb_upper_daily:.2f}, BB_Lower: {bb_lower_daily:.2f}, BB_MA: {bb_ma_daily:.2f}")
        bb_debug_lines.append(f"AI receives - Weekly: BB_Upper: {bb_upper_weekly:.2f}, BB_Lower: {bb_lower_weekly:.2f}, BB_MA: {bb_ma_weekly:.2f}")
        bb_debug_lines.append(f"AI receives - Monthly: BB_Upper: {bb_upper_monthly:.2f}, BB_Lower: {bb_lower_monthly:.2f}, BB_MA: {bb_ma_monthly:.2f}")
        bb_debug_path = os.path.join(debug_folder, f"{ticker}_bollinger_bands_debug_{current_date_str}.txt")
        with open(bb_debug_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(bb_debug_lines))

        # 일목균형표 디버그 파일
        ichimoku_debug_lines = []
        ichimoku_debug_lines.append(f"[Ichimoku DEBUG] Ticker: {ticker}\n")
        ichimoku_debug_lines.append("[Daily Ichimoku for Chart]")
        for idx in daily_df.index:
            ichimoku_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Ichimoku_Conversion: {daily_df.loc[idx, 'Ichimoku_Conversion']:.2f}, Ichimoku_Base: {daily_df.loc[idx, 'Ichimoku_Base']:.2f}, Ichimoku_SpanA: {daily_df.loc[idx, 'Ichimoku_SpanA']:.2f}, Ichimoku_SpanB: {daily_df.loc[idx, 'Ichimoku_SpanB']:.2f}, Ichimoku_Lagging: {daily_df.loc[idx, 'Ichimoku_Lagging']:.2f}")
        ichimoku_debug_lines.append("\n[Weekly Ichimoku for Chart]")
        for idx in weekly_df.index:
            ichimoku_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Ichimoku_Conversion: {weekly_df.loc[idx, 'Ichimoku_Conversion']:.2f}, Ichimoku_Base: {weekly_df.loc[idx, 'Ichimoku_Base']:.2f}, Ichimoku_SpanA: {weekly_df.loc[idx, 'Ichimoku_SpanA']:.2f}, Ichimoku_SpanB: {weekly_df.loc[idx, 'Ichimoku_SpanB']:.2f}, Ichimoku_Lagging: {weekly_df.loc[idx, 'Ichimoku_Lagging']:.2f}")
        ichimoku_debug_lines.append("\n[Monthly Ichimoku for Chart]")
        for idx in monthly_df.index:
            ichimoku_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Ichimoku_Conversion: {monthly_df.loc[idx, 'Ichimoku_Conversion']:.2f}, Ichimoku_Base: {monthly_df.loc[idx, 'Ichimoku_Base']:.2f}, Ichimoku_SpanA: {monthly_df.loc[idx, 'Ichimoku_SpanA']:.2f}, Ichimoku_SpanB: {monthly_df.loc[idx, 'Ichimoku_SpanB']:.2f}, Ichimoku_Lagging: {monthly_df.loc[idx, 'Ichimoku_Lagging']:.2f}")
        ichimoku_debug_lines.append("\n[Ichimoku values sent to AI (actual .2f formatted values)]")
        ichimoku_debug_lines.append(f"AI receives - Daily: Conv: {ichimoku_conv_daily:.2f}, Base: {ichimoku_base_daily:.2f}, SpanA: {ichimoku_spana_daily:.2f}, SpanB: {ichimoku_spanb_daily:.2f}, Lag: {ichimoku_lag_daily:.2f}")
        ichimoku_debug_lines.append(f"AI receives - Weekly: Conv: {ichimoku_conv_weekly:.2f}, Base: {ichimoku_base_weekly:.2f}, SpanA: {ichimoku_spana_weekly:.2f}, SpanB: {ichimoku_spanb_weekly:.2f}, Lag: {ichimoku_lag_weekly:.2f}")
        ichimoku_debug_lines.append(f"AI receives - Monthly: Conv: {ichimoku_conv_monthly:.2f}, Base: {ichimoku_base_monthly:.2f}, SpanA: {ichimoku_spana_monthly:.2f}, SpanB: {ichimoku_spanb_monthly:.2f}, Lag: {ichimoku_lag_monthly:.2f}")
        ichimoku_debug_path = os.path.join(debug_folder, f"{ticker}_ichimoku_debug_{current_date_str}.txt")
        with open(ichimoku_debug_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ichimoku_debug_lines))

        # 거래량 디버그 파일
        volume_debug_lines = []
        volume_debug_lines.append(f"[Volume DEBUG] Ticker: {ticker}\n")
        volume_debug_lines.append("[Daily Volume for Chart]")
        for idx in daily_df.index:
            volume_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Volume: {daily_df.loc[idx, 'Volume']:,.0f}")
        volume_debug_lines.append("\n[Weekly Volume for Chart]")
        for idx in weekly_df.index:
            volume_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Volume: {weekly_df.loc[idx, 'Volume']:,.0f}")
        volume_debug_lines.append("\n[Monthly Volume for Chart]")
        for idx in monthly_df.index:
            volume_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Volume: {monthly_df.loc[idx, 'Volume']:,.0f}")
        volume_debug_lines.append("\n[Volume values sent to AI (actual formatted values)]")
        volume_debug_lines.append(f"AI receives - Daily: Volume: {volume_daily:,.0f}")
        volume_debug_lines.append(f"AI receives - Weekly: Volume: {volume_weekly:,.0f}")
        volume_debug_lines.append(f"AI receives - Monthly: Volume: {volume_monthly:,.0f}")
        volume_debug_path = os.path.join(debug_folder, f"{ticker}_volume_debug_{current_date_str}.txt")
        with open(volume_debug_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(volume_debug_lines))

        # OHLCV 데이터 디버그 파일
        ohlcv_debug_lines = []
        ohlcv_debug_lines.append(f"[OHLCV DEBUG] Ticker: {ticker}\n")
        ohlcv_debug_lines.append("=" * 50)
        ohlcv_debug_lines.append("일봉 OHLCV 데이터 (최근 30개):")
        ohlcv_debug_lines.append("=" * 50)
        ohlcv_debug_lines.append(daily_ohlcv_data)
        ohlcv_debug_lines.append("\n" + "=" * 50)
        ohlcv_debug_lines.append("주봉 OHLCV 데이터 (최근 30개):")
        ohlcv_debug_lines.append("=" * 50)
        ohlcv_debug_lines.append(weekly_ohlcv_data)
        ohlcv_debug_lines.append("\n" + "=" * 50)
        ohlcv_debug_lines.append("월봉 OHLCV 데이터 (최근 30개):")
        ohlcv_debug_lines.append("=" * 50)
        ohlcv_debug_lines.append(monthly_ohlcv_data)
        ohlcv_debug_lines.append("\n" + "=" * 50)
        ohlcv_debug_lines.append(f"총 데이터 크기: 일봉 {len(daily_ohlcv_data_points)}개, 주봉 {len(weekly_ohlcv_data_points)}개, 월봉 {len(monthly_ohlcv_data_points)}개")
        
        ohlcv_debug_path = os.path.join(debug_folder, f"{ticker}_ohlcv_debug_{current_date_str}.txt")
        with open(ohlcv_debug_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ohlcv_debug_lines))

        # AI 프롬프트 전체 내용 디버그 파일 저장
        prompt_debug_lines = []
        prompt_debug_lines.append(f"[AI PROMPT DEBUG] Ticker: {ticker}")
        prompt_debug_lines.append(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        prompt_debug_lines.append("=" * 80)
        prompt_debug_lines.append("")
        prompt_debug_lines.append(common_prompt)
        prompt_debug_lines.append("")
        prompt_debug_lines.append("=" * 80)
        prompt_debug_lines.append(f"Total prompt length: {len(common_prompt)} characters")
        
        prompt_debug_path = os.path.join(debug_folder, f"{ticker}_ai_prompt_debug_{current_date_str}.txt")
        with open(prompt_debug_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(prompt_debug_lines))

    except Exception as e:
        # 데이터 로드 또는 지표 계산 실패 시, AI 분석을 시도하지 않음
        logging.error(f"Failed to prepare data for AI analysis for {ticker}: {e}")
        return {
            "analysis_gemini": f"[데이터 준비 실패: {e}]",
            "analysis_openai": f"[데이터 준비 실패: {e}]",
            "summary_gemini": "데이터 준비 실패",
            "summary_openai": "데이터 준비 실패",
            "success": False
        }, 500

    analysis_gemini = "[Gemini 분석 실패: 분석을 시작할 수 없습니다.]"
    analysis_openai = "[OpenAI 분석 비활성화됨]"
    summary_gemini = "요약 없음."
    summary_openai = "요약 없음."
    
    gemini_succeeded = False
    openai_succeeded = False

    # AI 분석 수행 (Gemini만 사용)
    logging.info(f"[{ticker}] Starting Gemini AI analysis...")
    analysis_gemini, gemini_succeeded_status = perform_gemini_analysis(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64)
    logging.info(f"[{ticker}] Gemini AI analysis completed. Success: {gemini_succeeded_status}")

    gemini_succeeded = gemini_succeeded_status

    if gemini_succeeded:
        logging.info(f"[{ticker}] Extracting summary from Gemini analysis...")
        summary_gemini = _extract_summary_from_analysis(analysis_gemini)
        logging.info(f"[{ticker}] Summary extracted successfully")

    # 원래 경로(static/analysis)에 직접 저장 + 권한 문제 해결
    logging.info(f"[{ticker}] Saving analysis to original static directory...")
    try:
        import tempfile
        import shutil
        import subprocess
        
        # 1. 분석 텍스트를 원래 경로에 저장
        if gemini_succeeded:
            # 임시 파일에 분석 텍스트 작성
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_text:
                temp_text.write(analysis_gemini)
                temp_text_path = temp_text.name
            
            analysis_text_path = os.path.join(analysis_folder, f"{ticker}_analysis_{current_date_str}.txt")
            
            # analysis 디렉토리 생성 및 권한 확보
            try:
                os.makedirs(analysis_folder, exist_ok=True)
            except PermissionError:
                try:
                    subprocess.run(['sudo', 'mkdir', '-p', analysis_folder], check=True, capture_output=True)
                    subprocess.run(['sudo', 'chown', 'ubuntu:ubuntu', analysis_folder], check=True, capture_output=True)
                    subprocess.run(['sudo', 'chmod', '755', analysis_folder], check=True, capture_output=True)
                    logging.info(f"sudo로 분석 디렉토리 생성: {analysis_folder}")
                except Exception as sudo_error:
                    logging.error(f"sudo 분석 디렉토리 생성 실패: {sudo_error}")
                    raise
            
            # 임시 파일을 최종 경로로 이동
            try:
                shutil.move(temp_text_path, analysis_text_path)
                os.chmod(analysis_text_path, 0o644)
                logging.info(f"[{ticker}] Analysis text saved to original path: {analysis_text_path}")
            except PermissionError:
                try:
                    subprocess.run(['sudo', 'cp', temp_text_path, analysis_text_path], check=True, capture_output=True)
                    subprocess.run(['sudo', 'chown', 'ubuntu:ubuntu', analysis_text_path], check=True, capture_output=True)
                    subprocess.run(['sudo', 'chmod', '644', analysis_text_path], check=True, capture_output=True)
                    os.unlink(temp_text_path)
                    logging.info(f"[{ticker}] Analysis text saved with sudo: {analysis_text_path}")
                except Exception as sudo_error:
                    logging.error(f"sudo 분석 텍스트 저장 실패: {sudo_error}")
                    raise
        
        # 2. HTML 파일을 원래 경로에 저장
        # 임시 파일에 HTML 생성
        if current_app:
            rendered_html = render_template("charts.html", ticker=ticker, charts=charts, date=display_date, analysis_gemini=analysis_gemini)
        else:
            from app import app
            with app.app_context():
                rendered_html = render_template("charts.html", ticker=ticker, charts=charts, date=display_date, analysis_gemini=analysis_gemini)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
            temp_html.write(rendered_html)
            temp_html_path = temp_html.name
        
        # 임시 HTML 파일을 최종 경로로 이동
        try:
            shutil.move(temp_html_path, analysis_html_path)
            os.chmod(analysis_html_path, 0o644)
            logging.info(f"[{ticker}] HTML file saved to original path: {analysis_html_path}")
        except PermissionError:
            try:
                subprocess.run(['sudo', 'cp', temp_html_path, analysis_html_path], check=True, capture_output=True)
                subprocess.run(['sudo', 'chown', 'ubuntu:ubuntu', analysis_html_path], check=True, capture_output=True)
                subprocess.run(['sudo', 'chmod', '644', analysis_html_path], check=True, capture_output=True)
                os.unlink(temp_html_path)
                logging.info(f"[{ticker}] HTML file saved with sudo: {analysis_html_path}")
            except Exception as sudo_error:
                logging.error(f"sudo HTML 파일 저장 실패: {sudo_error}")
                raise
                
    except Exception as e:
        logging.error(f"[{ticker}] Failed to save analysis files: {e}")
        # 저장 실패해도 계속 진행
    
    # JSON 응답 반환
    logging.info(f"[{ticker}] AI analysis process completed successfully")
    return {
        "analysis_gemini": analysis_gemini,
        "analysis_openai": analysis_openai,
        "summary_gemini": summary_gemini,
        "summary_openai": summary_openai,
        "success": gemini_succeeded
    }, 200

def perform_gemini_analysis(ticker, common_prompt, daily_b64, weekly_b64, monthly_b64):
    """Gemini API를 사용한 분석을 수행합니다."""
    analysis = "[Gemini 분석 실패: 분석을 시작할 수 없습니다.]"
    succeeded = False
    try:
        gemini_api_key = GOOGLE_API_KEY
        if not gemini_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set for Gemini API.")
        
        model = genai.GenerativeModel(GEMINI_MODEL_VERSION)
        
        # 이미지가 있는 경우와 없는 경우를 구분
        if daily_b64 and weekly_b64 and monthly_b64:
            # 기존 방식: 이미지와 텍스트 함께 전달
            gemini_inputs = [
                {"text": common_prompt + "\n\n이 분석의 핵심 내용을 세 줄로 요약해 주십시오."},
                {"inline_data": {"mime_type": "image/png", "data": daily_b64}},
                {"inline_data": {"mime_type": "image/png", "data": weekly_b64}},
                {"inline_data": {"mime_type": "image/png", "data": monthly_b64}}
            ]
        else:
            # 새로운 방식: 텍스트만 전달 (히스토리컬 데이터 포함)
            gemini_inputs = [
                {"text": common_prompt + "\n\n이 분석의 핵심 내용을 세 줄로 요약해 주십시오."}
            ]
        
        logging.debug(f"Gemini API request payload (first part of text): {common_prompt[:200]}...")
        
        # Gemini API 호출 (자체 타임아웃 적용)
        import time
        start_time = time.time()
        response = model.generate_content(gemini_inputs)
        api_time = time.time() - start_time
        logging.info(f"[{ticker}] Gemini API call completed in {api_time:.2f} seconds")
        
        analysis = response.text
        logging.info(f"Gemini raw response text length: {len(response.text)}")
        logging.debug(f"Gemini analysis raw response: {response.text[:500]}...")
        succeeded = True
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

def analyze_ticker_force_new(ticker):
    """
    기존 파일을 무시하고 강제로 새로운 분석을 생성합니다.
    """
    ticker = ticker.upper()
    
    today_date_str = datetime.today().strftime("%Y%m%d")
    html_file_name = f"{ticker}_{today_date_str}.html"
    analysis_html_path = os.path.join(ANALYSIS_DIR, html_file_name)

    # 기존 파일이 있으면 삭제
    if os.path.exists(analysis_html_path):
        try:
            os.remove(analysis_html_path)
            logging.info(f"기존 분석 파일 삭제: {analysis_html_path}")
        except Exception as e:
            logging.error(f"기존 파일 삭제 실패: {e}")

    # 기존 analyze_ticker_internal 함수의 나머지 로직을 그대로 실행
    return analyze_ticker_internal_logic(ticker, analysis_html_path)

def start_bulk_analysis_task(user_id, list_ids):
    """
    Celery를 사용하여 특정 사용자의 여러 리스트에 대한 일괄 분석을 시작합니다.
    
    :param user_id: 대상 사용자의 ID
    :param list_ids: 분석할 종목 리스트 ID의 리스트
    :return: Celery 태스크 객체
    """
    try:
        logger.info(f"사용자 ID {user_id}의 리스트 {list_ids}에 대한 일괄 분석 작업을 요청합니다.")
        # Celery 태스크를 비동기적으로 호출
        task = run_bulk_analysis_for_user.delay(user_id, list_ids)
        return task
    except Exception as e:
        logger.error(f"일괄 분석 태스크 시작 중 예외 발생: {e}", exc_info=True)
        # 예외를 다시 발생시켜 호출한 쪽에서 처리하도록 함
        raise