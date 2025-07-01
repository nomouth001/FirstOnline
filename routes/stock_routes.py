import os
import csv
import json
import logging
import yfinance as yf
from datetime import datetime
from flask import Blueprint, request, jsonify, session, flash
from flask_login import login_required, current_user
from models import db, StockList, Stock, get_analysis_summary_path
from utils.file_manager import safe_write_file
from config import SUMMARY_DIR

# Blueprint 생성
stock_bp = Blueprint('stock', __name__)

@stock_bp.route("/get_current_stock_list")
@login_required
def get_current_stock_list():
    """현재 선택된 주식 리스트 이름 반환"""
    current_list_name = session.get('current_stock_list', 'default')
    
    # 어드민인 경우 리스트 존재 여부만 확인
    if current_user.is_administrator():
        stock_list = StockList.query.filter_by(name=current_list_name).first()
        if stock_list:
            return jsonify({"current_list": current_list_name})
        else:
            # 어드민용 첫 번째 리스트로 변경
            first_list = StockList.query.first()
            if first_list:
                session['current_stock_list'] = first_list.name
                return jsonify({"current_list": first_list.name})
            else:
                session['current_stock_list'] = 'default'
                return jsonify({"current_list": 'default'})
    
    # 일반 사용자인 경우 자신의 리스트만 확인
    stock_list = StockList.query.filter_by(user_id=current_user.id, name=current_list_name).first()
    if stock_list:
        return jsonify({"current_list": current_list_name})
    else:
        # 기본 리스트로 변경
        default_list = StockList.query.filter_by(user_id=current_user.id, is_default=True).first()
        if default_list:
            session['current_stock_list'] = default_list.name
            return jsonify({"current_list": default_list.name})
        else:
            session['current_stock_list'] = 'default'
            return jsonify({"current_list": 'default'})

@stock_bp.route("/get_stock_lists")
@login_required
def get_stock_lists():
    """종목 리스트 목록 반환 (어드민은 모든 리스트, 일반사용자는 자신의 리스트만)"""
    try:
        if current_user.is_administrator():
            # 어드민은 모든 사용자의 리스트에 접근 가능 (알파벳 순 정렬)
            stock_lists = StockList.query.order_by(StockList.name).all()
            lists = [stock_list.name for stock_list in stock_lists]
            # 중복 제거 후 다시 정렬
            lists = sorted(list(set(lists)))
        else:
            # 일반 사용자는 자신의 리스트만 (알파벳 순 정렬)
            stock_lists = StockList.query.filter_by(user_id=current_user.id).order_by(StockList.name).all()
            lists = [stock_list.name for stock_list in stock_lists]
        
        return jsonify(lists)
    except Exception as e:
        logging.exception("Failed to get stock lists")
        return jsonify({"error": "Failed to load stock lists"}), 500

@stock_bp.route("/select_stock_list", methods=["POST"])
@login_required
def select_stock_list():
    """종목 리스트 선택"""
    data = request.get_json()
    list_name = data.get("list_name")
    if not list_name:
        return "List name is required", 400
    
    # 리스트 존재 확인 (어드민은 모든 리스트, 일반사용자는 자신의 리스트만)
    if current_user.is_administrator():
        stock_list = StockList.query.filter_by(name=list_name).first()
    else:
        stock_list = StockList.query.filter_by(user_id=current_user.id, name=list_name).first()
    
    if not stock_list:
        return f"Stock list '{list_name}' not found", 404

    session['current_stock_list'] = list_name
    return f"Stock list changed to {list_name}", 200

@stock_bp.route("/create_stock_list", methods=["POST"])
@login_required
def create_stock_list():
    """사용자의 새 종목 리스트 생성"""
    # 일반 사용자는 추가 리스트 생성 금지
    if not current_user.is_administrator():
        return "일반 사용자는 기본 관심종목 외에 추가 리스트를 생성할 수 없습니다.", 403
    
    data = request.get_json()
    list_name = data.get("list_name")
    if not list_name:
        return "List name is required", 400

    if not list_name.replace(' ', '').isalnum():  # 공백 허용, 기본 검증
        return "List name must be alphanumeric with spaces only.", 400

    # 사용자 내에서 중복 확인
    existing_list = StockList.query.filter_by(user_id=current_user.id, name=list_name).first()
    if existing_list:
        return f"Stock list '{list_name}' already exists", 409

    try:
        # 데이터베이스에 새 리스트 생성
        new_list = StockList(
            name=list_name,
            description=f"{list_name} 리스트",
            user_id=current_user.id,
            is_default=False
        )
        db.session.add(new_list)
        db.session.commit()
        
        session['current_stock_list'] = list_name
        return f"Stock list '{list_name}' created and selected successfully", 200
    except Exception as e:
        logging.exception(f"Failed to create stock list {list_name}")
        return f"Failed to create stock list {list_name}: {e}", 500

@stock_bp.route("/delete_stock_list", methods=["DELETE"])
@login_required
def delete_stock_list():
    """사용자의 종목 리스트 삭제"""
    list_name_to_delete = request.args.get("list_name")
    if not list_name_to_delete:
        return "List name is required", 400
    
    if list_name_to_delete == "default":
        return "Cannot delete the default stock list", 403

    # 사용자의 리스트인지 확인
    stock_list = StockList.query.filter_by(user_id=current_user.id, name=list_name_to_delete).first()
    if not stock_list:
        return f"Stock list '{list_name_to_delete}' not found", 404
    
    if stock_list.is_default:
        return "Cannot delete the default stock list", 403
    
    try:
        # 데이터베이스에서 리스트 삭제 (관련 종목들도 함께 삭제됨)
        db.session.delete(stock_list)
        db.session.commit()

        if session.get('current_stock_list') == list_name_to_delete:
            # 기본 리스트로 변경
            default_list = StockList.query.filter_by(user_id=current_user.id, is_default=True).first()
            if default_list:
                session['current_stock_list'] = default_list.name
            else:
                session['current_stock_list'] = 'default'
                
        return f"Stock list '{list_name_to_delete}' deleted successfully", 200
    except Exception as e:
        logging.exception(f"Failed to delete stock list {list_name_to_delete}")
        return f"Failed to delete stock list {list_name_to_delete}: {e}", 500

@stock_bp.route("/get_tickers")
@login_required
def get_tickers():
    """현재 선택된 리스트의 종목들 반환"""
    current_list_name = session.get('current_stock_list', 'default')
    
    try:
        # 리스트 확인 (어드민은 모든 리스트, 일반사용자는 자신의 리스트만)
        if current_user.is_administrator():
            stock_list = StockList.query.filter_by(name=current_list_name).first()
        else:
            stock_list = StockList.query.filter_by(user_id=current_user.id, name=current_list_name).first()
        
        if not stock_list:
            if current_user.is_administrator():
                # 어드민은 빈 리스트 반환
                return jsonify([])
            else:
                # 일반 사용자는 기본 리스트 생성 (중복 방지)
                default_list = StockList.query.filter_by(user_id=current_user.id, is_default=True).first()
                if not default_list:
                    # 이름으로도 중복 체크
                    existing_default = StockList.query.filter_by(
                        user_id=current_user.id, 
                        name='기본 관심종목'
                    ).first()
                    
                    if existing_default:
                        # 기존 리스트를 기본으로 설정
                        existing_default.is_default = True
                        db.session.commit()
                        default_list = existing_default
                    else:
                        # 새로 생성
                        default_list = StockList(
                            name='기본 관심종목',
                            description='기본 관심종목',
                            user_id=current_user.id,
                            is_default=True
                        )
                        db.session.add(default_list)
                        db.session.commit()
                stock_list = default_list
                session['current_stock_list'] = default_list.name
        
        # 종목들 반환
        stocks = Stock.query.filter_by(stock_list_id=stock_list.id).all()
        return jsonify([{
            'ticker': stock.ticker,
            'name': stock.name
        } for stock in stocks])
        
    except Exception as e:
        logging.exception(f"Failed to read tickers for {current_list_name}")
        return jsonify({"error": f"Failed to load tickers from {current_list_name}"}), 500

@stock_bp.route("/lookup")
@login_required
def lookup_ticker():
    """종목 코드 검색"""
    ticker = request.args.get("ticker", "").upper()
    if not ticker:
        return jsonify({"error": "Ticker is required"}), 400

    try:
        stock_info = yf.Ticker(ticker).info
        name = stock_info.get("longName") or stock_info.get("shortName")

        if name:
            return jsonify({"ticker": ticker, "name": name})
        else:
            return jsonify({"name": None, "message": "Ticker not found or no name available."}), 404
    except Exception as e:
        logging.error(f"Error looking up ticker {ticker}: {e}")
        return jsonify({"name": None, "message": "Failed to lookup ticker."}), 500

@stock_bp.route("/add_ticker", methods=["POST"])
@login_required
def add_ticker():
    """현재 리스트에 종목 추가"""
    data = request.get_json()
    ticker = data.get("ticker", "").upper()
    name = data.get("name", "")
    current_list_name = session.get('current_stock_list', 'default')

    if not ticker or not name:
        return "Ticker and name are required", 400

    try:
        # 사용자의 리스트인지 확인
        stock_list = StockList.query.filter_by(user_id=current_user.id, name=current_list_name).first()
        if not stock_list:
            return f"Stock list '{current_list_name}' not found", 404
        
        # 종목 개수 제한 확인 (최대 50개)
        current_stock_count = Stock.query.filter_by(stock_list_id=stock_list.id).count()
        if current_stock_count >= 50:
            return f"리스트당 최대 50개의 종목만 추가할 수 있습니다. 현재: {current_stock_count}개", 400
        
        # 중복 확인
        existing_stock = Stock.query.filter_by(
            ticker=ticker,
            stock_list_id=stock_list.id
        ).first()
        
        if existing_stock:
            return f"Ticker {ticker} already exists in {current_list_name}", 409
        
        # 새 종목 추가
        new_stock = Stock(
            ticker=ticker,
            name=name,
            stock_list_id=stock_list.id
        )
        db.session.add(new_stock)
        db.session.commit()
        
        return f"Ticker {ticker} added to {current_list_name} successfully", 200
    except Exception as e:
        logging.exception(f"Failed to add ticker {ticker} to {current_list_name}")
        return f"Failed to add ticker {ticker} to {current_list_name}: {e}", 500

@stock_bp.route("/delete_ticker", methods=["DELETE"])
@login_required
def delete_ticker():
    """현재 리스트에서 종목 삭제"""
    ticker_to_delete = request.args.get("ticker", "").upper()
    current_list_name = session.get('current_stock_list', 'default')

    if not ticker_to_delete:
        return "Ticker is required", 400

    try:
        # 사용자의 리스트인지 확인
        stock_list = StockList.query.filter_by(user_id=current_user.id, name=current_list_name).first()
        if not stock_list:
            return f"Stock list '{current_list_name}' not found", 404
        
        # 종목 찾기 및 삭제
        stock = Stock.query.filter_by(
            ticker=ticker_to_delete,
            stock_list_id=stock_list.id
        ).first()
        
        if not stock:
            return f"Ticker {ticker_to_delete} not found in {current_list_name}", 404

        db.session.delete(stock)
        db.session.commit()
        
        # 종목 삭제 시 해당 종목의 요약 정보도 업데이트
        summary_file_path = get_analysis_summary_path(current_list_name)
        if os.path.exists(summary_file_path):
            with open(summary_file_path, 'r', encoding='utf-8') as f:
                summaries = json.load(f)
            
            if ticker_to_delete in summaries:
                del summaries[ticker_to_delete]
                json_content = json.dumps(summaries, ensure_ascii=False, indent=4)
                safe_write_file(summary_file_path, json_content)

        return f"Ticker {ticker_to_delete} deleted from {current_list_name} successfully", 200
    except Exception as e:
        logging.exception(f"Failed to delete ticker {ticker_to_delete} from {current_list_name}")
        return f"Failed to delete ticker {ticker_to_delete} from {current_list_name}: {e}", 500

@stock_bp.route("/get_analysis_summary", methods=["GET"])
@login_required
def get_analysis_summary():
    """종목 분석 요약 정보 반환"""
    current_list_name = session.get('current_stock_list', 'default')
    current_date_str = datetime.now().strftime("%Y%m%d")
    
    try:
        # 리스트 확인 (어드민은 모든 리스트, 일반사용자는 자신의 리스트만)
        if current_user.is_administrator():
            stock_list = StockList.query.filter_by(name=current_list_name).first()
        else:
            stock_list = StockList.query.filter_by(user_id=current_user.id, name=current_list_name).first()
        
        if not stock_list:
            if current_user.is_administrator():
                # 어드민은 빈 리스트 반환
                return jsonify([])
            else:
                # 일반 사용자는 기본 리스트 생성 (중복 방지)
                default_list = StockList.query.filter_by(user_id=current_user.id, is_default=True).first()
                if not default_list:
                    # 이름으로도 중복 체크
                    existing_default = StockList.query.filter_by(
                        user_id=current_user.id, 
                        name='기본 관심종목'
                    ).first()
                    
                    if existing_default:
                        # 기존 리스트를 기본으로 설정
                        existing_default.is_default = True
                        db.session.commit()
                        default_list = existing_default
                    else:
                        # 새로 생성
                        default_list = StockList(
                            name='기본 관심종목',
                            description='기본 관심종목',
                            user_id=current_user.id,
                            is_default=True
                        )
                        db.session.add(default_list)
                        db.session.commit()
                stock_list = default_list
                session['current_stock_list'] = default_list.name
        
        # 종목들 반환
        stocks = Stock.query.filter_by(stock_list_id=stock_list.id).all()
        summaries = [f"{stock.ticker} - {stock.name}" for stock in stocks]
        
        try:
            # 요약 파일 저장
            summary_file_path = os.path.join(SUMMARY_DIR, f"{stock_list.name}_summary_{current_date_str}.txt")
            summary_content = '\n'.join(summaries)
            safe_write_file(summary_file_path, summary_content)
            
            logging.info(f"Summary saved to {summary_file_path}")
            return jsonify(summaries)
        except Exception as e:
            logging.error(f"Error saving summary file: {e}")
            flash(f"요약 파일 저장 실패: {e}", "error")
            return jsonify(summaries)
        
    except Exception as e:
        logging.exception(f"Failed to get analysis summary for {current_list_name}")
        return jsonify({"error": f"Failed to load analysis summary from {current_list_name}"}), 500 