import logging
import yfinance as yf
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, StockList, Stock
from forms import StockListForm, AddStockForm
from datetime import datetime
import os
import json

user_stock_bp = Blueprint('user_stock', __name__)
logger = logging.getLogger(__name__)

@user_stock_bp.route('/dashboard')
@login_required
def dashboard():
    """사용자 대시보드"""
    stock_lists = StockList.query.filter_by(user_id=current_user.id).all()
    return render_template('user/dashboard.html', stock_lists=stock_lists)

@user_stock_bp.route('/stock-lists')
@login_required
def stock_lists():
    """사용자의 종목 리스트 목록"""
    stock_lists = StockList.query.filter_by(user_id=current_user.id).all()
    return render_template('user/stock_lists.html', stock_lists=stock_lists)

@user_stock_bp.route('/stock-lists/create', methods=['GET', 'POST'])
@login_required
def create_stock_list():
    """새 종목 리스트 생성"""
    # 일반 사용자는 추가 리스트 생성 금지
    if not current_user.is_administrator():
        flash('일반 사용자는 기본 관심종목 외에 추가 리스트를 생성할 수 없습니다.', 'error')
        return redirect(url_for('user_stock.stock_lists'))
    
    form = StockListForm(user_id=current_user.id)
    if form.validate_on_submit():
        stock_list = StockList(
            name=form.name.data,
            description=form.description.data,
            is_public=form.is_public.data,
            user_id=current_user.id
        )
        db.session.add(stock_list)
        db.session.commit()
        
        logger.info(f"새 종목 리스트 생성: {current_user.username} - {stock_list.name}")
        flash('종목 리스트가 생성되었습니다.', 'success')
        return redirect(url_for('user_stock.stock_lists'))
    
    return render_template('user/create_stock_list.html', form=form)

@user_stock_bp.route('/stock-lists/<int:list_id>')
@login_required
def view_stock_list(list_id):
    """종목 리스트 상세 보기"""
    stock_list = StockList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    stocks = Stock.query.filter_by(stock_list_id=list_id).all()
    
    # 각 종목의 파일 상태 정보 추가
    from utils.file_manager import get_stock_file_status
    stocks_with_status = []
    for stock in stocks:
        try:
            file_status = get_stock_file_status(stock.ticker)
            stock_data = {
                'stock': stock,
                'file_status': file_status
            }
            stocks_with_status.append(stock_data)
        except Exception as e:
            logger.error(f"Error getting file status for {stock.ticker}: {e}")
            # 오류 발생 시 기본값으로 설정
            stock_data = {
                'stock': stock,
                'file_status': {
                    'chart': {'exists': False, 'formatted_time': 'N/A', 'button_status': 'normal'},
                    'analysis': {'exists': False, 'formatted_time': 'N/A', 'button_status': 'normal'},
                    'is_us_stock': not stock.ticker.isdigit()
                }
            }
            stocks_with_status.append(stock_data)
    
    return render_template('user/view_stock_list.html', 
                          stock_list=stock_list, 
                          stocks=stocks,
                          stocks_with_status=stocks_with_status)

@user_stock_bp.route('/stock-lists/<int:list_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_stock_list(list_id):
    """종목 리스트 수정"""
    stock_list = StockList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    form = StockListForm(user_id=current_user.id, list_id=list_id)
    
    if form.validate_on_submit():
        stock_list.name = form.name.data
        stock_list.description = form.description.data
        stock_list.is_public = form.is_public.data
        
        db.session.commit()
        logger.info(f"종목 리스트 수정: {current_user.username} - {stock_list.name}")
        flash('종목 리스트가 수정되었습니다.', 'success')
        return redirect(url_for('user_stock.view_stock_list', list_id=list_id))
    elif request.method == 'GET':
        form.name.data = stock_list.name
        form.description.data = stock_list.description
        form.is_public.data = stock_list.is_public
    
    return render_template('user/edit_stock_list.html', form=form, stock_list=stock_list)

@user_stock_bp.route('/stock-lists/<int:list_id>/delete', methods=['POST'])
@login_required
def delete_stock_list(list_id):
    """종목 리스트 삭제"""
    stock_list = StockList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    
    # 기본 리스트도 삭제 가능하게 변경
    # 단, 마지막 리스트인 경우에는 삭제 방지
    user_lists_count = StockList.query.filter_by(user_id=current_user.id).count()
    if user_lists_count <= 1:
        flash('최소 하나의 리스트는 보유해야 합니다.', 'error')
        return redirect(url_for('user_stock.stock_lists'))
    
    list_name = stock_list.name
    db.session.delete(stock_list)
    db.session.commit()
    
    logger.info(f"종목 리스트 삭제: {current_user.username} - {list_name}")
    flash(f'종목 리스트 "{list_name}"이(가) 삭제되었습니다.', 'success')
    return redirect(url_for('user_stock.stock_lists'))

@user_stock_bp.route('/stock-lists/<int:list_id>/add-stock', methods=['GET', 'POST'])
@login_required
def add_stock(list_id):
    """종목 추가"""
    stock_list = StockList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    form = AddStockForm()
    
    if form.validate_on_submit():
        # 종목 개수 제한 확인 (최대 50개)
        current_stock_count = Stock.query.filter_by(stock_list_id=list_id).count()
        if current_stock_count >= 50:
            flash(f'리스트당 최대 50개의 종목만 추가할 수 있습니다. 현재: {current_stock_count}개', 'error')
            return redirect(url_for('user_stock.add_stock', list_id=list_id))
        
        # 중복 확인
        existing_stock = Stock.query.filter_by(
            ticker=form.ticker.data.upper(),
            stock_list_id=list_id
        ).first()
        
        if existing_stock:
            flash('이미 리스트에 존재하는 종목입니다.', 'error')
            return redirect(url_for('user_stock.add_stock', list_id=list_id))
        
        stock = Stock(
            ticker=form.ticker.data.upper(),
            name=form.name.data,
            stock_list_id=list_id
        )
        db.session.add(stock)
        db.session.commit()
        
        logger.info(f"종목 추가: {current_user.username} - {stock.ticker} to {stock_list.name}")
        flash('종목이 추가되었습니다.', 'success')
        return redirect(url_for('user_stock.view_stock_list', list_id=list_id))
    
    return render_template('user/add_stock.html', form=form, stock_list=stock_list)

@user_stock_bp.route('/stock-lists/<int:list_id>/remove-stock/<int:stock_id>', methods=['POST'])
@login_required
def remove_stock(list_id, stock_id):
    """종목 제거"""
    stock_list = StockList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    stock = Stock.query.filter_by(id=stock_id, stock_list_id=list_id).first_or_404()
    
    db.session.delete(stock)
    db.session.commit()
    
    logger.info(f"종목 제거: {current_user.username} - {stock.ticker} from {stock_list.name}")
    flash('종목이 제거되었습니다.', 'success')
    return redirect(url_for('user_stock.view_stock_list', list_id=list_id))

@user_stock_bp.route('/stock-lists/<int:list_id>/bulk-generate', methods=['POST'])
@login_required
def bulk_generate(list_id):
    """종목 리스트의 일괄 생성"""
    stock_list = StockList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    stocks = Stock.query.filter_by(stock_list_id=list_id).all()
    
    if not stocks:
        flash('리스트에 종목이 없습니다.', 'error')
        return redirect(url_for('user_stock.view_stock_list', list_id=list_id))
    
    # 일괄 생성 로직 (기존 CSV 기반 기능을 데이터베이스 기반으로 수정)
    try:
        from routes.analysis_routes import generate_chart_route, analyze_ticker_internal_logic
        from services.progress_service import start_batch_progress, end_batch_progress, update_progress, is_stop_requested
        
        tickers = [stock.ticker for stock in stocks]
        total_tickers = len(tickers)
        
        # 일괄 처리 시작 기록
        start_batch_progress("single", total_tickers, stock_list.name)
        
        results = []
        all_summaries = {}
        
        logger.info(f"일괄 생성 시작: {current_user.username} - {stock_list.name} ({total_tickers}개 종목)")
        
        for i, ticker in enumerate(tickers, 1):
            # 중단 요청 확인
            if is_stop_requested():
                logger.info(f"일괄 처리가 중단되었습니다. {i-1}개 종목이 처리되었습니다.")
                flash(f'일괄 처리가 중단되었습니다. {i-1}개 종목이 처리되었습니다.', 'warning')
                break
            
            ticker_start_time = datetime.now()
            logger.info(f"처리 중: {i}/{total_tickers} - {ticker}")
            
            # 진행상황 업데이트
            update_progress(ticker=ticker, processed=i-1, total=total_tickers, list_name=stock_list.name)
            
            try:
                # 1. 차트 생성
                chart_result = generate_chart_route(ticker)
                
                # 2. AI 분석
                today_date_str = datetime.today().strftime("%Y%m%d")
                html_file_name = f"{ticker}_{today_date_str}.html"
                
                # 분석 파일 경로 설정
                from routes.analysis_routes import get_date_folder_path, ANALYSIS_DIR
                analysis_date_folder = get_date_folder_path(ANALYSIS_DIR, today_date_str)
                analysis_html_path = os.path.join(analysis_date_folder, html_file_name)
                
                analysis_data, analysis_status_code = analyze_ticker_internal_logic(ticker, analysis_html_path)
                
                if analysis_status_code == 200 and analysis_data.get("success"):
                    all_summaries[ticker] = {
                        "gemini_summary": analysis_data.get("summary_gemini", "요약 없음."),
                        "openai_summary": "OpenAI 분석 비활성화됨",
                        "last_analyzed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    results.append({
                        "ticker": ticker,
                        "status": "성공",
                        "duration": (datetime.now() - ticker_start_time).total_seconds()
                    })
                else:
                    results.append({
                        "ticker": ticker,
                        "status": "분석 실패",
                        "error": analysis_data.get("analysis_gemini", "알 수 없는 오류")
                    })
                    
            except Exception as e:
                logger.error(f"종목 {ticker} 처리 중 오류: {e}")
                results.append({
                    "ticker": ticker,
                    "status": "오류",
                    "error": str(e)
                })
        
        # 일괄 처리 종료
        end_batch_progress()
        
        # 결과 요약
        success_count = sum(1 for r in results if r.get("status") == "성공")
        failed_count = len(results) - success_count
        
        logger.info(f"일괄 생성 완료: {current_user.username} - {stock_list.name} (성공: {success_count}, 실패: {failed_count})")
        
        flash(f'일괄 생성이 완료되었습니다. 성공: {success_count}개, 실패: {failed_count}개', 'success')
        
    except Exception as e:
        logger.error(f"일괄 생성 중 오류: {e}")
        flash(f'일괄 생성 중 오류가 발생했습니다: {str(e)}', 'error')
    
    return redirect(url_for('user_stock.view_stock_list', list_id=list_id))

@user_stock_bp.route('/lookup-ticker')
@login_required
def lookup_ticker():
    """종목 코드 조회"""
    ticker = request.args.get("ticker", "").upper()
    if not ticker:
        return jsonify({"error": "종목 코드가 필요합니다"}), 400

    try:
        import yfinance as yf
        import time
        
        # retry 로직 적용
        for attempt in range(3):
            try:
                # yfinance가 자체 세션을 사용하도록 세션 파라미터 제거
                ticker_obj = yf.Ticker(ticker)
                stock_info = ticker_obj.info
                name = stock_info.get("longName") or stock_info.get("shortName")
                sector = stock_info.get("sector", "")
                industry = stock_info.get("industry", "")
                market_cap = stock_info.get("marketCap", 0)
                country = stock_info.get("country", "")

                if name:
                    return jsonify({
                        "ticker": ticker, 
                        "name": name,
                        "sector": sector,
                        "industry": industry,
                        "market_cap": market_cap,
                        "country": country,
                        "success": True
                    })
                else:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    else:
                        return jsonify({"name": None, "message": "종목을 찾을 수 없습니다.", "success": False}), 404
                        
            except Exception as e:
                error_msg = str(e).lower()
                if '429' in error_msg or 'rate' in error_msg or 'too many' in error_msg:
                    if attempt < 2:
                        wait_time = 3 * (2 ** attempt)
                        logger.info(f"[{ticker}] Rate limit detected in user lookup, waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"종목 조회 실패 {ticker}: {e}")
                        return jsonify({"name": None, "message": "종목 조회에 실패했습니다.", "success": False}), 500
                else:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    else:
                        logger.error(f"종목 조회 실패 {ticker}: {e}")
                        return jsonify({"name": None, "message": "종목 조회에 실패했습니다.", "success": False}), 500
        
        return jsonify({"name": None, "message": "종목 조회에 실패했습니다.", "success": False}), 500
        
    except Exception as e:
        logger.error(f"종목 조회 실패 {ticker}: {e}")
        return jsonify({"name": None, "message": "종목 조회에 실패했습니다.", "success": False}), 500

@user_stock_bp.route('/search-stocks')
@login_required
def search_stocks():
    """종목 검색 (자동완성용)"""
    query = request.args.get("q", "").strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    try:
        import yfinance as yf
        import time
        import re
        
        # 일반적인 종목 코드들로 검색
        common_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX", "ADBE", "CRM",
            "005930", "000660", "005380", "035420", "051910", "006400", "035720", "068270", "207940", "323410"
        ]
        
        results = []
        added_tickers = set()  # 중복 방지
        
        def try_ticker(ticker):
            """단일 종목 정보 조회"""
            try:
                for attempt in range(2):  # 검색은 2번만 시도
                    try:
                        ticker_obj = yf.Ticker(ticker)
                        stock_info = ticker_obj.info
                        name = stock_info.get("longName") or stock_info.get("shortName")
                        
                        if name and ticker not in added_tickers:
                            results.append({
                                "ticker": ticker,
                                "name": name,
                                "sector": stock_info.get("sector", ""),
                                "country": stock_info.get("country", "")
                            })
                            added_tickers.add(ticker)
                            return True
                        elif attempt < 1:
                            time.sleep(1)
                            continue
                        else:
                            # 기본 정보만 제공
                            if ticker not in added_tickers:
                                results.append({
                                    "ticker": ticker,
                                    "name": ticker,
                                    "sector": "",
                                    "country": ""
                                })
                                added_tickers.add(ticker)
                                return True
                            return False
                            
                    except Exception as e:
                        error_msg = str(e).lower()
                        if '429' in error_msg or 'rate' in error_msg or 'too many' in error_msg:
                            if attempt < 1:
                                time.sleep(2)
                                continue
                            else:
                                # 기본 정보만 제공
                                if ticker not in added_tickers:
                                    results.append({
                                        "ticker": ticker,
                                        "name": ticker,
                                        "sector": "",
                                        "country": ""
                                    })
                                    added_tickers.add(ticker)
                                    return True
                                return False
                        else:
                            if attempt < 1:
                                time.sleep(1)
                                continue
                            else:
                                # 기본 정보만 제공
                                if ticker not in added_tickers:
                                    results.append({
                                        "ticker": ticker,
                                        "name": ticker,
                                        "sector": "",
                                        "country": ""
                                    })
                                    added_tickers.add(ticker)
                                    return True
                                return False
            except:
                # 기본 정보만 제공
                if ticker not in added_tickers:
                    results.append({
                        "ticker": ticker,
                        "name": ticker,
                        "sector": "",
                        "country": ""
                    })
                    added_tickers.add(ticker)
                    return True
                return False
        
        # 6자리 숫자 패턴 체크 (한국 종목 코드)
        if re.match(r'^\d{6}$', query):
            # 6자리 숫자면 .KS와 .KQ 둘 다 시도
            for suffix in ['.KS', '.KQ']:
                test_ticker = query + suffix
                if try_ticker(test_ticker):
                    # 하나라도 찾으면 성공
                    pass
        
        # 기존 common_tickers 검색
        for ticker in common_tickers:
            if query.upper() in ticker.upper():
                try_ticker(ticker)
        
        # 결과 수 제한
        return jsonify(results[:10])
        
    except Exception as e:
        logger.error(f"종목 검색 실패: {e}")
        return jsonify([])

# API 엔드포인트들
@user_stock_bp.route('/api/stock-lists')
@login_required
def api_get_stock_lists():
    """사용자의 종목 리스트 API"""
    stock_lists = StockList.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': sl.id,
        'name': sl.name,
        'description': sl.description,
        'is_public': sl.is_public,
        'is_default': sl.is_default,
        'stock_count': len(sl.stocks),
        'created_at': sl.created_at.isoformat()
    } for sl in stock_lists])

@user_stock_bp.route('/api/stock-lists/<int:list_id>/stocks')
@login_required
def api_get_stocks(list_id):
    """종목 리스트의 종목들 API"""
    stock_list = StockList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    stocks = Stock.query.filter_by(stock_list_id=list_id).all()
    return jsonify([{
        'id': s.id,
        'ticker': s.ticker,
        'name': s.name,
        'added_at': s.added_at.isoformat()
    } for s in stocks])

@user_stock_bp.route('/api/file-status/<ticker>')
@login_required
def api_get_file_status(ticker):
    """API: 특정 종목의 파일 상태 반환"""
    try:
        logger.info(f"Getting file status for ticker: {ticker}")
        from utils.file_manager import get_stock_file_status
        file_status = get_stock_file_status(ticker)
        logger.info(f"File status result: {file_status}")
        
        # timestamp를 ISO 형식 문자열로 변환
        chart_timestamp = file_status['chart']['timestamp']
        analysis_timestamp = file_status['analysis']['timestamp']
        
        response_data = {
            'success': True,
            'ticker': ticker,
            'chart': {
                'exists': file_status['chart']['exists'],
                'timestamp': chart_timestamp.isoformat() if chart_timestamp else None,
                'formatted_time': file_status['chart']['formatted_time'],
                'button_status': file_status['chart']['button_status']
            },
            'analysis': {
                'exists': file_status['analysis']['exists'],
                'timestamp': analysis_timestamp.isoformat() if analysis_timestamp else None,
                'formatted_time': file_status['analysis']['formatted_time'],
                'button_status': file_status['analysis']['button_status']
            },
            'is_us_stock': file_status['is_us_stock']
        }
        
        logger.info(f"API response data: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting file status for {ticker}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e),
            'ticker': ticker
        }), 500

@user_stock_bp.route('/cleanup-duplicate-lists', methods=['POST'])
@login_required
def cleanup_duplicate_lists():
    """중복된 기본 관심종목 리스트 정리"""
    try:
        # 현재 사용자의 모든 리스트 조회
        all_lists = StockList.query.filter_by(user_id=current_user.id).all()
        
        # 이름별로 그룹화
        name_groups = {}
        for stock_list in all_lists:
            if stock_list.name not in name_groups:
                name_groups[stock_list.name] = []
            name_groups[stock_list.name].append(stock_list)
        
        # 중복된 리스트 찾기 및 정리
        deleted_count = 0
        for name, lists in name_groups.items():
            if len(lists) > 1:
                # 가장 최근에 생성된 것을 남기고 나머지 삭제
                lists_sorted = sorted(lists, key=lambda x: x.created_at, reverse=True)
                lists_to_delete = lists_sorted[1:]  # 첫 번째(최신)를 제외한 나머지
                
                for list_to_delete in lists_to_delete:
                    # 종목이 있는 경우 최신 리스트로 이동
                    if list_to_delete.stocks:
                        keep_list = lists_sorted[0]
                        for stock in list_to_delete.stocks:
                            # 중복 체크 후 이동
                            existing = Stock.query.filter_by(
                                ticker=stock.ticker, 
                                stock_list_id=keep_list.id
                            ).first()
                            if not existing:
                                stock.stock_list_id = keep_list.id
                    
                    db.session.delete(list_to_delete)
                    deleted_count += 1
                    logger.info(f"중복 리스트 삭제: {current_user.username} - {list_to_delete.name} (ID: {list_to_delete.id})")
        
        db.session.commit()
        
        flash(f'중복된 리스트 {deleted_count}개가 정리되었습니다.', 'success')
        return jsonify({'success': True, 'deleted_count': deleted_count})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"중복 리스트 정리 실패: {current_user.username} - {e}")
        flash('중복 리스트 정리 중 오류가 발생했습니다.', 'error')
        return jsonify({'success': False, 'error': str(e)}) 