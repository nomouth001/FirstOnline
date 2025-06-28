import yfinance as yf
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import ta
from ta.trend import EMAIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
from ta.trend import IchimokuIndicator

def safe_last_value(series):
    """시리즈의 마지막 값을 안전하게 반환합니다."""
    return series.iloc[-1] if not series.empty and not series.isnull().all() else float('nan')

def get_key_data_points(df, num_points=30):
    """주요 데이터 포인트 추출 (최신값 + 과거 주요 지점들)"""
    if df.empty:
        return []
    
    # 최신 데이터
    latest_data = {
        'date': df.index[-1].strftime('%Y-%m-%d'),
        'close': df['Close'].iloc[-1],
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

def calculate_technical_indicators(df):
    """기술적 지표를 계산합니다."""
    # EMA 계산
    df['EMA5'] = ta.trend.ema_indicator(df['Close'], window=5)
    df['EMA20'] = ta.trend.ema_indicator(df['Close'], window=20)
    df['EMA40'] = ta.trend.ema_indicator(df['Close'], window=40)
    
    # MACD 계산
    df['MACD_TA'] = ta.trend.macd(df['Close'])
    df['MACD_Signal_TA'] = ta.trend.macd_signal(df['Close'])
    df['MACD_Hist_TA'] = ta.trend.macd_diff(df['Close'])

    # 볼린저 밴드 계산
    bollinger = BollingerBands(close=df["Close"], window=20, window_dev=2)
    df["BB_Upper"] = bollinger.bollinger_hband()
    df["BB_Lower"] = bollinger.bollinger_lband()
    df["BB_MA"] = bollinger.bollinger_mavg()

    # 일목균형표 계산
    ichimoku = IchimokuIndicator(high=df["High"], low=df["Low"])
    df["Ichimoku_Conversion"] = ichimoku.ichimoku_conversion_line()
    df["Ichimoku_Base"] = ichimoku.ichimoku_base_line()
    df["Ichimoku_SpanA"] = ichimoku.ichimoku_a()
    df["Ichimoku_SpanB"] = ichimoku.ichimoku_b()
    # 지연스팬은 종가를 26일 뒤로 이동한 값
    df["Ichimoku_Lagging"] = df["Close"].shift(-26)
    
    return df

def prepare_stock_data(ticker, display_date):
    """주식 데이터를 준비하고 기술적 지표를 계산합니다."""
    try:
        data_end_date = datetime.strptime(display_date, "%Y-%m-%d")
        data_fetch_start_date = data_end_date - timedelta(days=5*365 + 60)

        stock_data_full = yf.Ticker(ticker).history(start=data_fetch_start_date, end=data_end_date + timedelta(days=1), auto_adjust=False)
        
        if stock_data_full.empty:
             raise ValueError(f"No stock data found for {ticker} for indicator calculation up to {data_end_date.strftime('%Y-%m-%d')}.")

        if stock_data_full.index.tz is not None:
            stock_data_full.index = stock_data_full.index.tz_localize(None)

        stock_data = stock_data_full[stock_data_full.index <= data_end_date]
        if stock_data.empty:
             raise ValueError(f"Filtered stock data up to {data_end_date.strftime('%Y-%m-%d')} is empty.")

        # 일봉 데이터 준비
        daily_start_limit = data_end_date - timedelta(days=90)
        daily_df = stock_data[stock_data.index >= daily_start_limit].copy()
        
        if daily_df.empty or len(daily_df) < 40:
             raise ValueError(f"Insufficient daily data ({len(daily_df)} points) for indicators up to {data_end_date.strftime('%Y-%m-%d')}.")

        daily_df = calculate_technical_indicators(daily_df)
        daily_df.dropna(subset=['EMA40', 'MACD_Hist_TA', 'BB_Upper', 'BB_Lower', 'BB_MA'], inplace=True)
        if daily_df.empty:
            raise ValueError("Daily DataFrame became empty after indicator calculation and NaN drop.")

        # 주봉 데이터 준비
        weekly_df_resampled = stock_data.resample('W').agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna().copy()
        weekly_start_limit = data_end_date - timedelta(weeks=52*2 + 4)
        weekly_df = weekly_df_resampled[weekly_df_resampled.index >= weekly_start_limit].copy()
        
        if weekly_df.empty or len(weekly_df) < 40:
            raise ValueError(f"Insufficient weekly data ({len(weekly_df)} points) for indicators up to {data_end_date.strftime('%Y-%m-%d')}.")

        weekly_df = calculate_technical_indicators(weekly_df)
        weekly_df.dropna(subset=['EMA40', 'MACD_Hist_TA', 'BB_Upper', 'BB_Lower', 'BB_MA'], inplace=True)
        if weekly_df.empty:
            raise ValueError("Weekly DataFrame became empty after indicator calculation and NaN drop.")

        # 월봉 데이터 준비
        monthly_df_resampled = stock_data.resample('M').agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna().copy()
        monthly_start_limit = data_end_date - timedelta(weeks=52*5 + 8)
        monthly_df = monthly_df_resampled[monthly_df_resampled.index >= monthly_start_limit].copy()
        
        if monthly_df.empty or len(monthly_df) < 40:
            raise ValueError(f"Insufficient monthly data ({len(monthly_df)} points) for indicators up to {data_end_date.strftime('%Y-%m-%d')}.")

        monthly_df = calculate_technical_indicators(monthly_df)
        monthly_df.dropna(subset=['EMA40', 'MACD_Hist_TA', 'BB_Upper', 'BB_Lower', 'BB_MA'], inplace=True)
        if monthly_df.empty:
            raise ValueError("Monthly DataFrame became empty after indicator calculation and NaN drop.")

        return {
            'daily_df': daily_df,
            'weekly_df': weekly_df,
            'monthly_df': monthly_df,
            'stock_data': stock_data
        }

    except Exception as e:
        logging.error(f"Failed to prepare stock data for {ticker}: {e}")
        raise 