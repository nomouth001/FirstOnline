import os
import logging
from datetime import datetime
from config import DEBUG_DIR
from utils.file_manager import get_date_folder_path, safe_write_file

def create_debug_files(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points):
    """모든 지표에 대한 디버그 파일을 생성합니다."""
    try:
        current_date_str = datetime.now().strftime("%Y%m%d")
        
        # EMA 디버그 파일
        create_ema_debug_file(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points, current_date_str)
        
        # MACD 디버그 파일
        create_macd_debug_file(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points, current_date_str)
        
        # 볼린저 밴드 디버그 파일
        create_bollinger_debug_file(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points, current_date_str)
        
        # 일목균형표 디버그 파일
        create_ichimoku_debug_file(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points, current_date_str)
        
        logging.info(f"Debug files created successfully for {ticker}")
        
    except Exception as e:
        logging.error(f"Failed to create debug files for {ticker}: {e}")

def create_ema_debug_file(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points, current_date_str):
    """EMA 디버그 파일을 생성합니다."""
    ema_debug_lines = []
    ema_debug_lines.append(f"[EMA DEBUG] Ticker: {ticker}\n")
    ema_debug_lines.append("[Daily EMA for Chart]")
    for idx in daily_df.index:
        ema_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, EMA5: {daily_df.loc[idx, 'EMA5']:.4f}, EMA20: {daily_df.loc[idx, 'EMA20']:.4f}, EMA40: {daily_df.loc[idx, 'EMA40']:.4f}")
    ema_debug_lines.append("\n[Weekly EMA for Chart]")
    for idx in weekly_df.index:
        ema_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, EMA5: {weekly_df.loc[idx, 'EMA5']:.4f}, EMA20: {weekly_df.loc[idx, 'EMA20']:.4f}, EMA40: {weekly_df.loc[idx, 'EMA40']:.4f}")
    ema_debug_lines.append("\n[Monthly EMA for Chart]")
    for idx in monthly_df.index:
        ema_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, EMA5: {monthly_df.loc[idx, 'EMA5']:.4f}, EMA20: {monthly_df.loc[idx, 'EMA20']:.4f}, EMA40: {monthly_df.loc[idx, 'EMA40']:.4f}")
    ema_debug_lines.append("\n[EMA values sent to AI (from get_key_data_points)]")
    for tf, points in zip(['Daily', 'Weekly', 'Monthly'], [daily_data_points, weekly_data_points, monthly_data_points]):
        ema_debug_lines.append(f"\n[{tf}]")
        for p in points:
            ema_debug_lines.append(f"{p['date']}, EMA5: {p['ema5']}, EMA20: {p['ema20']}, EMA40: {p['ema40']}")
    
    # 날짜별 폴더 경로 사용
    debug_folder = get_date_folder_path(DEBUG_DIR, current_date_str)
    ema_debug_path = os.path.join(debug_folder, f"{ticker}_ema_debug_{current_date_str}.txt")
    safe_write_file(ema_debug_path, '\n'.join(ema_debug_lines))

def create_macd_debug_file(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points, current_date_str):
    """MACD 디버그 파일을 생성합니다."""
    macd_debug_lines = []
    macd_debug_lines.append(f"[MACD DEBUG] Ticker: {ticker}\n")
    macd_debug_lines.append("[Daily MACD for Chart]")
    for idx in daily_df.index:
        macd_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, MACD: {daily_df.loc[idx, 'MACD_TA']:.4f}, Signal: {daily_df.loc[idx, 'MACD_Signal_TA']:.4f}, Hist: {daily_df.loc[idx, 'MACD_Hist_TA']:.4f}")
    macd_debug_lines.append("\n[Weekly MACD for Chart]")
    for idx in weekly_df.index:
        macd_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, MACD: {weekly_df.loc[idx, 'MACD_TA']:.4f}, Signal: {weekly_df.loc[idx, 'MACD_Signal_TA']:.4f}, Hist: {weekly_df.loc[idx, 'MACD_Hist_TA']:.4f}")
    macd_debug_lines.append("\n[Monthly MACD for Chart]")
    for idx in monthly_df.index:
        macd_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, MACD: {monthly_df.loc[idx, 'MACD_TA']:.4f}, Signal: {monthly_df.loc[idx, 'MACD_Signal_TA']:.4f}, Hist: {monthly_df.loc[idx, 'MACD_Hist_TA']:.4f}")
    macd_debug_lines.append("\n[MACD values sent to AI (from get_key_data_points)]")
    for tf, points in zip(['Daily', 'Weekly', 'Monthly'], [daily_data_points, weekly_data_points, monthly_data_points]):
        macd_debug_lines.append(f"\n[{tf}]")
        for p in points:
            macd_debug_lines.append(f"{p['date']}, MACD: {p['macd']}, Signal: {p['macd_signal']}, Hist: {p['macd_hist']}")
    
    # 날짜별 폴더 경로 사용
    debug_folder = get_date_folder_path(DEBUG_DIR, current_date_str)
    macd_debug_path = os.path.join(debug_folder, f"{ticker}_macd_debug_{current_date_str}.txt")
    safe_write_file(macd_debug_path, '\n'.join(macd_debug_lines))

def create_bollinger_debug_file(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points, current_date_str):
    """볼린저 밴드 디버그 파일을 생성합니다."""
    bb_debug_lines = []
    bb_debug_lines.append(f"[Bollinger Bands DEBUG] Ticker: {ticker}\n")
    bb_debug_lines.append("[Daily Bollinger Bands for Chart]")
    for idx in daily_df.index:
        bb_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, BB_Upper: {daily_df.loc[idx, 'BB_Upper']:.4f}, BB_Lower: {daily_df.loc[idx, 'BB_Lower']:.4f}, BB_MA: {daily_df.loc[idx, 'BB_MA']:.4f}")
    bb_debug_lines.append("\n[Weekly Bollinger Bands for Chart]")
    for idx in weekly_df.index:
        bb_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, BB_Upper: {weekly_df.loc[idx, 'BB_Upper']:.4f}, BB_Lower: {weekly_df.loc[idx, 'BB_Lower']:.4f}, BB_MA: {weekly_df.loc[idx, 'BB_MA']:.4f}")
    bb_debug_lines.append("\n[Monthly Bollinger Bands for Chart]")
    for idx in monthly_df.index:
        bb_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, BB_Upper: {monthly_df.loc[idx, 'BB_Upper']:.4f}, BB_Lower: {monthly_df.loc[idx, 'BB_Lower']:.4f}, BB_MA: {monthly_df.loc[idx, 'BB_MA']:.4f}")
    bb_debug_lines.append("\n[Bollinger Bands values sent to AI (from get_key_data_points)]")
    for tf, points in zip(['Daily', 'Weekly', 'Monthly'], [daily_data_points, weekly_data_points, monthly_data_points]):
        bb_debug_lines.append(f"\n[{tf}]")
        for p in points:
            bb_debug_lines.append(f"{p['date']}, BB_Upper: {p['bb_upper']}, BB_Lower: {p['bb_lower']}, BB_MA: {p['bb_ma']}")
    
    # 날짜별 폴더 경로 사용
    debug_folder = get_date_folder_path(DEBUG_DIR, current_date_str)
    bb_debug_path = os.path.join(debug_folder, f"{ticker}_bollinger_bands_debug_{current_date_str}.txt")
    safe_write_file(bb_debug_path, '\n'.join(bb_debug_lines))

def create_ichimoku_debug_file(ticker, daily_df, weekly_df, monthly_df, daily_data_points, weekly_data_points, monthly_data_points, current_date_str):
    """일목균형표 디버그 파일을 생성합니다."""
    ichimoku_debug_lines = []
    ichimoku_debug_lines.append(f"[Ichimoku DEBUG] Ticker: {ticker}\n")
    ichimoku_debug_lines.append("[Daily Ichimoku for Chart]")
    for idx in daily_df.index:
        ichimoku_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Ichimoku_Conversion: {daily_df.loc[idx, 'Ichimoku_Conversion']:.4f}, Ichimoku_Base: {daily_df.loc[idx, 'Ichimoku_Base']:.4f}, Ichimoku_SpanA: {daily_df.loc[idx, 'Ichimoku_SpanA']:.4f}, Ichimoku_SpanB: {daily_df.loc[idx, 'Ichimoku_SpanB']:.4f}, Ichimoku_Lagging: {daily_df.loc[idx, 'Ichimoku_Lagging']:.4f}")
    ichimoku_debug_lines.append("\n[Weekly Ichimoku for Chart]")
    for idx in weekly_df.index:
        ichimoku_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Ichimoku_Conversion: {weekly_df.loc[idx, 'Ichimoku_Conversion']:.4f}, Ichimoku_Base: {weekly_df.loc[idx, 'Ichimoku_Base']:.4f}, Ichimoku_SpanA: {weekly_df.loc[idx, 'Ichimoku_SpanA']:.4f}, Ichimoku_SpanB: {weekly_df.loc[idx, 'Ichimoku_SpanB']:.4f}, Ichimoku_Lagging: {weekly_df.loc[idx, 'Ichimoku_Lagging']:.4f}")
    ichimoku_debug_lines.append("\n[Monthly Ichimoku for Chart]")
    for idx in monthly_df.index:
        ichimoku_debug_lines.append(f"{idx.strftime('%Y-%m-%d')}, Ichimoku_Conversion: {monthly_df.loc[idx, 'Ichimoku_Conversion']:.4f}, Ichimoku_Base: {monthly_df.loc[idx, 'Ichimoku_Base']:.4f}, Ichimoku_SpanA: {monthly_df.loc[idx, 'Ichimoku_SpanA']:.4f}, Ichimoku_SpanB: {monthly_df.loc[idx, 'Ichimoku_SpanB']:.4f}, Ichimoku_Lagging: {monthly_df.loc[idx, 'Ichimoku_Lagging']:.4f}")
    ichimoku_debug_lines.append("\n[Ichimoku values sent to AI (from get_key_data_points)]")
    for tf, points in zip(['Daily', 'Weekly', 'Monthly'], [daily_data_points, weekly_data_points, monthly_data_points]):
        ichimoku_debug_lines.append(f"\n[{tf}]")
        for p in points:
            ichimoku_debug_lines.append(f"{p['date']}, Ichimoku_Conv: {p['ichimoku_conv']}, Ichimoku_Base: {p['ichimoku_base']}, Ichimoku_SpanA: {p['ichimoku_spana']}, Ichimoku_SpanB: {p['ichimoku_spanb']}, Ichimoku_Lag: {p['ichimoku_lag']}")
    
    # 날짜별 폴더 경로 사용
    debug_folder = get_date_folder_path(DEBUG_DIR, current_date_str)
    ichimoku_debug_path = os.path.join(debug_folder, f"{ticker}_ichimoku_debug_{current_date_str}.txt")
    safe_write_file(ichimoku_debug_path, '\n'.join(ichimoku_debug_lines)) 