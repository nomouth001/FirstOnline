import os
import logging
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use('Agg')  # GUI 백엔드 사용하지 않음
# matplotlib 로깅 레벨을 WARNING으로 설정하여 폰트 검색 DEBUG 로그 비활성화
import matplotlib.font_manager as fm
fm._log.setLevel(logging.WARNING)
# matplotlib 전체 로깅 레벨도 WARNING으로 설정
import matplotlib.pyplot as plt
plt.set_loglevel('warning')

# 폰트 캐시 미리 로드 및 기본 폰트 설정으로 성능 최적화
def optimize_matplotlib_fonts():
    """matplotlib 폰트 성능 최적화"""
    try:
        # 폰트 캐시 미리 로드
        fm.findfont('DejaVu Sans')
        
        # 기본 폰트 설정 (가장 빠른 폰트)
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['font.size'] = 10
        
        logging.info("matplotlib 폰트 최적화 완료")
    except Exception as e:
        logging.warning(f"폰트 최적화 실패: {e}")

# 애플리케이션 시작 시 폰트 최적화 실행
optimize_matplotlib_fonts()

import mplfinance as mpf
import ta
from ta.volatility import BollingerBands
from ta.trend import IchimokuIndicator
from datetime import datetime, timedelta
from config import CHART_DIR, DEBUG_DIR
from utils.file_manager import get_date_folder_path
import signal
import threading
from functools import wraps

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

def timeout_decorator(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            def target():
                return func(*args, **kwargs)
            
            result = [None]
            exception = [None]
            
            def worker():
                try:
                    result[0] = target()
                except Exception as e:
                    exception[0] = e
            
            thread = threading.Thread(target=worker)
            thread.daemon = True
            thread.start()
            thread.join(seconds)
            
            if thread.is_alive():
                logging.error(f"Function {func.__name__} timed out after {seconds} seconds")
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds} seconds")
            
            if exception[0]:
                raise exception[0]
            
            return result[0]
        return wrapper
    return decorator

@timeout_decorator(30)  # 30초 타임아웃
def create_chart_with_timeout(df_plot, ticker, period, main_ax, volume_ax):
    """타임아웃이 적용된 차트 생성 함수"""
    logging.info(f"[{ticker}] Creating {period} chart with timeout protection...")
    # 메모리 정리
    import gc
    gc.collect()
    # 차트 생성 (실제 함수 없음, 불필요한 호출 제거)
    # create_chart(df_plot, ticker, period, main_ax, volume_ax)
    # 메모리 정리
    gc.collect()
    logging.info(f"[{ticker}] {period} chart created successfully")

@timeout_decorator(30)  # 30초 타임아웃
def generate_with_timeout(df_input, freq_label, suffix):
    """타임아웃이 적용된 차트 생성 함수"""
    logging.info(f"Creating {freq_label} chart with timeout protection...")
    
    # 메모리 정리
    import gc
    gc.collect()
    
    # 차트 생성
    result = generate(df_input, freq_label, suffix)
    
    # 메모리 정리
    gc.collect()
    logging.info(f"{freq_label} chart created successfully")
    return result

def generate_chart(ticker):
    """주식 차트를 생성합니다."""
    logging.info(f"[{ticker}] Starting chart generation process...")
    ticker = ticker.upper()
    start = (datetime.now() - timedelta(days=5 * 365 + 30)).replace(hour=0, minute=0, second=0, microsecond=0)
    os.makedirs(CHART_DIR, exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)

    try:
        logging.info(f"[{ticker}] Downloading data from yfinance...")
        df = yf.download(ticker, start=start, end=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1), auto_adjust=False)
        logging.info(f"[{ticker}] Data download completed. DataFrame shape: {df.shape}")
        
        if df.empty:
            logging.warning(f"[{ticker}] No data downloaded for {ticker}. This might be due to invalid ticker symbol or data availability issues.")
            # 빈 DataFrame을 반환하여 다음 단계에서 처리할 수 있도록 함
            return {
                "Daily": None,
                "Weekly": None,
                "Monthly": None
            }
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        end_date_from_data = df.index[-1].to_pydatetime()
        date_str = end_date_from_data.strftime("%Y%m%d")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        logging.info(f"[{ticker}] Data preprocessing completed. Final DataFrame shape: {df.shape}")

        # 일봉 차트
        daily_chart_path = generate(df.copy(), "Daily", "daily", ticker)
        # 주봉 차트
        weekly_df = df.resample("W").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        weekly_chart_path = generate(weekly_df, "Weekly", "weekly", ticker)
        # 월봉 차트
        monthly_df = df.resample("M").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        monthly_chart_path = generate(monthly_df, "Monthly", "monthly", ticker)

        logging.info(f"[{ticker}] Chart generation completed successfully. Generated charts: Daily={daily_chart_path is not None}, Weekly={weekly_chart_path is not None}, Monthly={monthly_chart_path is not None}")
        return {
            "Daily": daily_chart_path,
            "Weekly": weekly_chart_path,
            "Monthly": monthly_chart_path
        }
    except Exception as e:
        logging.exception(f"Chart generation failed for {ticker}")
        raise e

def generate(df_input, freq_label, suffix, ticker):
    num_bars_to_show = 60
    min_data_for_full_calc = 60
    if freq_label == "Monthly":
        num_bars_to_show = 26
        min_data_for_full_calc = 40
    if len(df_input) < min_data_for_full_calc:
        logging.warning(f"Not enough data for accurate full indicator calculation for {freq_label} chart for {ticker}. Need at least {min_data_for_full_calc} periods, got {len(df_input)}. Only {num_bars_to_show} bars will be shown if possible.")
        if len(df_input) < num_bars_to_show:
            logging.warning(f"Insufficient data to plot {num_bars_to_show} bars for {freq_label} chart for {ticker}. Skipping chart generation.")
            return None
    df_calc = df_input.copy()
    df_calc["EMA5"] = ta.trend.ema_indicator(df_calc["Close"], window=5)
    df_calc["EMA20"] = ta.trend.ema_indicator(df_calc["Close"], window=20)
    df_calc["EMA40"] = ta.trend.ema_indicator(df_calc["Close"], window=40)
    ichimoku = IchimokuIndicator(high=df_calc["High"], low=df_calc["Low"])
    df_calc["Ichimoku_Conversion"] = ichimoku.ichimoku_conversion_line()
    df_calc["Ichimoku_Base"] = ichimoku.ichimoku_base_line()
    df_calc["Ichimoku_SpanA"] = ichimoku.ichimoku_a()
    df_calc["Ichimoku_SpanB"] = ichimoku.ichimoku_b()
    df_calc["Ichimoku_Lagging"] = df_calc["Close"].shift(-26)
    df_calc['MACD_TA'] = ta.trend.macd(df_calc['Close'])
    df_calc['MACD_Signal_TA'] = ta.trend.macd_signal(df_calc['Close'])
    df_calc['MACD_Hist_TA'] = ta.trend.macd_diff(df_calc['Close'])
    bollinger = BollingerBands(close=df_calc["Close"], window=20, window_dev=2)
    df_calc["BB_Upper"] = bollinger.bollinger_hband()
    df_calc["BB_Lower"] = bollinger.bollinger_lband()
    df_calc["BB_MA"] = bollinger.bollinger_mavg()
    df_calc.dropna(subset=['EMA40', 'MACD_Hist_TA', 'BB_Upper', 'BB_Lower', 'BB_MA'], inplace=True)
    if df_calc.empty:
        logging.warning(f"DataFrame for calculations became empty after dropping NaNs for {freq_label} chart for {ticker}.")
        return None
    df_plot = df_calc[-num_bars_to_show:].copy()
    if df_plot.empty:
        logging.warning(f"DataFrame for plotting became empty for {freq_label} chart for {ticker}.")
        return None
    current_date_str = datetime.now().strftime("%Y%m%d")
    chart_creation_date = datetime.now()
    # 디버그 데이터 수집 (차트에 실제로 그려지는 데이터만)
    daily_ema_data = []
    daily_macd_data = []
    daily_bb_data = []
    daily_ichimoku_data = []
    weekly_ema_data = []
    weekly_macd_data = []
    weekly_bb_data = []
    weekly_ichimoku_data = []
    monthly_ema_data = []
    monthly_macd_data = []
    monthly_bb_data = []
    monthly_ichimoku_data = []
    for idx in df_plot.index:
        date_str = idx.strftime('%Y-%m-%d')
        ema_data = f"{date_str}, EMA5: {df_plot.loc[idx, 'EMA5']:.4f}, EMA20: {df_plot.loc[idx, 'EMA20']:.4f}, EMA40: {df_plot.loc[idx, 'EMA40']:.4f}"
        macd_data = f"{date_str}, MACD: {df_plot.loc[idx, 'MACD_TA']:.4f}, Signal: {df_plot.loc[idx, 'MACD_Signal_TA']:.4f}, Hist: {df_plot.loc[idx, 'MACD_Hist_TA']:.4f}"
        bb_data = f"{date_str}, BB_Upper: {df_plot.loc[idx, 'BB_Upper']:.4f}, BB_Lower: {df_plot.loc[idx, 'BB_Lower']:.4f}, BB_MA: {df_plot.loc[idx, 'BB_MA']:.4f}"
        if freq_label == "Daily":
            daily_ema_data.append(ema_data)
            daily_macd_data.append(macd_data)
            daily_bb_data.append(bb_data)
            ichimoku_conv = df_plot.loc[idx, 'Ichimoku_Conversion'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Conversion']) else 'NaN'
            ichimoku_base = df_plot.loc[idx, 'Ichimoku_Base'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Base']) else 'NaN'
            ichimoku_spana = df_plot.loc[idx, 'Ichimoku_SpanA'] if pd.notna(df_plot.loc[idx, 'Ichimoku_SpanA']) else 'NaN'
            ichimoku_spanb = df_plot.loc[idx, 'Ichimoku_SpanB'] if pd.notna(df_plot.loc[idx, 'Ichimoku_SpanB']) else 'NaN'
            ichimoku_lag = df_plot.loc[idx, 'Ichimoku_Lagging'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Lagging']) else 'NaN'
            daily_ichimoku_data.append(f"{date_str}, Ichimoku_Conversion: {ichimoku_conv}, Ichimoku_Base: {ichimoku_base}, Ichimoku_SpanA: {ichimoku_spana}, Ichimoku_SpanB: {ichimoku_spanb}, Ichimoku_Lagging: {ichimoku_lag}")
        elif freq_label == "Weekly":
            weekly_ema_data.append(ema_data)
            weekly_macd_data.append(macd_data)
            weekly_bb_data.append(bb_data)
            ichimoku_conv = df_plot.loc[idx, 'Ichimoku_Conversion'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Conversion']) else 'NaN'
            ichimoku_base = df_plot.loc[idx, 'Ichimoku_Base'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Base']) else 'NaN'
            ichimoku_spana = df_plot.loc[idx, 'Ichimoku_SpanA'] if pd.notna(df_plot.loc[idx, 'Ichimoku_SpanA']) else 'NaN'
            ichimoku_spanb = df_plot.loc[idx, 'Ichimoku_SpanB'] if pd.notna(df_plot.loc[idx, 'Ichimoku_SpanB']) else 'NaN'
            ichimoku_lag = df_plot.loc[idx, 'Ichimoku_Lagging'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Lagging']) else 'NaN'
            weekly_ichimoku_data.append(f"{date_str}, Ichimoku_Conversion: {ichimoku_conv}, Ichimoku_Base: {ichimoku_base}, Ichimoku_SpanA: {ichimoku_spana}, Ichimoku_SpanB: {ichimoku_spanb}, Ichimoku_Lagging: {ichimoku_lag}")
        elif freq_label == "Monthly":
            monthly_ema_data.append(ema_data)
            monthly_macd_data.append(macd_data)
            monthly_bb_data.append(bb_data)
            ichimoku_conv = df_plot.loc[idx, 'Ichimoku_Conversion'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Conversion']) else 'NaN'
            ichimoku_base = df_plot.loc[idx, 'Ichimoku_Base'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Base']) else 'NaN'
            ichimoku_spana = df_plot.loc[idx, 'Ichimoku_SpanA'] if pd.notna(df_plot.loc[idx, 'Ichimoku_SpanA']) else 'NaN'
            ichimoku_spanb = df_plot.loc[idx, 'Ichimoku_SpanB'] if pd.notna(df_plot.loc[idx, 'Ichimoku_SpanB']) else 'NaN'
            ichimoku_lag = df_plot.loc[idx, 'Ichimoku_Lagging'] if pd.notna(df_plot.loc[idx, 'Ichimoku_Lagging']) else 'NaN'
            monthly_ichimoku_data.append(f"{date_str}, Ichimoku_Conversion: {ichimoku_conv}, Ichimoku_Base: {ichimoku_base}, Ichimoku_SpanA: {ichimoku_spana}, Ichimoku_SpanB: {ichimoku_spanb}, Ichimoku_Lagging: {ichimoku_lag}")
    # Safely access the last row for title info
    if not df_plot.empty:
        close = df_plot["Close"].iloc[-1]
        previous_close = df_plot["Close"].iloc[-2] if len(df_plot) > 1 else float('nan')
        change_percent = (close - previous_close) / previous_close * 100 if previous_close != 0 else float('nan')
        ema5 = df_plot["EMA5"].iloc[-1]
        ema20 = df_plot["EMA20"].iloc[-1]
        ema40 = df_plot["EMA40"].iloc[-1]
        gap20 = (close - ema20) / ema20 * 100 if ema20 != 0 else float('inf')
        gap40 = (close - ema40) / ema40 * 100 if ema40 != 0 else float('inf')
        bb_upper = df_plot["BB_Upper"].iloc[-1]
        bb_lower = df_plot["BB_Lower"].iloc[-1]
        bb_ma = df_plot["BB_MA"].iloc[-1]
    else:
        close, previous_close, change_percent, ema5, ema20, ema40 = [float('nan')]*6
        gap20, gap40 = float('nan'), float('nan')
        bb_upper, bb_lower, bb_ma = [float('nan')] * 3

    title_line = f"{ticker} - {freq_label} Chart (as of {chart_creation_date.strftime('%Y-%m-%d')})"
    price_line = f"Close: {close:.2f} ({change_percent:+.2f}%), EMA5: {ema5:.2f}, EMA20: {ema20:.2f}, EMA40: {ema40:.2f}"
    gap_line = f"Gap EMA20: {gap20:.2f}%, EMA40: {gap40:.2f}%"
    bollinger_line = f"BB_Upper: {bb_upper:.2f}, BB_Lower: {bb_lower:.2f}, BB_MA: {bb_ma:.2f}"

    # 패널 번호 할당: 0=메인, 1=거래량, 2=MACD
    panel_map = {
        'Daily': 2,
        'Weekly': 2,
        'Monthly': 2
    }
    macd_panel = panel_map.get(freq_label, 2)

    apds = [
        mpf.make_addplot(df_plot["EMA5"], color="Red", label="EMA 5", panel=0),
        mpf.make_addplot(df_plot["EMA20"], color="orange", label="EMA 20", panel=0),
        mpf.make_addplot(df_plot["EMA40"], color="green", label="EMA 40", panel=0),
        # MACD
        mpf.make_addplot(df_plot["MACD_TA"], panel=macd_panel, color="purple", ylabel=f"MACD_{freq_label}", type='line', width=1.2, secondary_y=False, label="MACD"),
        mpf.make_addplot(df_plot["MACD_Signal_TA"], panel=macd_panel, color="red", type='line', width=1.2, secondary_y=False, label="MACD Signal"),
        mpf.make_addplot(df_plot["MACD_Hist_TA"], type='bar', panel=macd_panel, color='gray', width=0.7, alpha=0.5, label="MACD_Hist", secondary_y=False),
        mpf.make_addplot([0]*len(df_plot), panel=macd_panel, color='black', type='line', width=0.8, linestyle='dashed', secondary_y=False, label="Zero Line"),
        # 볼린저 밴드는 matplotlib로 오버레이하므로 제거
    ]

    volume_panel_height = 1
    macd_panel_height = 1
    main_panel_ratio = 3
    # 총 3개 패널: 0(메인), 1(거래량), 2(MACD)
    panel_ratios = (main_panel_ratio, volume_panel_height, macd_panel_height)

    fig, axes = mpf.plot(
        df_plot,
        type="candle",
        volume=True,
        style="yahoo",
        addplot=apds,
        returnfig=True,
        panel_ratios=panel_ratios,
        tight_layout=True,
    )

    fig.suptitle(f"{title_line}\n{price_line}\n{gap_line}\n{bollinger_line}", fontsize=13, y=1.15)

    # 볼린저 밴드를 matplotlib로 오버레이
    main_ax = axes[0]  # 메인 차트 축 (패널 0)
    
    # 볼린저 밴드 오버레이
    main_ax.fill_between(range(len(df_plot)), df_plot["BB_Upper"], df_plot["BB_Lower"], 
                       alpha=0.3, color='lightgrey', label='Bollinger Bands')
    main_ax.plot(range(len(df_plot)), df_plot["BB_Upper"], color='Grey', linewidth=1.0, label='BB_Upper')
    main_ax.plot(range(len(df_plot)), df_plot["BB_Lower"], color='Grey', linewidth=1.0, label='BB_Lower')
    main_ax.plot(range(len(df_plot)), df_plot["BB_MA"], color='black', linewidth=1.0, label='BB_MA')

    # 일목균형표 오버레이
    # 선행스팬1과 선행스팬2 사이를 구름으로 채우기
    span_a = df_plot["Ichimoku_SpanA"].dropna()
    span_b = df_plot["Ichimoku_SpanB"].dropna()
    
    # 일목균형표 차트 그리기 비활성화 (계산은 유지)
    # if not span_a.empty and not span_b.empty:
    #     # 구름 영역 채우기 (선행스팬1이 선행스팬2보다 높을 때는 빨간색, 낮을 때는 초록색)
    #     cloud_x = range(len(span_a))
    #     main_ax.fill_between(cloud_x, span_a, span_b, 
    #                        where=(span_a >= span_b), alpha=0.3, color='lightgreen', label='Ichimoku Cloud (Bullish)')
    #     main_ax.fill_between(cloud_x, span_a, span_b, 
    #                        where=(span_a < span_b), alpha=0.3, color='lightcoral', label='Ichimoku Cloud (Bearish)')
    #     
    #     # 선행스팬 라인 그리기
    #     main_ax.plot(cloud_x, span_a, color='blue', linewidth=1.5, label='Senkou Span A', alpha=0.8, linestyle='--')
    #     main_ax.plot(cloud_x, span_b, color='red', linewidth=1.5, label='Senkou Span B', alpha=0.8, linestyle='--')
    
    # 전환선, 기준선, 후행스팬 그리기
    conversion = df_plot["Ichimoku_Conversion"].dropna()
    base = df_plot["Ichimoku_Base"].dropna()
    lagging = df_plot["Ichimoku_Lagging"].dropna()
    
    # 일목균형표 선 그리기 비활성화 (계산은 유지)
    # if not conversion.empty:
    #     main_ax.plot(range(len(conversion)), conversion, color='yellow', linewidth=1.5, label='Tenkan-sen (Conversion)', alpha=0.8, linestyle='--')
    # if not base.empty:
    #     main_ax.plot(range(len(base)), base, color='purple', linewidth=1.5, label='Kijun-sen (Base)', alpha=0.8, linestyle='--')
    # if not lagging.empty:
    #     main_ax.plot(range(len(lagging)), lagging, color='green', linewidth=1.5, label='Chikou Span (Lagging)', alpha=0.8, linestyle='--')

    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, loc="upper left", fontsize="small")

    # 날짜별 폴더 구조 사용
    date_folder = get_date_folder_path(CHART_DIR, current_date_str)
    path = os.path.join(date_folder, f"{ticker}_{suffix}_{current_date_str}.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close('all')
    
    # 디버그 파일 생성
    debug_date_folder = get_date_folder_path(DEBUG_DIR, current_date_str)
    
    # EMA 디버그 파일
    if freq_label == "Daily":
        ema_debug_lines = []
        ema_debug_lines.append(f"[EMA DEBUG] Ticker: {ticker} (Chart Generation)\n")
        ema_debug_lines.append("[Daily EMA for Chart]")
        ema_debug_lines.extend(daily_ema_data)
        ema_debug_path = os.path.join(debug_date_folder, f"{ticker}_ema_chart_debug_{current_date_str}.txt")
        with open(ema_debug_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ema_debug_lines))
    
    return path 