import os
import csv
import json
import logging
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
import re
from utils.file_manager import safe_write_file
import io

# 상수 정의
STOCK_LISTS_DIR = 'stock_lists'
SUMMARY_DIR = 'static/summaries'

# 데이터베이스 객체 생성
db = SQLAlchemy()

class User(UserMixin, db.Model):
    """사용자 모델"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(25), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)  # 어드민 권한 추가
    is_withdrawn = db.Column(db.Boolean, default=False)  # 탈퇴 여부
    withdrawn_at = db.Column(db.DateTime)  # 탈퇴 일시
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계 설정
    stock_lists = relationship('StockList', back_populates='user', cascade='all, delete-orphan')
    analysis_history = relationship('AnalysisHistory', back_populates='user', cascade='all, delete-orphan')
    
    def set_password(self, password):
        """비밀번호 설정"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """비밀번호 확인"""
        return check_password_hash(self.password_hash, password)
    
    def get_full_name(self):
        """전체 이름 반환"""
        return f"{self.first_name} {self.last_name}".strip()
    
    def is_administrator(self):
        """어드민 권한 확인"""
        return self.is_admin
    
    def withdraw_account(self):
        """계정 탈퇴 처리"""
        self.is_active = False
        self.is_withdrawn = True
        self.withdrawn_at = datetime.utcnow()
    
    def is_withdrawn_user(self):
        """탈퇴 사용자 여부 확인"""
        return self.is_withdrawn
    
    def __repr__(self):
        return f'<User {self.username}>'

class StockList(db.Model):
    """종목 리스트 모델"""
    __tablename__ = 'stock_lists'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 외래 키
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # 관계 설정
    user = relationship('User', back_populates='stock_lists')
    stocks = relationship('Stock', back_populates='stock_list', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<StockList {self.name}>'

class Stock(db.Model):
    """종목 모델"""
    __tablename__ = 'stocks'
    
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 외래 키
    stock_list_id = db.Column(db.Integer, db.ForeignKey('stock_lists.id'), nullable=False)
    
    # 관계 설정
    stock_list = relationship('StockList', back_populates='stocks')
    
    def __repr__(self):
        return f'<Stock {self.ticker}>'

class AnalysisHistory(db.Model):
    """분석 히스토리 모델"""
    __tablename__ = 'analysis_history'
    
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False)
    analysis_date = db.Column(db.Date, nullable=False)
    analysis_type = db.Column(db.String(50), default='daily')  # daily, weekly, monthly
    chart_path = db.Column(db.String(500))
    analysis_path = db.Column(db.String(500))
    summary = db.Column(db.Text)
    status = db.Column(db.String(20), default='completed')  # completed, failed, pending
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 외래 키
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # 관계 설정
    user = relationship('User', back_populates='analysis_history')
    
    def __repr__(self):
        return f'<AnalysisHistory {self.ticker} {self.analysis_date}>'

class NewsletterSubscription(db.Model):
    """뉴스레터 구독 모델"""
    __tablename__ = 'newsletter_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    frequency = db.Column(db.String(20), default='daily')  # daily, weekly, monthly
    send_time = db.Column(db.Time, default=datetime.strptime('09:00', '%H:%M').time())
    include_charts = db.Column(db.Boolean, default=True)
    include_summary = db.Column(db.Boolean, default=True)
    include_technical_analysis = db.Column(db.Boolean, default=True)
    unsubscribe_token = db.Column(db.String(100), unique=True)  # 구독 해지용 토큰
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계 설정
    user = relationship('User', backref='newsletter_subscription')
    
    def generate_unsubscribe_token(self):
        """구독 해지용 토큰 생성"""
        import secrets
        self.unsubscribe_token = secrets.token_urlsafe(32)
        return self.unsubscribe_token
    
    def __repr__(self):
        return f'<NewsletterSubscription {self.user_id} {self.frequency}>'

class EmailLog(db.Model):
    """이메일 발송 로그 모델"""
    __tablename__ = 'email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    email_type = db.Column(db.String(50), nullable=False)  # newsletter, analysis, notification
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='sent')  # sent, failed, pending
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    error_message = db.Column(db.Text)
    
    # 관계 설정
    user = relationship('User', backref='email_logs')
    
    def __repr__(self):
        return f'<EmailLog {self.user_id} {self.email_type} {self.status}>'

# 유틸리티 함수들
def get_stock_list_path(list_name):
    """주식 리스트 파일 경로를 반환합니다."""
    return os.path.join(STOCK_LISTS_DIR, f"{list_name}.csv")

def get_analysis_summary_path(list_name):
    """분석 요약 파일 경로를 반환합니다."""
    return os.path.join(SUMMARY_DIR, f"{list_name}_analysis_results.json")

def ensure_stock_list_exists(list_name):
    """주식 리스트 파일이 존재하지 않으면 생성합니다."""
    path = get_stock_list_path(list_name)
    if not os.path.exists(path):
        # CSV 문자열 생성
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ticker", "name"])
        csv_content = output.getvalue()
        output.close()
        
        # safe_write_file로 저장
        safe_write_file(path, csv_content)

def _extract_summary_from_analysis(analysis_text, num_sentences=3):
    """
    AI 분석 텍스트에서 핵심 요약을 안정적으로 추출합니다.
    번호 매김 문장(1. 2. 3.)을 우선적으로 찾아 정확히 3개만 추출합니다.
    """
    if not analysis_text:
        return "요약 없음."

    # 텍스트 정리
    text = analysis_text.strip()
    
    # 간단한 방법: 1., 2., 3. 으로 시작하는 문장들을 직접 찾기
    sentences = []
    
    # 각 번호별로 직접 검색
    for num in range(1, num_sentences + 1):
        # 번호로 시작하는 패턴 찾기 (줄 시작 또는 공백 뒤)
        patterns = [
            f"{num}. ",  # 문장 시작
            f" {num}. ", # 공백 뒤
            f"\n{num}. " # 줄바꿈 뒤
        ]
        
        sentence_found = False
        for pattern in patterns:
            start_pos = text.find(pattern)
            if start_pos != -1:
                # 패턴 발견, 다음 번호까지 또는 텍스트 끝까지 추출
                start_pos = start_pos if pattern.startswith(f"{num}.") else start_pos + 1  # 공백 제거
                
                # 다음 번호 찾기 (num+1 또는 4번이 있다면 4번까지, 아니면 텍스트 끝까지)
                next_num = num + 1
                next_patterns = [
                    f"{next_num}. ",
                    f" {next_num}. ",
                    f"\n{next_num}. "
                ]
                
                # 3번째 이후라면 더 넓은 범위에서 종료점 찾기
                if num >= 3:
                    # 4번 이후의 번호들도 찾기
                    for check_num in range(4, 10):  # 4~9번까지 확인
                        next_patterns.extend([
                            f"{check_num}. ",
                            f" {check_num}. ",
                            f"\n{check_num}. "
                        ])
                    # 특정 종료 키워드들도 추가
                    next_patterns.extend([
                        "\n\n**", "**결론", "**전망", "**요약", "**주의", 
                        "면책 조항", "투자 주의사항", "본 분석은"
                    ])
                
                # 다음 번호 중 가장 가까운 위치 찾기
                end_pos = len(text)
                for next_pattern in next_patterns:
                    next_pos = text.find(next_pattern, start_pos + 1)
                    if next_pos != -1 and next_pos < end_pos:
                        end_pos = next_pos
                
                # 3번째인 경우 더 적극적으로 종료점 찾기
                if num == 3:
                    # 3번 문장이 끝나는 지점을 더 정확히 찾기
                    sentence_enders = ["다.", "니다.", "습니다.", "됩니다.", "있습니다."]
                    for ender in sentence_enders:
                        ender_pos = text.find(ender, start_pos + 10)  # 최소 10글자 이후부터 검색
                        if ender_pos != -1 and ender_pos + len(ender) < end_pos:
                            # 이 종료점이 다른 번호 시작점보다 앞에 있다면 사용
                            potential_end = ender_pos + len(ender)
                            # 다음 20글자 내에 번호가 없다면 여기서 종료
                            next_20_chars = text[potential_end:potential_end + 20]
                            has_number = any(f"{i}." in next_20_chars for i in range(1, 10))
                            if not has_number:
                                end_pos = potential_end
                                break
                
                # 문장 추출
                sentence = text[start_pos:end_pos].strip()
                if sentence:
                    sentences.append(sentence)
                    sentence_found = True
                    break
        
        # 해당 번호를 찾지 못한 경우 중단
        if not sentence_found:
            break
    
    # 3개까지만 확실하게 제한
    sentences = sentences[:num_sentences]
    
    # 결과 반환
    if sentences:
        return '<br>'.join(sentences)
    
    # 번호 매김이 없는 경우 폴백: 한국어 완전한 문장 찾기
    korean_sentences = re.findall(r'[^.]*?(?:니다|다)\.', text)
    if korean_sentences:
        selected = korean_sentences[:num_sentences]
        return '<br>'.join(selected) if len(selected) > 1 else ' '.join(selected)
    
    return "요약 없음."

# 기본 주식 리스트 초기화 (하위 호환성을 위해 유지)
# 데이터베이스가 초기화된 후에 실행되도록 수정 필요
# ensure_stock_list_exists("default") 