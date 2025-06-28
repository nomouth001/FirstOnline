import os
import logging
import base64
from datetime import datetime, timedelta
from jinja2 import Template
from models import db, User, StockList, Stock, AnalysisHistory, NewsletterSubscription
from services.email_service import email_service

logger = logging.getLogger(__name__)

class NewsletterService:
    """뉴스레터 생성 및 발송 서비스"""
    
    def __init__(self):
        self.template_dir = 'templates/email'
        self._ensure_template_dir()
    
    def _ensure_template_dir(self):
        """이메일 템플릿 디렉토리 생성"""
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir)
    
    def generate_newsletter_content(self, user, stock_list=None, analysis_date=None):
        """사용자별 뉴스레터 콘텐츠 생성"""
        try:
            if not analysis_date:
                analysis_date = datetime.now().date()
            
            # 사용자의 구독 설정 가져오기
            subscription = NewsletterSubscription.query.filter_by(user_id=user.id).first()
            if not subscription or not subscription.is_active:
                logger.info(f"사용자 {user.id}의 뉴스레터 구독이 비활성화되어 있습니다.")
                return None
            
            # 관리자는 모든 리스트의 종목을 중복 제거해서 통합
            if user.is_administrator():
                return self._generate_admin_newsletter_content(user, analysis_date, subscription)
            
            # 일반 사용자는 기존 방식 유지
            if not stock_list:
                # 기본 리스트 찾기
                stock_list = StockList.query.filter_by(user_id=user.id, is_default=True).first()
                if not stock_list:
                    stock_list = StockList.query.filter_by(user_id=user.id).first()
                if not stock_list:
                    logger.info(f"사용자 {user.id}의 종목 리스트가 없습니다.")
                    return None
            
            # 종목별 분석 결과 수집
            stock_analyses = []
            
            # 1. 먼저 AnalysisHistory 테이블에서 검색
            for stock in stock_list.stocks:
                analysis = AnalysisHistory.query.filter_by(
                    user_id=user.id,
                    ticker=stock.ticker,
                    analysis_date=analysis_date,
                    status='completed'
                ).first()
                
                if analysis:
                    stock_analyses.append({
                        'ticker': stock.ticker,
                        'name': stock.name,
                        'summary': analysis.summary,
                        'analysis_path': analysis.analysis_path,
                        'chart_path': analysis.chart_path
                    })
            
            # 2. AnalysisHistory에 결과가 없으면 파일 기반에서 검색 (최근 7일간)
            if not stock_analyses:
                from datetime import timedelta
                
                # 오늘부터 최근 7일간 검색
                for i in range(7):
                    search_date = analysis_date - timedelta(days=i)
                    stock_analyses = self._get_analyses_from_files(user, stock_list, search_date)
                    if stock_analyses:
                        logger.info(f"분석 결과를 {search_date} 날짜에서 발견했습니다.")
                        break
            
            if not stock_analyses:
                logger.info(f"사용자 {user.id}의 분석 결과가 없습니다.")
                return None
            
            # 뉴스레터 HTML 생성
            html_content = self._create_newsletter_html(user, stock_analyses, analysis_date, subscription)
            text_content = self._create_newsletter_text(user, stock_analyses, analysis_date, subscription)
            
            return {
                'html': html_content,
                'text': text_content,
                'stock_count': len(stock_analyses)
            }
            
        except Exception as e:
            logger.error(f"뉴스레터 콘텐츠 생성 실패: {e}")
            return None
    
    def _generate_admin_newsletter_content(self, user, analysis_date, subscription):
        """관리자용 통합 뉴스레터 콘텐츠 생성 (리스트별로 수익률 내림차순 정렬, 중복 포함)"""
        try:
            from datetime import timedelta
            import json
            import os
            from models import get_analysis_summary_path
            
            # 모든 종목 리스트 가져오기
            all_stock_lists = StockList.query.filter_by(user_id=user.id).all()
            if not all_stock_lists:
                logger.info(f"관리자 {user.id}의 종목 리스트가 없습니다.")
                return None
            
            # 리스트별 분석 결과 수집
            list_summaries = []
            all_stock_analyses = []
            
            # 각 리스트별로 분석 결과 수집 및 정렬
            for stock_list in all_stock_lists:
                # 최근 7일간 파일 기반 분석 결과 검색
                list_analyses = []
                for i in range(7):
                    search_date = analysis_date - timedelta(days=i)
                    temp_analyses = self._get_analyses_from_files(user, stock_list, search_date)
                    
                    if temp_analyses:
                        logger.info(f"리스트 {stock_list.name}의 분석 결과를 {search_date} 날짜에서 발견했습니다.")
                        list_analyses = temp_analyses
                        break  # 해당 리스트에서 분석 결과를 찾으면 다음 리스트로
                
                if list_analyses:
                    # 종목별 가격 변화율 추가
                    from routes.analysis_routes import get_ticker_price_change
                    for analysis in list_analyses:
                        analysis['price_change_rate'] = get_ticker_price_change(analysis['ticker'])
                        analysis['source_list'] = stock_list.name
                    
                    # 리스트 내에서 가격 변화율 기준으로 내림차순 정렬
                    list_analyses.sort(key=lambda x: x.get('price_change_rate', 0), reverse=True)
                    
                    # 리스트 요약 정보 추가
                    list_summaries.append({
                        'list_name': stock_list.name,
                        'stock_count': len(list_analyses),
                        'description': f"수익률 순 정렬 ({len(list_analyses)}개 종목)"
                    })
                    
                    # 전체 분석 결과에 추가
                    all_stock_analyses.extend(list_analyses)
            
            if not all_stock_analyses:
                logger.info(f"관리자 {user.id}의 모든 리스트에서 분석 결과를 찾을 수 없습니다.")
                return None
            
            # 관리자용 HTML 생성 (리스트별 정렬 정보 포함)
            html_content = self._create_admin_newsletter_html_by_lists(user, all_stock_analyses, list_summaries, analysis_date, subscription)
            text_content = self._create_admin_newsletter_text_by_lists(user, all_stock_analyses, list_summaries, analysis_date, subscription)
            
            return {
                'html': html_content,
                'text': text_content,
                'stock_count': len(all_stock_analyses),
                'list_count': len(list_summaries),
                'is_admin': True
            }
            
        except Exception as e:
            logger.error(f"관리자 뉴스레터 콘텐츠 생성 실패: {e}")
            return None
    
    def _create_newsletter_html(self, user, stock_analyses, analysis_date, subscription):
        """뉴스레터 HTML 생성"""
        template_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>주식 분석 뉴스레터</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #007bff; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; }
                .stock-item { border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 5px; }
                .stock-header { background-color: #f8f9fa; padding: 10px; margin: -15px -15px 15px -15px; border-radius: 5px 5px 0 0; }
                .ticker { font-weight: bold; color: #007bff; font-size: 18px; }
                .summary { margin: 15px 0; }
                .footer { background-color: #f8f9fa; padding: 20px; text-align: center; margin-top: 30px; }
                .btn { display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📈 주식 분석 뉴스레터</h1>
                    <p>{{ analysis_date.strftime('%Y년 %m월 %d일') }}</p>
                </div>
                
                <div class="content">
                    <p>안녕하세요, {{ user.get_full_name() }}님!</p>
                    <p>오늘의 주식 분석 결과를 전해드립니다.</p>
                    
                    <h2>📊 분석 종목 ({{ stock_analyses|length }}개)</h2>
                    
                    {% for analysis in stock_analyses %}
                    <div class="stock-item">
                        <div class="stock-header">
                            <span class="ticker">{{ analysis['ticker'] }}</span>
                            {% if analysis['name'] %}
                            <span style="color: #666;"> - {{ analysis['name'] }}</span>
                            {% endif %}
                        </div>
                        
                        {% if subscription.include_summary and analysis['summary'] %}
                        <div class="summary">
                            <h4>📋 핵심 요약</h4>
                            <p>{{ analysis['summary'] }}</p>
                        </div>
                        {% endif %}
                        
                        {% if subscription.include_charts and analysis['chart_path'] %}
                        <p><strong>📈 차트 분석:</strong> 상세 차트는 웹사이트에서 확인하세요.</p>
                        {% endif %}
                        
                        {% if subscription.include_technical_analysis %}
                        <p><strong>🔍 상세 분석:</strong> 
                            <a href="http://localhost:5000/view_chart/{{ analysis['ticker'] }}" target="_blank" class="btn">차트 & 분석 보기</a>
                        </p>
                        {% endif %}
                    </div>
                    {% endfor %}
                    
                    <div style="margin-top: 30px; padding: 20px; background-color: #e9ecef; border-radius: 5px;">
                        <h3>💡 투자 조언</h3>
                        <p>• 위 분석은 참고용이며, 투자 결정은 신중히 하시기 바랍니다.</p>
                        <p>• 시장 상황에 따라 결과가 달라질 수 있습니다.</p>
                        <p>• 분산 투자와 리스크 관리에 유의하세요.</p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>이 뉴스레터는 {{ user.email }}로 발송되었습니다.</p>
                    <p>구독 설정 변경은 <a href="{{ unsubscribe_url }}">여기</a>에서 가능합니다.</p>
                    <p>&copy; 2025 주식 분석 뉴스레터. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(template_content)
        
        # 구독 해지 토큰 생성 (필요한 경우)
        if not subscription.unsubscribe_token:
            subscription.generate_unsubscribe_token()
            db.session.commit()
        
        # 구독 해지 URL 생성
        from flask import url_for
        unsubscribe_url = url_for('newsletter.unsubscribe', token=subscription.unsubscribe_token, _external=True)
        
        return template.render(
            user=user,
            stock_analyses=stock_analyses,
            analysis_date=analysis_date,
            subscription=subscription,
            unsubscribe_url=unsubscribe_url
        )
    
    def _create_newsletter_text(self, user, stock_analyses, analysis_date, subscription):
        """뉴스레터 텍스트 버전 생성"""
        text_content = f"""
주식 분석 뉴스레터
{analysis_date.strftime('%Y년 %m월 %d일')}

안녕하세요, {user.get_full_name()}님!

오늘의 주식 분석 결과를 전해드립니다.

📊 분석 종목 ({len(stock_analyses)}개)
"""
        
        for analysis in stock_analyses:
            text_content += f"""
{analysis['ticker']} - {analysis['name'] or 'N/A'}
"""
            
            if subscription.include_summary and analysis['summary']:
                text_content += f"📋 핵심 요약: {analysis['summary']}\n"
            
            if subscription.include_charts and analysis['chart_path']:
                text_content += "📈 차트 분석: 상세 차트는 웹사이트에서 확인하세요.\n"
            
            if subscription.include_technical_analysis:
                text_content += f"🔍 상세 분석: http://localhost:5000/view_chart/{analysis['ticker']}\n"
            
            text_content += "\n"
        
        text_content += f"""
💡 투자 조언
• 위 분석은 참고용이며, 투자 결정은 신중히 하시기 바랍니다.
• 시장 상황에 따라 결과가 달라질 수 있습니다.
• 분산 투자와 리스크 관리에 유의하세요.

이 뉴스레터는 {user.email}로 발송되었습니다.
구독 설정 변경은 웹사이트에서 가능합니다.

© 2025 주식 분석 뉴스레터. All rights reserved.
"""
        
        return text_content
    
    def _create_admin_newsletter_html_by_lists(self, user, all_stock_analyses, list_summaries, analysis_date, subscription):
        """관리자용 리스트별 정렬 뉴스레터 HTML 생성"""
        template_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>통합 주식 분석 뉴스레터 - 리스트별 정렬</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 800px; margin: 0 auto; padding: 20px; }
                .header { background-color: #6f42c1; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; }
                .list-section { margin: 30px 0; border: 2px solid #6f42c1; border-radius: 10px; overflow: hidden; }
                .list-header { background-color: #6f42c1; color: white; padding: 15px; font-weight: bold; font-size: 18px; }
                .stock-item { border-bottom: 1px solid #ddd; padding: 15px; }
                .stock-item:last-child { border-bottom: none; }
                .stock-header { display: flex; align-items: center; margin-bottom: 10px; }
                .ticker { font-weight: bold; color: #6f42c1; font-size: 16px; }
                .price-change { font-weight: bold; margin-left: 15px; padding: 5px 10px; border-radius: 15px; }
                .price-up { background-color: #e74c3c; color: white; }
                .price-down { background-color: #3498db; color: white; }
                .price-neutral { background-color: #7f8c8d; color: white; }
                .summary { margin: 10px 0; background-color: #f8f9fa; padding: 10px; border-radius: 5px; }
                .footer { background-color: #f8f9fa; padding: 20px; text-align: center; margin-top: 30px; }
                .btn { display: inline-block; background-color: #6f42c1; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-size: 14px; }
                .admin-notice { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
                .stats { background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📈 통합 주식 분석 뉴스레터</h1>
                    <p>{{ analysis_date.strftime('%Y년 %m월 %d일') }} - 관리자용 (리스트별 정렬)</p>
                </div>
                
                <div class="content">
                    <div class="admin-notice">
                        <strong>👑 관리자 전용:</strong> 각 리스트별로 수익률 내림차순 정렬되어 표시됩니다. (중복 종목 포함)
                    </div>
                    
                    <div class="stats">
                        <h3>📊 통계 요약</h3>
                        <p>• 총 리스트 수: {{ list_summaries|length }}개</p>
                        <p>• 총 종목 수: {{ all_stock_analyses|length }}개 (중복 포함)</p>
                        <p>• 리스트별 수익률 내림차순 정렬</p>
                    </div>
                    
                    <p>안녕하세요, {{ user.get_full_name() }}님!</p>
                    <p>모든 종목 리스트의 분석 결과를 리스트별로 정렬하여 전해드립니다.</p>
                    
                    {% set current_list = '' %}
                    {% for analysis in all_stock_analyses %}
                        {% if analysis['source_list'] != current_list %}
                            {% if current_list != '' %}
                            </div>
                            {% endif %}
                            {% set current_list = analysis['source_list'] %}
                            <div class="list-section">
                                <div class="list-header">
                                    📋 {{ analysis['source_list'] }}
                                    {% for summary in list_summaries %}
                                        {% if summary['list_name'] == analysis['source_list'] %}
                                            ({{ summary['stock_count'] }}개 종목 - 수익률 순)
                                        {% endif %}
                                    {% endfor %}
                                </div>
                        {% endif %}
                        
                        <div class="stock-item">
                            <div class="stock-header">
                                <span class="ticker">{{ analysis['ticker'] }}</span>
                                {% if analysis['name'] %}
                                <span style="color: #666; margin-left: 10px;"> - {{ analysis['name'] }}</span>
                                {% endif %}
                                {% if analysis['price_change_rate'] %}
                                {% set rate = analysis['price_change_rate'] %}
                                <span class="price-change {% if rate > 0 %}price-up{% elif rate < 0 %}price-down{% else %}price-neutral{% endif %}">
                                    {% if rate > 0 %}+{% endif %}{{ rate }}%
                                </span>
                                {% endif %}
                            </div>
                            
                            {% if subscription.include_summary and analysis['summary'] %}
                            <div class="summary">
                                <strong>📋 핵심 요약:</strong> {{ analysis['summary'] }}
                            </div>
                            {% endif %}
                            
                            {% if subscription.include_charts and analysis['chart_path'] %}
                            <p><strong>📈 차트 분석:</strong> 상세 차트는 웹사이트에서 확인하세요.</p>
                            {% endif %}
                            
                            {% if subscription.include_technical_analysis %}
                            <p><strong>🔍 상세 분석:</strong> 
                                <a href="http://localhost:5000/view_chart/{{ analysis['ticker'] }}" target="_blank" class="btn">차트 & 분석 보기</a>
                            </p>
                            {% endif %}
                        </div>
                    {% endfor %}
                    </div> <!-- 마지막 리스트 섹션 종료 -->
                    
                    <div style="margin-top: 30px; padding: 20px; background-color: #e9ecef; border-radius: 5px;">
                        <h3>💡 투자 조언</h3>
                        <p>• 위 분석은 참고용이며, 투자 결정은 신중히 하시기 바랍니다.</p>
                        <p>• 시장 상황에 따라 결과가 달라질 수 있습니다.</p>
                        <p>• 분산 투자와 리스크 관리에 유의하세요.</p>
                        <p>• 각 리스트별로 수익률 순 정렬되어 있어 포트폴리오 구성에 참고하세요.</p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>이 통합 뉴스레터는 {{ user.email }}로 발송되었습니다.</p>
                    <p>구독 설정 변경은 <a href="{{ unsubscribe_url }}">여기</a>에서 가능합니다.</p>
                    <p>&copy; 2025 주식 분석 뉴스레터. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(template_content)
        
        # 구독 해지 토큰 생성 (필요한 경우)
        if not subscription.unsubscribe_token:
            subscription.generate_unsubscribe_token()
            db.session.commit()
        
        # 구독 해지 URL 생성
        from flask import url_for
        unsubscribe_url = url_for('newsletter.unsubscribe', token=subscription.unsubscribe_token, _external=True)
        
        return template.render(
            user=user,
            all_stock_analyses=all_stock_analyses,
            list_summaries=list_summaries,
            analysis_date=analysis_date,
            subscription=subscription,
            unsubscribe_url=unsubscribe_url
        )
    
    def _create_admin_newsletter_html(self, user, stock_analyses, analysis_date, subscription):
        """관리자용 뉴스레터 HTML 생성 (리스트 정보 포함)"""
        template_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>통합 주식 분석 뉴스레터</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #6f42c1; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; }
                .stock-item { border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 5px; }
                .stock-header { background-color: #f8f9fa; padding: 10px; margin: -15px -15px 15px -15px; border-radius: 5px 5px 0 0; }
                .ticker { font-weight: bold; color: #6f42c1; font-size: 18px; }
                .price-change { font-weight: bold; margin-left: 10px; }
                .price-up { color: #e74c3c; }
                .price-down { color: #3498db; }
                .price-neutral { color: #7f8c8d; }
                .source-list { font-size: 12px; color: #6c757d; background-color: #e9ecef; padding: 2px 6px; border-radius: 3px; margin-left: 10px; }
                .summary { margin: 15px 0; }
                .footer { background-color: #f8f9fa; padding: 20px; text-align: center; margin-top: 30px; }
                .btn { display: inline-block; background-color: #6f42c1; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
                .admin-notice { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📈 통합 주식 분석 뉴스레터</h1>
                    <p>{{ analysis_date.strftime('%Y년 %m월 %d일') }} - 관리자용</p>
                </div>
                
                <div class="content">
                    <div class="admin-notice">
                        <strong>👑 관리자 전용:</strong> 모든 종목 리스트의 중복 제거된 종목들이 가격 변화율 순으로 정렬되어 표시됩니다.
                    </div>
                    
                    <p>안녕하세요, {{ user.get_full_name() }}님!</p>
                    <p>전체 종목 리스트의 통합 분석 결과를 전해드립니다.</p>
                    
                    <h2>📊 분석 종목 ({{ stock_analyses|length }}개, 중복 제거됨)</h2>
                    
                    {% for analysis in stock_analyses %}
                    <div class="stock-item">
                        <div class="stock-header">
                            <span class="ticker">{{ analysis['ticker'] }}</span>
                            {% if analysis['name'] %}
                            <span style="color: #666;"> - {{ analysis['name'] }}</span>
                            {% endif %}
                            {% if analysis['price_change_rate'] %}
                            {% set rate = analysis['price_change_rate'] %}
                            <span class="price-change {% if rate > 0 %}price-up{% elif rate < 0 %}price-down{% else %}price-neutral{% endif %}">
                                {% if rate > 0 %}+{% endif %}{{ rate }}%
                            </span>
                            {% endif %}
                            <span class="source-list">{{ analysis['source_list'] }}</span>
                        </div>
                        
                        {% if subscription.include_summary and analysis['summary'] %}
                        <div class="summary">
                            <h4>📋 핵심 요약</h4>
                            <p>{{ analysis['summary'] }}</p>
                        </div>
                        {% endif %}
                        
                        {% if subscription.include_charts and analysis['chart_path'] %}
                        <p><strong>📈 차트 분석:</strong> 상세 차트는 웹사이트에서 확인하세요.</p>
                        {% endif %}
                        
                        {% if subscription.include_technical_analysis %}
                        <p><strong>🔍 상세 분석:</strong> 
                            <a href="http://localhost:5000/view_chart/{{ analysis['ticker'] }}" target="_blank" class="btn">차트 & 분석 보기</a>
                        </p>
                        {% endif %}
                    </div>
                    {% endfor %}
                    
                    <div style="margin-top: 30px; padding: 20px; background-color: #e9ecef; border-radius: 5px;">
                        <h3>💡 투자 조언</h3>
                        <p>• 위 분석은 참고용이며, 투자 결정은 신중히 하시기 바랍니다.</p>
                        <p>• 시장 상황에 따라 결과가 달라질 수 있습니다.</p>
                        <p>• 분산 투자와 리스크 관리에 유의하세요.</p>
                        <p>• 종목들은 가격 변화율 기준으로 정렬되어 있습니다.</p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>이 통합 뉴스레터는 {{ user.email }}로 발송되었습니다.</p>
                    <p>구독 설정 변경은 <a href="{{ unsubscribe_url }}">여기</a>에서 가능합니다.</p>
                    <p>&copy; 2025 주식 분석 뉴스레터. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(template_content)
        
        # 구독 해지 토큰 생성 (필요한 경우)
        if not subscription.unsubscribe_token:
            subscription.generate_unsubscribe_token()
            db.session.commit()
        
        # 구독 해지 URL 생성
        from flask import url_for
        unsubscribe_url = url_for('newsletter.unsubscribe', token=subscription.unsubscribe_token, _external=True)
        
        return template.render(
            user=user,
            stock_analyses=stock_analyses,
            analysis_date=analysis_date,
            subscription=subscription,
            unsubscribe_url=unsubscribe_url
        )
    
    def _create_admin_newsletter_text_by_lists(self, user, all_stock_analyses, list_summaries, analysis_date, subscription):
        """관리자용 리스트별 정렬 뉴스레터 텍스트 생성"""
        text_content = f"""
통합 주식 분석 뉴스레터 - 리스트별 정렬
{analysis_date.strftime('%Y년 %m월 %d일')} - 관리자용

안녕하세요, {user.get_full_name()}님!

👑 관리자 전용: 각 리스트별로 수익률 내림차순 정렬되어 표시됩니다. (중복 종목 포함)

📊 통계 요약
• 총 리스트 수: {len(list_summaries)}개
• 총 종목 수: {len(all_stock_analyses)}개 (중복 포함)  
• 리스트별 수익률 내림차순 정렬

모든 종목 리스트의 분석 결과를 리스트별로 정렬하여 전해드립니다.

"""
        
        current_list = ''
        for analysis in all_stock_analyses:
            # 새로운 리스트 섹션 시작
            if analysis['source_list'] != current_list:
                current_list = analysis['source_list']
                # 해당 리스트의 종목 수 찾기
                stock_count = 0
                for summary in list_summaries:
                    if summary['list_name'] == current_list:
                        stock_count = summary['stock_count']
                        break
                
                text_content += f"""
════════════════════════════════════════
📋 {current_list} ({stock_count}개 종목 - 수익률 순)
════════════════════════════════════════

"""
            
            # 종목 정보
            rate = analysis.get('price_change_rate', 0)
            rate_str = f" ({'+' if rate > 0 else ''}{rate}%)" if rate != 0 else " (0%)"
            
            text_content += f"{analysis['ticker']} - {analysis['name'] or 'N/A'}{rate_str}\n"
            
            if subscription.include_summary and analysis['summary']:
                text_content += f"📋 핵심 요약: {analysis['summary']}\n"
            
            if subscription.include_charts and analysis['chart_path']:
                text_content += "📈 차트 분석: 상세 차트는 웹사이트에서 확인하세요.\n"
            
            if subscription.include_technical_analysis:
                text_content += f"🔍 상세 분석: http://localhost:5000/view_chart/{analysis['ticker']}\n"
            
            text_content += "\n"
        
        text_content += f"""
════════════════════════════════════════

💡 투자 조언
• 위 분석은 참고용이며, 투자 결정은 신중히 하시기 바랍니다.
• 시장 상황에 따라 결과가 달라질 수 있습니다.
• 분산 투자와 리스크 관리에 유의하세요.
• 각 리스트별로 수익률 순 정렬되어 있어 포트폴리오 구성에 참고하세요.

이 통합 뉴스레터는 {user.email}로 발송되었습니다.
구독 설정 변경은 웹사이트에서 가능합니다.

© 2025 주식 분석 뉴스레터. All rights reserved.
"""
        
        return text_content
    
    def _create_admin_newsletter_text(self, user, stock_analyses, analysis_date, subscription):
        """관리자용 뉴스레터 텍스트 버전 생성"""
        text_content = f"""
통합 주식 분석 뉴스레터 - 관리자용
{analysis_date.strftime('%Y년 %m월 %d일')}

안녕하세요, {user.get_full_name()}님!

전체 종목 리스트의 통합 분석 결과를 전해드립니다.
모든 종목 리스트의 중복 제거된 종목들이 가격 변화율 순으로 정렬되어 있습니다.

📊 분석 종목 ({len(stock_analyses)}개, 중복 제거됨)
"""
        
        for analysis in stock_analyses:
            rate = analysis.get('price_change_rate', 0)
            rate_str = f" ({'+' if rate > 0 else ''}{rate}%)" if rate != 0 else ""
            source_list = f" [출처: {analysis.get('source_list', 'N/A')}]"
            
            text_content += f"""
{analysis['ticker']} - {analysis['name'] or 'N/A'}{rate_str}{source_list}
"""
            
            if subscription.include_summary and analysis['summary']:
                text_content += f"📋 핵심 요약: {analysis['summary']}\n"
            
            if subscription.include_charts and analysis['chart_path']:
                text_content += "📈 차트 분석: 상세 차트는 웹사이트에서 확인하세요.\n"
            
            if subscription.include_technical_analysis:
                text_content += f"🔍 상세 분석: http://localhost:5000/view_chart/{analysis['ticker']}\n"
            
            text_content += "\n"
        
        text_content += f"""
💡 투자 조언
• 위 분석은 참고용이며, 투자 결정은 신중히 하시기 바랍니다.
• 시장 상황에 따라 결과가 달라질 수 있습니다.
• 분산 투자와 리스크 관리에 유의하세요.
• 종목들은 가격 변화율 기준으로 정렬되어 있습니다.

이 통합 뉴스레터는 {user.email}로 발송되었습니다.
구독 설정 변경은 웹사이트에서 가능합니다.

© 2025 주식 분석 뉴스레터. All rights reserved.
"""
        
        return text_content
    
    def _get_analyses_from_files(self, user, stock_list, analysis_date):
        """파일 기반 분석 결과 수집"""
        import json
        import os
        from datetime import datetime
        from models import _extract_summary_from_analysis, get_analysis_summary_path
        
        stock_analyses = []
        
        try:
            # 분석 요약 파일 경로
            summary_file_path = get_analysis_summary_path(stock_list.name)
            
            if not os.path.exists(summary_file_path):
                logger.info(f"분석 요약 파일이 없습니다: {summary_file_path}")
                return []
            
            # 분석 요약 파일 읽기
            with open(summary_file_path, 'r', encoding='utf-8') as f:
                summaries = json.load(f)
            
            # 날짜별 분석 결과 폴더
            analysis_date_str = analysis_date.strftime('%Y%m%d')
            analysis_dir = f"static/analysis/{analysis_date_str}"
            chart_dir = f"static/charts/{analysis_date_str}"
            
            for stock in stock_list.stocks:
                ticker = stock.ticker
                
                # 요약 정보가 있는지 확인
                if ticker in summaries:
                    summary_data = summaries[ticker]
                    summary_text = summary_data.get('gemini_summary', '')
                    
                    # 분석 파일 경로
                    analysis_file = f"{ticker}_{analysis_date_str}.html"
                    analysis_path = os.path.join(analysis_dir, analysis_file)
                    
                    # 차트 파일 경로 (일봉 차트 사용)
                    chart_file = f"{ticker}_daily_{analysis_date_str}.png"
                    chart_path = os.path.join(chart_dir, chart_file)
                    
                    # 실제 파일 존재 여부 확인
                    analysis_exists = os.path.exists(analysis_path)
                    chart_exists = os.path.exists(chart_path)
                    
                    if analysis_exists or summary_text:
                        # 요약 추출
                        extracted_summary = _extract_summary_from_analysis(summary_text, 3)
                        
                        # 웹 URL로 변환
                        analysis_url = None
                        chart_url = None
                        
                        if analysis_exists:
                            # static 폴더 기준 상대 경로로 변환
                            relative_analysis_path = os.path.relpath(analysis_path, 'static').replace(os.sep, '/')
                            analysis_url = f"/static/{relative_analysis_path}"
                        
                        if chart_exists:
                            # static 폴더 기준 상대 경로로 변환
                            relative_chart_path = os.path.relpath(chart_path, 'static').replace(os.sep, '/')
                            chart_url = f"/static/{relative_chart_path}"
                        
                        stock_analyses.append({
                            'ticker': ticker,
                            'name': stock.name,
                            'summary': extracted_summary,
                            'analysis_path': analysis_url,
                            'chart_path': chart_url
                        })
                        
                        logger.info(f"파일 기반 분석 결과 발견: {ticker}")
            
            logger.info(f"파일 기반에서 {len(stock_analyses)}개 종목의 분석 결과 수집 완료")
            return stock_analyses
            
        except Exception as e:
            logger.error(f"파일 기반 분석 결과 수집 실패: {e}")
            return []
    
    def send_daily_newsletter(self, user_id):
        """일일 뉴스레터 발송"""
        try:
            user = User.query.get(user_id)
            if not user:
                logger.error(f"사용자를 찾을 수 없습니다: {user_id}")
                return False
            
            # 사용자의 기본 종목 리스트 가져오기
            stock_list = StockList.query.filter_by(user_id=user.id, is_default=True).first()
            if not stock_list:
                logger.info(f"사용자 {user_id}의 기본 종목 리스트가 없습니다.")
                return False
            
            # 뉴스레터 콘텐츠 생성
            content = self.generate_newsletter_content(user, stock_list)
            if not content:
                logger.info(f"사용자 {user_id}의 뉴스레터 콘텐츠를 생성할 수 없습니다.")
                return False
            
            # 이메일 발송
            subject = f"📈 주식 분석 뉴스레터 - {datetime.now().strftime('%Y년 %m월 %d일')}"
            success, result = email_service.send_newsletter(
                user, subject, content['html'], content['text']
            )
            
            if success:
                logger.info(f"일일 뉴스레터 발송 성공: {user.email}")
            else:
                logger.error(f"일일 뉴스레터 발송 실패: {user.email} - {result}")
            
            return success
            
        except Exception as e:
            logger.error(f"일일 뉴스레터 발송 중 오류: {e}")
            return False
    
    def send_weekly_newsletter(self, user_id):
        """주간 뉴스레터 발송"""
        try:
            user = User.query.get(user_id)
            if not user:
                logger.error(f"사용자를 찾을 수 없습니다: {user_id}")
                return False
            
            # 사용자의 기본 종목 리스트 가져오기
            stock_list = StockList.query.filter_by(user_id=user.id, is_default=True).first()
            if not stock_list:
                logger.info(f"사용자 {user_id}의 기본 종목 리스트가 없습니다.")
                return False
            
            # 뉴스레터 콘텐츠 생성
            content = self.generate_newsletter_content(user, stock_list)
            if not content:
                logger.info(f"사용자 {user_id}의 뉴스레터 콘텐츠를 생성할 수 없습니다.")
                return False
            
            # 이메일 발송
            subject = f"📈 주간 주식 분석 뉴스레터 - {datetime.now().strftime('%Y년 %m월 %d일')}"
            success, result = email_service.send_newsletter(
                user, subject, content['html'], content['text']
            )
            
            if success:
                logger.info(f"주간 뉴스레터 발송 성공: {user.email}")
            else:
                logger.error(f"주간 뉴스레터 발송 실패: {user.email} - {result}")
            
            return success
            
        except Exception as e:
            logger.error(f"주간 뉴스레터 발송 중 오류: {e}")
            return False
    
    def send_monthly_newsletter(self, user_id):
        """월간 뉴스레터 발송"""
        try:
            user = User.query.get(user_id)
            if not user:
                logger.error(f"사용자를 찾을 수 없습니다: {user_id}")
                return False
            
            # 사용자의 기본 종목 리스트 가져오기
            stock_list = StockList.query.filter_by(user_id=user.id, is_default=True).first()
            if not stock_list:
                logger.info(f"사용자 {user_id}의 기본 종목 리스트가 없습니다.")
                return False
            
            # 뉴스레터 콘텐츠 생성
            content = self.generate_newsletter_content(user, stock_list)
            if not content:
                logger.info(f"사용자 {user_id}의 뉴스레터 콘텐츠를 생성할 수 없습니다.")
                return False
            
            # 이메일 발송
            subject = f"📈 월간 주식 분석 뉴스레터 - {datetime.now().strftime('%Y년 %m월')}"
            success, result = email_service.send_newsletter(
                user, subject, content['html'], content['text']
            )
            
            if success:
                logger.info(f"월간 뉴스레터 발송 성공: {user.email}")
            else:
                logger.error(f"월간 뉴스레터 발송 실패: {user.email} - {result}")
            
            return success
            
        except Exception as e:
            logger.error(f"월간 뉴스레터 발송 중 오류: {e}")
            return False

    def generate_multi_list_newsletter_content(self, user, stock_lists=None, analysis_date=None):
        """여러 종목 리스트의 분석 결과를 통합한 뉴스레터 콘텐츠 생성"""
        try:
            if not analysis_date:
                analysis_date = datetime.now().date()
            
            # 사용자의 구독 설정 가져오기
            subscription = NewsletterSubscription.query.filter_by(user_id=user.id).first()
            if not subscription or not subscription.is_active:
                logger.info(f"사용자 {user.id}의 뉴스레터 구독이 비활성화되어 있습니다.")
                return None
            
            # stock_lists가 지정되지 않으면 사용자의 모든 리스트 사용
            if not stock_lists:
                stock_lists = StockList.query.filter_by(user_id=user.id).all()
            
            if not stock_lists:
                logger.info(f"사용자 {user.id}의 종목 리스트가 없습니다.")
                return None
            
            # 모든 리스트별로 분석 결과 수집
            all_stock_analyses = []
            list_summaries = []  # 리스트별 요약 정보
            
            for stock_list in stock_lists:
                stock_analyses = []
                
                # 1. 먼저 AnalysisHistory 테이블에서 검색
                for stock in stock_list.stocks:
                    analysis = AnalysisHistory.query.filter_by(
                        user_id=user.id,
                        ticker=stock.ticker,
                        analysis_date=analysis_date,
                        status='completed'
                    ).first()
                    
                    if analysis:
                        stock_analyses.append({
                            'ticker': stock.ticker,
                            'name': stock.name,
                            'summary': analysis.summary,
                            'analysis_path': analysis.analysis_path,
                            'chart_path': analysis.chart_path,
                            'list_name': stock_list.name
                        })
                
                # 2. AnalysisHistory에 결과가 없으면 파일 기반에서 검색 (최근 7일간)
                if not stock_analyses:
                    from datetime import timedelta
                    
                    # 오늘부터 최근 7일간 검색
                    for i in range(7):
                        search_date = analysis_date - timedelta(days=i)
                        file_analyses = self._get_analyses_from_files(user, stock_list, search_date)
                        if file_analyses:
                            # 리스트 이름 추가
                            for analysis in file_analyses:
                                analysis['list_name'] = stock_list.name
                            stock_analyses = file_analyses
                            logger.info(f"리스트 '{stock_list.name}'의 분석 결과를 {search_date} 날짜에서 발견했습니다.")
                            break
                
                if stock_analyses:
                    list_summaries.append({
                        'list_name': stock_list.name,
                        'stock_count': len(stock_analyses),
                        'description': stock_list.description or ''
                    })
                    all_stock_analyses.extend(stock_analyses)
            
            if not all_stock_analyses:
                logger.info(f"사용자 {user.id}의 모든 리스트에서 분석 결과를 찾을 수 없습니다.")
                return None
            
            # 중복 종목 제거 (같은 종목이 여러 리스트에 있을 수 있음)
            unique_analyses = {}
            for analysis in all_stock_analyses:
                ticker = analysis['ticker']
                if ticker not in unique_analyses:
                    unique_analyses[ticker] = analysis
                else:
                    # 여러 리스트에 포함된 종목의 경우 리스트 이름을 병합
                    existing_lists = unique_analyses[ticker]['list_name']
                    new_list = analysis['list_name']
                    if new_list not in existing_lists:
                        unique_analyses[ticker]['list_name'] = f"{existing_lists}, {new_list}"
            
            final_stock_analyses = list(unique_analyses.values())
            
            # 뉴스레터 HTML 생성 (멀티 리스트 버전)
            html_content = self._create_multi_list_newsletter_html(user, final_stock_analyses, list_summaries, analysis_date, subscription)
            text_content = self._create_multi_list_newsletter_text(user, final_stock_analyses, list_summaries, analysis_date, subscription)
            
            return {
                'html': html_content,
                'text': text_content,
                'stock_count': len(final_stock_analyses),
                'list_count': len(list_summaries),
                'list_summaries': list_summaries
            }
            
        except Exception as e:
            logger.error(f"멀티 리스트 뉴스레터 콘텐츠 생성 실패: {e}")
            return None

    def _create_multi_list_newsletter_html(self, user, stock_analyses, list_summaries, analysis_date, subscription):
        """멀티 리스트 뉴스레터 HTML 생성"""
        template_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>주식 분석 뉴스레터 - 통합 리포트</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #007bff; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; }
                .stock-item { border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 5px; }
                .stock-header { background-color: #f8f9fa; padding: 10px; margin: -15px -15px 15px -15px; border-radius: 5px 5px 0 0; }
                .ticker { font-weight: bold; color: #007bff; font-size: 18px; }
                .list-badge { background-color: #6c757d; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px; }
                .summary { margin: 15px 0; }
                .footer { background-color: #f8f9fa; padding: 20px; text-align: center; margin-top: 30px; }
                .btn { display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
                .list-summary { background-color: #e9ecef; padding: 15px; margin: 15px 0; border-radius: 5px; }
                .list-summary h4 { margin: 0 0 10px 0; color: #495057; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📈 주식 분석 뉴스레터 - 통합 리포트</h1>
                    <p>{{ analysis_date.strftime('%Y년 %m월 %d일') }}</p>
                </div>
                
                <div class="content">
                    <p>안녕하세요, {{ user.get_full_name() }}님!</p>
                    <p>{{ list_summaries|length }}개 리스트의 종목 분석 결과를 통합하여 전해드립니다.</p>
                    
                    <h2>📊 분석 대상 리스트</h2>
                    {% for list_summary in list_summaries %}
                    <div class="list-summary">
                        <h4>📋 {{ list_summary.list_name }} ({{ list_summary.stock_count }}개 종목)</h4>
                        {% if list_summary.description %}
                        <p>{{ list_summary.description }}</p>
                        {% endif %}
                    </div>
                    {% endfor %}
                    
                    <h2>📈 분석 종목 (총 {{ stock_analyses|length }}개)</h2>
                    
                    {% for analysis in stock_analyses %}
                    <div class="stock-item">
                        <div class="stock-header">
                            <span class="ticker">{{ analysis['ticker'] }}</span>
                            {% if analysis['name'] %}
                            <span style="color: #666;"> - {{ analysis['name'] }}</span>
                            {% endif %}
                            <span class="list-badge">{{ analysis['list_name'] }}</span>
                        </div>
                        
                        {% if subscription.include_summary and analysis['summary'] %}
                        <div class="summary">
                            <h4>📋 핵심 요약</h4>
                            <p>{{ analysis['summary'] }}</p>
                        </div>
                        {% endif %}
                        
                        {% if subscription.include_charts and analysis['chart_path'] %}
                        <p><strong>📈 차트 분석:</strong> 상세 차트는 웹사이트에서 확인하세요.</p>
                        {% endif %}
                        
                        {% if subscription.include_technical_analysis %}
                        <p><strong>🔍 상세 분석:</strong> 
                            <a href="http://localhost:5000/view_chart/{{ analysis['ticker'] }}" target="_blank" class="btn">차트 & 분석 보기</a>
                        </p>
                        {% endif %}
                    </div>
                    {% endfor %}
                    
                    <div style="margin-top: 30px; padding: 20px; background-color: #e9ecef; border-radius: 5px;">
                        <h3>💡 투자 조언</h3>
                        <p>• 위 분석은 참고용이며, 투자 결정은 신중히 하시기 바랍니다.</p>
                        <p>• 시장 상황에 따라 결과가 달라질 수 있습니다.</p>
                        <p>• 분산 투자와 리스크 관리에 유의하세요.</p>
                        <p>• 여러 리스트의 종목이 포함되어 있으니 포트폴리오 구성에 참고하세요.</p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>이 뉴스레터는 {{ user.email }}로 발송되었습니다.</p>
                    <p>구독 설정 변경은 <a href="{{ unsubscribe_url }}">여기</a>에서 가능합니다.</p>
                    <p>&copy; 2025 주식 분석 뉴스레터. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(template_content)
        
        # 구독 해지 토큰 생성 (필요한 경우)
        if not subscription.unsubscribe_token:
            subscription.generate_unsubscribe_token()
            db.session.commit()
        
        # 구독 해지 URL 생성
        from flask import url_for
        unsubscribe_url = url_for('newsletter.unsubscribe', token=subscription.unsubscribe_token, _external=True)
        
        return template.render(
            user=user,
            stock_analyses=stock_analyses,
            list_summaries=list_summaries,
            analysis_date=analysis_date,
            subscription=subscription,
            unsubscribe_url=unsubscribe_url
        )
    
    def _create_multi_list_newsletter_text(self, user, stock_analyses, list_summaries, analysis_date, subscription):
        """멀티 리스트 뉴스레터 텍스트 버전 생성"""
        text_content = f"""
주식 분석 뉴스레터 - 통합 리포트
{analysis_date.strftime('%Y년 %m월 %d일')}

안녕하세요, {user.get_full_name()}님!

{len(list_summaries)}개 리스트의 종목 분석 결과를 통합하여 전해드립니다.

📊 분석 대상 리스트
"""
        
        for list_summary in list_summaries:
            text_content += f"""
📋 {list_summary['list_name']} ({list_summary['stock_count']}개 종목)
{list_summary['description'] or ''}
"""
        
        text_content += f"""

📈 분석 종목 (총 {len(stock_analyses)}개)
"""
        
        for analysis in stock_analyses:
            text_content += f"""
{analysis['ticker']} - {analysis['name'] or 'N/A'} [{analysis['list_name']}]
"""
            
            if subscription.include_summary and analysis['summary']:
                text_content += f"📋 핵심 요약: {analysis['summary']}\n"
            
            if subscription.include_charts and analysis['chart_path']:
                text_content += "📈 차트 분석: 상세 차트는 웹사이트에서 확인하세요.\n"
            
            if subscription.include_technical_analysis:
                text_content += f"🔍 상세 분석: http://localhost:5000/view_chart/{analysis['ticker']}\n"
            
            text_content += "\n"
        
        text_content += """
💡 투자 조언
• 위 분석은 참고용이며, 투자 결정은 신중히 하시기 바랍니다.
• 시장 상황에 따라 결과가 달라질 수 있습니다.
• 분산 투자와 리스크 관리에 유의하세요.
• 여러 리스트의 종목이 포함되어 있으니 포트폴리오 구성에 참고하세요.

---
이 뉴스레터는 {user.email}로 발송되었습니다.
구독 해지를 원하시면 구독 설정에서 변경해주세요.

© 2025 주식 분석 뉴스레터. All rights reserved.
"""
        
        return text_content

# 전역 뉴스레터 서비스 인스턴스
newsletter_service = NewsletterService() 