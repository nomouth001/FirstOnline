#!/usr/bin/env python3
from app import app
from models import User, StockList, Stock, db
from sqlalchemy.orm import joinedload
from flask import render_template_string

def test_template_render():
    """템플릿 렌더링 직접 테스트"""
    print("🔍 템플릿 렌더링 테스트")
    
    with app.app_context():
        # 관리자 계정 조회
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("❌ 관리자 계정을 찾을 수 없습니다.")
            return
            
        print(f"👤 관리자 계정: {admin.username} (ID: {admin.id})")
        
        # 주식 리스트 조회 (eager loading 사용)
        stock_lists = StockList.query.options(joinedload(StockList.stocks)).filter_by(user_id=admin.id).all()
        print(f"📋 조회된 리스트 수: {len(stock_lists)}")
        
        # 템플릿 조각 테스트
        template_test = """
        <h3>내 종목 리스트 ({{ stock_lists|length }}개)</h3>
        {% for stock_list in stock_lists %}
            <div>
                <h4>{{ stock_list.name }}</h4>
                <p>종목 수: {{ stock_list.stocks|length }}개</p>
                <p>생성일: {{ stock_list.created_at.strftime('%Y-%m-%d %H:%M') }}</p>
                {% if stock_list.stocks %}
                    <ul>
                    {% for stock in stock_list.stocks %}
                        <li>{{ stock.ticker }}: {{ stock.name }}</li>
                    {% endfor %}
                    </ul>
                {% endif %}
            </div>
        {% endfor %}
        """
        
        try:
            rendered = render_template_string(template_test, stock_lists=stock_lists)
            print("\n✅ 템플릿 렌더링 성공:")
            print(rendered)
            
        except Exception as e:
            print(f"\n❌ 템플릿 렌더링 오류: {e}")
            import traceback
            traceback.print_exc()
        
        # 각 리스트 상세 정보 출력
        print("\n📊 리스트 상세 정보:")
        for stock_list in stock_lists:
            print(f"\n리스트: {stock_list.name}")
            print(f"  ID: {stock_list.id}")
            print(f"  사용자 ID: {stock_list.user_id}")
            print(f"  종목 수: {len(stock_list.stocks)}")
            print(f"  생성일: {stock_list.created_at}")
            print(f"  공개 여부: {stock_list.is_public}")
            print(f"  기본 여부: {stock_list.is_default}")
            
            for stock in stock_list.stocks:
                print(f"    종목: {stock.ticker} - {stock.name}")

if __name__ == "__main__":
    test_template_render() 