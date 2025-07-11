"""
주식 기술지표 계산 및 저장 서비스
- OHLCV 데이터 저장 (일봉/주봉/월봉)
- 기술지표 계산 및 저장 (EMA, MACD, 볼린저밴드, 일목균형표, RSI, 스토캐스틱, 거래량 비율)
- 파일 관리 (90일 이상 된 파일 자동 삭제)
- 골드크로스/데드크로스 감지
"""

import pandas as pd
import numpy as np
import os
import logging
from datetime import datetime, timedelta
import ta
import glob


class IndicatorService:
    def __init__(self):
        self.indicators_dir = "static/indicators"
        self.ensure_directory_exists()
    
    def ensure_directory_exists(self):
        """indicators 디렉토리가 존재하지 않으면 생성"""
        if not os.path.exists(self.indicators_dir):
            os.makedirs(self.indicators_dir)
    
    def generate_filename(self, ticker, indicator_type, timeframe, timestamp=None):
        """파일명 생성: {ticker}_{indicator}_{timeframe}_{YYYYMMDD}_{HHMMSS}.csv"""
        if timestamp is None:
            timestamp = datetime.now()
        date_str = timestamp.strftime("%Y%m%d")
        time_str = timestamp.strftime("%H%M%S")
        return f"{ticker}_{indicator_type}_{timeframe}_{date_str}_{time_str}.csv"
    
    def save_ohlcv_data(self, ticker, daily_data, timestamp=None):
        """일봉/주봉/월봉 OHLCV 데이터를 CSV 파일로 저장"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            # MultiIndex 컬럼 처리
            if isinstance(daily_data.columns, pd.MultiIndex):
                # MultiIndex인 경우 첫 번째 레벨만 사용
                daily_data.columns = daily_data.columns.get_level_values(0)
            
            # 필요한 컬럼만 선택
            daily_data = daily_data[["Open", "High", "Low", "Close", "Volume"]].dropna()
            
            # 일봉 데이터 저장
            daily_filename = self.generate_filename(ticker, "ohlcv", "d", timestamp)
            daily_path = os.path.join(self.indicators_dir, daily_filename)
            daily_data.to_csv(daily_path, index=True)
            logging.info(f"[{ticker}] Daily OHLCV data saved: {daily_filename}")
            
            # 주봉 데이터 계산 및 저장
            weekly_data = daily_data.resample('W').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
            
            weekly_filename = self.generate_filename(ticker, "ohlcv", "w", timestamp)
            weekly_path = os.path.join(self.indicators_dir, weekly_filename)
            weekly_data.to_csv(weekly_path, index=True)
            logging.info(f"[{ticker}] Weekly OHLCV data saved: {weekly_filename}")
            
            # 월봉 데이터 계산 및 저장
            monthly_data = daily_data.resample('M').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
            
            monthly_filename = self.generate_filename(ticker, "ohlcv", "m", timestamp)
            monthly_path = os.path.join(self.indicators_dir, monthly_filename)
            monthly_data.to_csv(monthly_path, index=True)
            logging.info(f"[{ticker}] Monthly OHLCV data saved: {monthly_filename}")
            
            return {
                'daily': daily_path,
                'weekly': weekly_path,
                'monthly': monthly_path
            }
            
        except Exception as e:
            logging.error(f"[{ticker}] Error saving OHLCV data: {str(e)}")
            return None
    
    def calculate_and_save_ema(self, ticker, ohlcv_data, timeframe, timestamp=None):
        """EMA 지표 계산 및 저장"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            ema_data = pd.DataFrame(index=ohlcv_data.index)
            ema_data['EMA5'] = ta.trend.ema_indicator(ohlcv_data['Close'], window=5)
            ema_data['EMA20'] = ta.trend.ema_indicator(ohlcv_data['Close'], window=20)
            ema_data['EMA40'] = ta.trend.ema_indicator(ohlcv_data['Close'], window=40)
            ema_data['Close'] = ohlcv_data['Close']
            
            # 각 EMA를 별도 파일로 저장
            for period in [5, 20, 40]:
                filename = self.generate_filename(ticker, f"ema{period}", timeframe, timestamp)
                filepath = os.path.join(self.indicators_dir, filename)
                
                single_ema_data = pd.DataFrame({
                    'EMA': ema_data[f'EMA{period}'],
                    'Close': ema_data['Close']
                })
                single_ema_data.to_csv(filepath, index=True)
                logging.info(f"[{ticker}] EMA{period} {timeframe} data saved: {filename}")
            
            return ema_data
            
        except Exception as e:
            logging.error(f"[{ticker}] Error calculating EMA {timeframe}: {str(e)}")
            return None
    
    def calculate_and_save_macd(self, ticker, ohlcv_data, timeframe, timestamp=None):
        """MACD 지표 계산 및 저장"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            macd_data = pd.DataFrame(index=ohlcv_data.index)
            macd_data['MACD'] = ta.trend.macd_diff(ohlcv_data['Close'])
            macd_data['MACD_Signal'] = ta.trend.macd_signal(ohlcv_data['Close'])
            macd_data['MACD_Histogram'] = ta.trend.macd(ohlcv_data['Close'])
            macd_data['Close'] = ohlcv_data['Close']
            
            filename = self.generate_filename(ticker, "macd", timeframe, timestamp)
            filepath = os.path.join(self.indicators_dir, filename)
            macd_data.to_csv(filepath, index=True)
            logging.info(f"[{ticker}] MACD {timeframe} data saved: {filename}")
            
            return macd_data
            
        except Exception as e:
            logging.error(f"[{ticker}] Error calculating MACD {timeframe}: {str(e)}")
            return None
    
    def calculate_and_save_bollinger_bands(self, ticker, ohlcv_data, timeframe, timestamp=None):
        """볼린저 밴드 지표 계산 및 저장"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            bb_data = pd.DataFrame(index=ohlcv_data.index)
            bb_data['BB_Upper'] = ta.volatility.bollinger_hband(ohlcv_data['Close'])
            bb_data['BB_Middle'] = ta.volatility.bollinger_mavg(ohlcv_data['Close'])
            bb_data['BB_Lower'] = ta.volatility.bollinger_lband(ohlcv_data['Close'])
            bb_data['Close'] = ohlcv_data['Close']
            
            filename = self.generate_filename(ticker, "bollinger", timeframe, timestamp)
            filepath = os.path.join(self.indicators_dir, filename)
            bb_data.to_csv(filepath, index=True)
            logging.info(f"[{ticker}] Bollinger Bands {timeframe} data saved: {filename}")
            
            return bb_data
            
        except Exception as e:
            logging.error(f"[{ticker}] Error calculating Bollinger Bands {timeframe}: {str(e)}")
            return None
    
    def calculate_and_save_ichimoku(self, ticker, ohlcv_data, timeframe, timestamp=None):
        """일목균형표 지표 계산 및 저장"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            ichimoku_data = pd.DataFrame(index=ohlcv_data.index)
            ichimoku_data['Tenkan'] = ta.trend.ichimoku_conversion_line(ohlcv_data['High'], ohlcv_data['Low'])
            ichimoku_data['Kijun'] = ta.trend.ichimoku_base_line(ohlcv_data['High'], ohlcv_data['Low'])
            ichimoku_data['Senkou_A'] = ta.trend.ichimoku_a(ohlcv_data['High'], ohlcv_data['Low'])
            ichimoku_data['Senkou_B'] = ta.trend.ichimoku_b(ohlcv_data['High'], ohlcv_data['Low'])
            ichimoku_data['Close'] = ohlcv_data['Close']
            
            filename = self.generate_filename(ticker, "ichimoku", timeframe, timestamp)
            filepath = os.path.join(self.indicators_dir, filename)
            ichimoku_data.to_csv(filepath, index=True)
            logging.info(f"[{ticker}] Ichimoku {timeframe} data saved: {filename}")
            
            return ichimoku_data
            
        except Exception as e:
            logging.error(f"[{ticker}] Error calculating Ichimoku {timeframe}: {str(e)}")
            return None
    
    def calculate_and_save_rsi(self, ticker, ohlcv_data, timeframe, timestamp=None):
        """RSI 지표 계산 및 저장"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            rsi_data = pd.DataFrame(index=ohlcv_data.index)
            rsi_data['RSI'] = ta.momentum.rsi(ohlcv_data['Close'])
            rsi_data['Close'] = ohlcv_data['Close']
            
            filename = self.generate_filename(ticker, "rsi", timeframe, timestamp)
            filepath = os.path.join(self.indicators_dir, filename)
            rsi_data.to_csv(filepath, index=True)
            logging.info(f"[{ticker}] RSI {timeframe} data saved: {filename}")
            
            return rsi_data
            
        except Exception as e:
            logging.error(f"[{ticker}] Error calculating RSI {timeframe}: {str(e)}")
            return None
    
    def calculate_and_save_stochastic(self, ticker, ohlcv_data, timeframe, timestamp=None):
        """스토캐스틱 오실레이터 계산 및 저장"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            stoch_data = pd.DataFrame(index=ohlcv_data.index)
            stoch_data['Stoch_K'] = ta.momentum.stoch(ohlcv_data['High'], ohlcv_data['Low'], ohlcv_data['Close'])
            stoch_data['Stoch_D'] = ta.momentum.stoch_signal(ohlcv_data['High'], ohlcv_data['Low'], ohlcv_data['Close'])
            stoch_data['Close'] = ohlcv_data['Close']
            
            filename = self.generate_filename(ticker, "stochastic", timeframe, timestamp)
            filepath = os.path.join(self.indicators_dir, filename)
            stoch_data.to_csv(filepath, index=True)
            logging.info(f"[{ticker}] Stochastic {timeframe} data saved: {filename}")
            
            return stoch_data
            
        except Exception as e:
            logging.error(f"[{ticker}] Error calculating Stochastic {timeframe}: {str(e)}")
            return None
    
    def calculate_and_save_volume_ratios(self, ticker, ohlcv_data, timeframe, timestamp=None):
        """거래량 비율 계산 및 저장 (5일/20일/40일 평균 대비)"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            volume_data = pd.DataFrame(index=ohlcv_data.index)
            volume_data['Volume'] = ohlcv_data['Volume']
            
            # 5일, 20일, 40일 평균 거래량 계산
            volume_data['Volume_MA5'] = volume_data['Volume'].rolling(window=5).mean()
            volume_data['Volume_MA20'] = volume_data['Volume'].rolling(window=20).mean()
            volume_data['Volume_MA40'] = volume_data['Volume'].rolling(window=40).mean()
            
            # 비율 계산 (%)
            volume_data['Volume_Ratio_5d'] = (volume_data['Volume'] / volume_data['Volume_MA5'] * 100).round(2)
            volume_data['Volume_Ratio_20d'] = (volume_data['Volume'] / volume_data['Volume_MA20'] * 100).round(2)
            volume_data['Volume_Ratio_40d'] = (volume_data['Volume'] / volume_data['Volume_MA40'] * 100).round(2)
            
            # 각 비율을 별도 파일로 저장
            for period in [5, 20, 40]:
                filename = self.generate_filename(ticker, f"volume_ratio_{period}d", timeframe, timestamp)
                filepath = os.path.join(self.indicators_dir, filename)
                
                ratio_data = pd.DataFrame({
                    'Volume': volume_data['Volume'],
                    f'Volume_MA{period}': volume_data[f'Volume_MA{period}'],
                    f'Volume_Ratio_{period}d': volume_data[f'Volume_Ratio_{period}d']
                })
                ratio_data.to_csv(filepath, index=True)
                logging.info(f"[{ticker}] Volume Ratio {period}d {timeframe} data saved: {filename}")
            
            return volume_data
            
        except Exception as e:
            logging.error(f"[{ticker}] Error calculating Volume Ratios {timeframe}: {str(e)}")
            return None
    
    def detect_crossovers(self, ticker, timeframe, days_back=30):
        """골드크로스/데드크로스 감지 (최근 30일 내)"""
        try:
            # 최근 파일들 찾기
            macd_files = glob.glob(os.path.join(self.indicators_dir, f"{ticker}_macd_{timeframe}_*.csv"))
            ema5_files = glob.glob(os.path.join(self.indicators_dir, f"{ticker}_ema5_{timeframe}_*.csv"))
            ema20_files = glob.glob(os.path.join(self.indicators_dir, f"{ticker}_ema20_{timeframe}_*.csv"))
            ema40_files = glob.glob(os.path.join(self.indicators_dir, f"{ticker}_ema40_{timeframe}_*.csv"))
            
            if not (macd_files and ema5_files and ema20_files and ema40_files):
                return None
            
            # 가장 최근 파일들 선택
            macd_file = max(macd_files, key=os.path.getctime)
            ema5_file = max(ema5_files, key=os.path.getctime)
            ema20_file = max(ema20_files, key=os.path.getctime)
            ema40_file = max(ema40_files, key=os.path.getctime)
            
            # 데이터 로드
            macd_data = pd.read_csv(macd_file, index_col=0, parse_dates=True)
            ema5_data = pd.read_csv(ema5_file, index_col=0, parse_dates=True)
            ema20_data = pd.read_csv(ema20_file, index_col=0, parse_dates=True)
            ema40_data = pd.read_csv(ema40_file, index_col=0, parse_dates=True)
            
            # 최근 30일 데이터만 사용
            cutoff_date = datetime.now() - timedelta(days=days_back)
            macd_recent = macd_data[macd_data.index >= cutoff_date]
            ema5_recent = ema5_data[ema5_data.index >= cutoff_date]
            ema20_recent = ema20_data[ema20_data.index >= cutoff_date]
            ema40_recent = ema40_data[ema40_data.index >= cutoff_date]
            
            crossovers = {}
            
            # MACD 크로스오버 감지
            if len(macd_recent) > 1:
                macd_cross = self._detect_macd_crossover(macd_recent)
                if macd_cross:
                    crossovers['macd'] = macd_cross
            
            # EMA 크로스오버 감지
            if len(ema5_recent) > 1 and len(ema20_recent) > 1:
                ema_cross = self._detect_ema_crossover(ema5_recent, ema20_recent, ema40_recent)
                if ema_cross:
                    crossovers['ema'] = ema_cross
            
            return crossovers
            
        except Exception as e:
            logging.error(f"[{ticker}] Error detecting crossovers {timeframe}: {str(e)}")
            return None
    
    def _detect_macd_crossover(self, macd_data):
        """MACD 크로스오버 감지"""
        try:
            # MACD > Signal 크로스 찾기
            macd_above = macd_data['MACD'] > macd_data['MACD_Signal']
            crossover_points = macd_above != macd_above.shift(1)
            
            if crossover_points.any():
                last_cross_date = crossover_points[crossover_points].index[-1]
                is_golden = macd_data.loc[last_cross_date, 'MACD'] > macd_data.loc[last_cross_date, 'MACD_Signal']
                
                return {
                    'date': last_cross_date,
                    'type': 'Golden Cross' if is_golden else 'Dead Cross',
                    'macd': macd_data.loc[last_cross_date, 'MACD'],
                    'signal': macd_data.loc[last_cross_date, 'MACD_Signal']
                }
            return None
            
        except Exception as e:
            logging.error(f"Error detecting MACD crossover: {str(e)}")
            return None
    
    def _detect_ema_crossover(self, ema5_data, ema20_data, ema40_data):
        """EMA 크로스오버 감지 (대순환 분석 적용)"""
        try:
            # 공통 인덱스 찾기
            common_index = ema5_data.index.intersection(ema20_data.index).intersection(ema40_data.index)
            if len(common_index) < 10:  # 최소 10개 데이터 필요
                return None
            
            # 최근 데이터만 사용
            recent_index = common_index[-10:]
            
            # EMA 데이터 정리
            ema5_values = ema5_data.loc[recent_index, 'EMA']
            ema20_values = ema20_data.loc[recent_index, 'EMA']
            ema40_values = ema40_data.loc[recent_index, 'EMA']
            
            # 각 날짜의 EMA 상태 분석
            crossover_events = []
            
            for i in range(1, len(recent_index)):
                prev_date = recent_index[i-1]
                curr_date = recent_index[i]
                
                # 이전 상태
                prev_ema5 = ema5_values.iloc[i-1]
                prev_ema20 = ema20_values.iloc[i-1]
                prev_ema40 = ema40_values.iloc[i-1]
                
                # 현재 상태
                curr_ema5 = ema5_values.iloc[i]
                curr_ema20 = ema20_values.iloc[i]
                curr_ema40 = ema40_values.iloc[i]
                
                # 이전 상태와 현재 상태 분류
                prev_state = self._classify_ema_state(prev_ema5, prev_ema20, prev_ema40)
                curr_state = self._classify_ema_state(curr_ema5, curr_ema20, curr_ema40)
                
                # 크로스오버 감지
                crossover_type = self._detect_crossover_type(prev_state, curr_state, prev_ema5, prev_ema20, prev_ema40, curr_ema5, curr_ema20, curr_ema40)
                
                if crossover_type:
                    crossover_events.append({
                        'date': curr_date,
                        'type': crossover_type,
                        'ema5': curr_ema5,
                        'ema20': curr_ema20,
                        'ema40': curr_ema40,
                        'prev_state': prev_state,
                        'curr_state': curr_state
                    })
            
            # 가장 최근 크로스오버 반환
            if crossover_events:
                return crossover_events[-1]
            
            return None
            
        except Exception as e:
            logging.error(f"Error detecting EMA crossover: {str(e)}")
            return None
    
    def _classify_ema_state(self, ema5, ema20, ema40):
        """EMA 상태 분류 (대순환 분석 기준)"""
        if ema5 > ema20 > ema40:
            return "안정_상승기"
        elif ema20 > ema5 > ema40:
            return "하락_변화기1"
        elif ema20 > ema40 > ema5:
            return "하락_변화기2"
        elif ema40 > ema20 > ema5:
            return "안정_하락기"
        elif ema40 > ema5 > ema20:
            return "상승_변화기1"
        elif ema5 > ema40 > ema20:
            return "상승_변화기2"
        else:
            return "혼조"
    
    def _detect_crossover_type(self, prev_state, curr_state, prev_ema5, prev_ema20, prev_ema40, curr_ema5, curr_ema20, curr_ema40):
        """크로스오버 타입 감지"""
        # 골드크로스 감지
        if prev_state == "안정_하락기" and curr_state == "상승_변화기1":
            # EMA5가 EMA20을 상향돌파 (골드크로스1)
            if prev_ema5 <= prev_ema20 and curr_ema5 > curr_ema20:
                return "Golden Cross 1"
        
        elif prev_state == "상승_변화기1" and curr_state == "상승_변화기2":
            # EMA5가 EMA40을 상향돌파 (골드크로스2)
            if prev_ema5 <= prev_ema40 and curr_ema5 > curr_ema40:
                return "Golden Cross 2"
        
        elif prev_state == "상승_변화기2" and curr_state == "안정_상승기":
            # EMA20이 EMA40을 상향돌파 (골드크로스3)
            if prev_ema20 <= prev_ema40 and curr_ema20 > curr_ema40:
                return "Golden Cross 3"
        
        # 데드크로스 감지
        elif prev_state == "안정_상승기" and curr_state == "하락_변화기1":
            # EMA5가 EMA20을 하향돌파 (데드크로스1)
            if prev_ema5 >= prev_ema20 and curr_ema5 < curr_ema20:
                return "Dead Cross 1"
        
        elif prev_state == "하락_변화기1" and curr_state == "하락_변화기2":
            # EMA5가 EMA40을 하향돌파 (데드크로스2)
            if prev_ema5 >= prev_ema40 and curr_ema5 < curr_ema40:
                return "Dead Cross 2"
        
        elif prev_state == "하락_변화기2" and curr_state == "안정_하락기":
            # EMA20이 EMA40을 하향돌파 (데드크로스3)
            if prev_ema20 >= prev_ema40 and curr_ema20 < curr_ema40:
                return "Dead Cross 3"
        
        return None
    
    def process_all_indicators(self, ticker, daily_data, timestamp=None):
        """모든 지표를 계산하고 저장하는 통합 함수"""
        if timestamp is None:
            timestamp = datetime.now()
        
        logging.info(f"[{ticker}] Starting comprehensive indicator calculation and storage...")
        
        try:
            # 1. OHLCV 데이터 저장
            ohlcv_paths = self.save_ohlcv_data(ticker, daily_data, timestamp)
            if not ohlcv_paths:
                return None
            
            # 2. 주봉, 월봉 데이터 계산
            weekly_data = daily_data.resample('W').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            
            monthly_data = daily_data.resample('M').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            
            # 3. 각 시간대별로 모든 지표 계산
            timeframes = [
                ('d', daily_data),
                ('w', weekly_data),
                ('m', monthly_data)
            ]
            
            results = {}
            
            for timeframe, data in timeframes:
                if len(data) < 50:  # 최소 데이터 요구사항
                    logging.warning(f"[{ticker}] Insufficient data for {timeframe} timeframe: {len(data)} rows")
                    continue
                
                timeframe_results = {}
                
                # EMA 계산
                timeframe_results['ema'] = self.calculate_and_save_ema(ticker, data, timeframe, timestamp)
                
                # MACD 계산
                timeframe_results['macd'] = self.calculate_and_save_macd(ticker, data, timeframe, timestamp)
                
                # 볼린저 밴드 계산
                timeframe_results['bollinger'] = self.calculate_and_save_bollinger_bands(ticker, data, timeframe, timestamp)
                
                # 일목균형표 계산
                timeframe_results['ichimoku'] = self.calculate_and_save_ichimoku(ticker, data, timeframe, timestamp)
                
                # RSI 계산
                timeframe_results['rsi'] = self.calculate_and_save_rsi(ticker, data, timeframe, timestamp)
                
                # 스토캐스틱 계산
                timeframe_results['stochastic'] = self.calculate_and_save_stochastic(ticker, data, timeframe, timestamp)
                
                # 거래량 비율 계산
                timeframe_results['volume_ratios'] = self.calculate_and_save_volume_ratios(ticker, data, timeframe, timestamp)
                
                results[timeframe] = timeframe_results
            
            logging.info(f"[{ticker}] All indicators calculated and saved successfully")
            return results
            
        except Exception as e:
            logging.error(f"[{ticker}] Error in process_all_indicators: {str(e)}")
            return None
    
    def cleanup_old_files(self, days_to_keep=90):
        """90일 이상 된 지표 파일들을 삭제 (주석 처리된 상태로 구현)"""
        # 주석 처리: 나중에 스케줄링과 함께 사용
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            deleted_count = 0
            
            # indicators 디렉토리의 모든 CSV 파일 확인
            for filename in os.listdir(self.indicators_dir):
                if filename.endswith('.csv'):
                    filepath = os.path.join(self.indicators_dir, filename)
                    
                    # 파일 수정 시간 확인
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    
                    if file_mtime < cutoff_date:
                        os.remove(filepath)
                        deleted_count += 1
                        logging.info(f"Deleted old indicator file: {filename}")
            
            logging.info(f"Cleanup completed. Deleted {deleted_count} old indicator files.")
            return deleted_count
            
        except Exception as e:
            logging.error(f"Error during file cleanup: {str(e)}")
            return 0
        """
        pass
    
    def get_latest_indicator_data(self, ticker, indicator_type, timeframe, rows=45):
        """저장된 지표 파일에서 최근 45개 데이터를 읽어옴"""
        try:
            # 해당 지표의 최근 파일 찾기
            pattern = f"{ticker}_{indicator_type}_{timeframe}_*.csv"
            files = glob.glob(os.path.join(self.indicators_dir, pattern))
            
            if not files:
                return None
            
            # 가장 최근 파일 선택
            latest_file = max(files, key=os.path.getctime)
            
            # 데이터 로드
            data = pd.read_csv(latest_file, index_col=0, parse_dates=True)
            
            # 최근 45개 행만 반환
            return data.tail(rows)
            
        except Exception as e:
            logging.error(f"[{ticker}] Error reading indicator data {indicator_type}_{timeframe}: {str(e)}")
            return None


# 전역 인스턴스 생성
indicator_service = IndicatorService() 