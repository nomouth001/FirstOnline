import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response
from flask_login import login_required, current_user
from models import db, User, StockList, AnalysisHistory, Stock
from functools import wraps
from services.analysis_service import start_bulk_analysis_task
from utils.log_utils import LogStreamer, get_available_log_files, get_log_file_info
from utils.memory_monitor import get_memory_status, get_process_memory_status
from utils.batch_recovery import get_all_batch_status, check_and_recover_batches

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)

def admin_required(f):
    """어드민 권한이 필요한 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_administrator():
            flash('어드민 권한이 필요합니다.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@login_required
@admin_required
def admin_dashboard():
    """어드민 대시보드"""
    # 통계 정보 수집
    total_users = User.query.count()
    total_stock_lists = StockList.query.count()
    total_analyses = AnalysisHistory.query.count()
    
    # 최근 가입한 사용자들
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    
    # 최근 분석 기록
    recent_analyses = AnalysisHistory.query.order_by(AnalysisHistory.created_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html', 
                         total_users=total_users,
                         total_stock_lists=total_stock_lists,
                         total_analyses=total_analyses,
                         recent_users=recent_users,
                         recent_analyses=recent_analyses)

@admin_bp.route('/users')
@login_required
@admin_required
def admin_users():
    """사용자 관리"""
    search_query = request.args.get('search', '').strip()
    
    if search_query:
        # 사용자명, 이메일, 이름으로 검색
        users = User.query.filter(
            db.or_(
                User.username.ilike(f'%{search_query}%'),
                User.email.ilike(f'%{search_query}%'),
                User.first_name.ilike(f'%{search_query}%'),
                User.last_name.ilike(f'%{search_query}%')
            )
        ).order_by(User.created_at.desc()).all()
    else:
        users = User.query.order_by(User.created_at.desc()).all()
    
    return render_template('admin/users.html', users=users, search_query=search_query)

@admin_bp.route('/api/search-users')
@login_required
@admin_required
def api_search_users():
    """사용자 검색 API"""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    users = User.query.filter(
        db.or_(
            User.username.ilike(f'%{query}%'),
            User.email.ilike(f'%{query}%'),
            User.first_name.ilike(f'%{query}%'),
            User.last_name.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    results = []
    for user in users:
        results.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.get_full_name(),
            'is_active': user.is_active,
            'is_admin': user.is_administrator(),
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M')
        })
    
    return jsonify(results)

@admin_bp.route('/users/<int:user_id>/stock-lists')
@login_required
@admin_required
def user_stock_lists(user_id):
    """특정 사용자의 종목 리스트 관리"""
    user = User.query.get_or_404(user_id)
    stock_lists = StockList.query.filter_by(user_id=user_id).order_by(StockList.created_at.desc()).all()
    
    return render_template('admin/user_stock_lists.html', 
                         user=user, 
                         stock_lists=stock_lists)

@admin_bp.route('/users/<int:user_id>/stock-lists/<int:list_id>')
@login_required
@admin_required
def user_stock_list_detail(user_id, list_id):
    """특정 사용자의 특정 리스트 상세 보기"""
    user = User.query.get_or_404(user_id)
    stock_list = StockList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    stocks = Stock.query.filter_by(stock_list_id=list_id).order_by(Stock.ticker).all()
    
    return render_template('admin/user_stock_list_detail.html', 
                         user=user, 
                         stock_list=stock_list, 
                         stocks=stocks)

@admin_bp.route('/users/<int:user_id>/stock-lists/<int:list_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user_stock_list(user_id, list_id):
    """사용자의 리스트 편집"""
    user = User.query.get_or_404(user_id)
    stock_list = StockList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    
    if request.method == 'POST':
        stock_list.name = request.form.get('name', '').strip()
        stock_list.description = request.form.get('description', '').strip()
        stock_list.is_public = 'is_public' in request.form
        
        db.session.commit()
        flash(f'{user.username}의 리스트 "{stock_list.name}"을 수정했습니다.', 'success')
        return redirect(url_for('admin.user_stock_list_detail', user_id=user_id, list_id=list_id))
    
    return render_template('admin/edit_user_stock_list.html', 
                         user=user, 
                         stock_list=stock_list)

@admin_bp.route('/users/<int:user_id>/stock-lists/<int:list_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user_stock_list(user_id, list_id):
    """사용자의 리스트 삭제 (어드민은 기본 리스트도 삭제 가능)"""
    user = User.query.get_or_404(user_id)
    stock_list = StockList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    
    # 어드민은 기본 리스트도 삭제 가능하지만, 마지막 리스트는 삭제 방지
    user_lists_count = StockList.query.filter_by(user_id=user_id).count()
    if user_lists_count <= 1:
        flash(f'{user.username}의 마지막 리스트는 삭제할 수 없습니다. 최소 하나의 리스트는 보유해야 합니다.', 'error')
        return redirect(url_for('admin.user_stock_list_detail', user_id=user_id, list_id=list_id))
    
    list_name = stock_list.name
    is_default = stock_list.is_default
    db.session.delete(stock_list)
    db.session.commit()
    
    default_msg = " (기본 리스트)" if is_default else ""
    flash(f'{user.username}의 리스트 "{list_name}"{default_msg}을 삭제했습니다.', 'success')
    logger.info(f"어드민 {current_user.username}이 사용자 {user.username}의 리스트 '{list_name}' 삭제")
    return redirect(url_for('admin.user_stock_lists', user_id=user_id))

@admin_bp.route('/users/<int:user_id>/stock-lists/<int:list_id>/add-stock', methods=['GET', 'POST'])
@login_required
@admin_required
def add_stock_to_user_list(user_id, list_id):
    """사용자 리스트에 종목 추가"""
    user = User.query.get_or_404(user_id)
    stock_list = StockList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    
    if request.method == 'POST':
        ticker = request.form.get('ticker', '').strip().upper()
        name = request.form.get('name', '').strip()
        
        if not ticker:
            flash('종목 코드를 입력해주세요.', 'error')
            return render_template('admin/add_stock_to_user_list.html', 
                                 user=user, 
                                 stock_list=stock_list)
        
        # 종목 개수 제한 확인 (최대 50개)
        current_stock_count = Stock.query.filter_by(stock_list_id=list_id).count()
        if current_stock_count >= 50:
            flash(f'리스트당 최대 50개의 종목만 추가할 수 있습니다. 현재: {current_stock_count}개', 'error')
            return render_template('admin/add_stock_to_user_list.html', 
                                 user=user, 
                                 stock_list=stock_list)
        
        # 이미 존재하는 종목인지 확인
        existing_stock = Stock.query.filter_by(stock_list_id=list_id, ticker=ticker).first()
        if existing_stock:
            flash(f'종목 {ticker}는 이미 리스트에 존재합니다.', 'error')
            return render_template('admin/add_stock_to_user_list.html', 
                                 user=user, 
                                 stock_list=stock_list)
        
        # 새 종목 추가
        new_stock = Stock(
            stock_list_id=list_id,
            ticker=ticker,
            name=name or ticker
        )
        db.session.add(new_stock)
        db.session.commit()
        
        flash(f'{user.username}의 리스트에 종목 {ticker}를 추가했습니다.', 'success')
        return redirect(url_for('admin.user_stock_list_detail', user_id=user_id, list_id=list_id))
    
    return render_template('admin/add_stock_to_user_list.html', 
                         user=user, 
                         stock_list=stock_list)

@admin_bp.route('/users/<int:user_id>/stock-lists/<int:list_id>/stocks/<int:stock_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_stock_from_user_list(user_id, list_id, stock_id):
    """사용자 리스트에서 종목 삭제"""
    user = User.query.get_or_404(user_id)
    stock_list = StockList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    stock = Stock.query.filter_by(id=stock_id, stock_list_id=list_id).first_or_404()
    
    ticker = stock.ticker
    db.session.delete(stock)
    db.session.commit()
    
    flash(f'{user.username}의 리스트에서 종목 {ticker}를 삭제했습니다.', 'success')
    return redirect(url_for('admin.user_stock_list_detail', user_id=user_id, list_id=list_id))

@admin_bp.route('/users/<int:user_id>/stock-lists/<int:list_id>/bulk-generate', methods=['POST'])
@login_required
@admin_required
def bulk_generate_for_user_list(user_id, list_id):
    """사용자 리스트의 일괄 생성"""
    user = User.query.get_or_404(user_id)
    stock_list = StockList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    
    # 여기에 일괄 생성 로직 추가
    # (기존 일괄 생성 기능을 재사용)
    
    flash(f'{user.username}의 리스트 "{stock_list.name}"에 대한 일괄 생성을 시작했습니다.', 'success')
    return redirect(url_for('admin.user_stock_list_detail', user_id=user_id, list_id=list_id))

@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    """사용자 어드민 권한 토글"""
    user = User.query.get_or_404(user_id)
    
    # 자기 자신의 어드민 권한은 제거할 수 없음
    if user.id == current_user.id:
        flash('자기 자신의 어드민 권한은 제거할 수 없습니다.', 'error')
        return redirect(url_for('admin.admin_users'))
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = "부여" if user.is_admin else "제거"
    logger.info(f"어드민 권한 {status}: {current_user.username} -> {user.username}")
    flash(f'{user.username}의 어드민 권한을 {status}했습니다.', 'success')
    
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def toggle_active(user_id):
    """사용자 활성화/비활성화"""
    user = User.query.get_or_404(user_id)
    
    # 자기 자신의 계정은 비활성화할 수 없음
    if user.id == current_user.id:
        flash('자기 자신의 계정은 비활성화할 수 없습니다.', 'error')
        return redirect(url_for('admin.admin_users'))
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = "활성화" if user.is_active else "비활성화"
    logger.info(f"계정 {status}: {current_user.username} -> {user.username}")
    flash(f'{user.username}의 계정을 {status}했습니다.', 'success')
    
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """사용자 계정 삭제"""
    user = User.query.get_or_404(user_id)
    
    # 자기 자신의 계정은 삭제할 수 없음
    if user.id == current_user.id:
        flash('자기 자신의 계정은 삭제할 수 없습니다.', 'error')
        return redirect(url_for('admin.admin_users'))
    
    # 관리자 계정은 삭제할 수 없음 (보안상)
    if user.is_admin:
        flash('관리자 계정은 삭제할 수 없습니다. 먼저 관리자 권한을 제거해주세요.', 'error')
        return redirect(url_for('admin.admin_users'))
    
    username = user.username
    
    # 사용자와 관련된 모든 데이터 삭제 (cascade 설정으로 자동 삭제됨)
    db.session.delete(user)
    db.session.commit()
    
    logger.info(f"사용자 계정 삭제: {current_user.username} -> {username}")
    flash(f'{username}의 계정을 삭제했습니다.', 'success')
    
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/analytics')
@login_required
@admin_required
def admin_analytics():
    """분석 통계"""
    # 일별 분석 통계
    from sqlalchemy import func
    daily_analyses = db.session.query(
        func.date(AnalysisHistory.created_at).label('date'),
        func.count(AnalysisHistory.id).label('count')
    ).group_by(func.date(AnalysisHistory.created_at)).order_by(func.date(AnalysisHistory.created_at).desc()).limit(30).all()
    
    # 사용자별 분석 통계
    user_analyses = db.session.query(
        User.username,
        func.count(AnalysisHistory.id).label('count')
    ).join(AnalysisHistory).group_by(User.id, User.username).order_by(func.count(AnalysisHistory.id).desc()).limit(10).all()
    
    return render_template('admin/analytics.html', 
                         daily_analyses=daily_analyses,
                         user_analyses=user_analyses)

@admin_bp.route('/system')
@login_required
@admin_required
def admin_system():
    """시스템 정보"""
    import platform
    import psutil
    
    system_info = {
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'cpu_count': psutil.cpu_count(),
        'memory_total': f"{psutil.virtual_memory().total / (1024**3):.1f} GB",
        'memory_available': f"{psutil.virtual_memory().available / (1024**3):.1f} GB",
        'disk_usage': f"{psutil.disk_usage('/').percent:.1f}%"
    }
    
    return render_template('admin/system.html', system_info=system_info)

@admin_bp.route('/users/<int:user_id>/bulk-generate-lists', methods=['POST'])
@login_required
@admin_required
def bulk_generate_for_user_lists(user_id):
    """관리자가 특정 사용자의 여러 종목 리스트에 대해 일괄 분석을 시작합니다."""
    data = request.get_json()
    if not data or 'list_ids' not in data:
        return jsonify({'success': False, 'error': '리스트 ID가 필요합니다.'}), 400

    list_ids = data['list_ids']
    if not isinstance(list_ids, list) or not all(isinstance(i, str) and i.isdigit() for i in list_ids):
        return jsonify({'success': False, 'error': '잘못된 리스트 ID 형식입니다.'}), 400
    
    list_ids = [int(i) for i in list_ids]

    # 해당 사용자의 리스트가 맞는지 확인
    user = User.query.get_or_404(user_id)
    stock_lists = StockList.query.filter(StockList.user_id == user.id, StockList.id.in_(list_ids)).all()

    if len(stock_lists) != len(list_ids):
        return jsonify({'success': False, 'error': '유효하지 않거나 권한이 없는 리스트가 포함되어 있습니다.'}), 403

    try:
        # Celery를 사용하여 비동기적으로 일괄 분석 시작
        task = start_bulk_analysis_task.delay(user_id, list_ids)
        logger.info(f"관리자({current_user.username})가 사용자({user.username})의 {len(list_ids)}개 리스트에 대한 일괄 분석을 시작했습니다. Task ID: {task.id}")
        return jsonify({
            'success': True, 
            'message': f'{len(list_ids)}개 리스트에 대한 일괄 분석 작업이 백그라운드에서 시작되었습니다. 완료 시 알림을 받게 됩니다.',
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"일괄 분석 작업 시작 실패: {e}", exc_info=True)
        return jsonify({'success': False, 'error': '일괄 분석 작업을 시작하는 중 오류가 발생했습니다.'}), 500

@admin_bp.route('/users/<int:user_id>/cleanup-duplicate-lists', methods=['POST'])
@login_required
@admin_required
def admin_cleanup_user_duplicate_lists(user_id):
    """관리자가 특정 사용자의 중복된 리스트 정리"""
    try:
        user = User.query.get_or_404(user_id)
        
        # 해당 사용자의 모든 리스트 조회
        all_lists = StockList.query.filter_by(user_id=user_id).all()
        
        # 이름별로 그룹화
        name_groups = {}
        for stock_list in all_lists:
            if stock_list.name not in name_groups:
                name_groups[stock_list.name] = []
            name_groups[stock_list.name].append(stock_list)
        
        # 중복된 리스트 찾기 및 정리
        deleted_count = 0
        merged_stocks = 0
        
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
                                merged_stocks += 1
                    
                    db.session.delete(list_to_delete)
                    deleted_count += 1
                    logger.info(f"관리자 {current_user.username}이 사용자 {user.username}의 중복 리스트 삭제: {list_to_delete.name} (ID: {list_to_delete.id})")
        
        db.session.commit()
        
        if deleted_count > 0:
            flash(f'{user.username}의 중복된 리스트 {deleted_count}개가 정리되었습니다. (병합된 종목: {merged_stocks}개)', 'success')
        else:
            flash(f'{user.username}의 중복된 리스트가 없습니다.', 'info')
        
        return jsonify({
            'success': True, 
            'deleted_count': deleted_count,
            'merged_stocks': merged_stocks
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"관리자 중복 리스트 정리 실패: {current_user.username} -> {user.username} - {e}")
        flash('중복 리스트 정리 중 오류가 발생했습니다.', 'error')
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/users/<int:user_id>/delete-all-default-lists', methods=['POST'])
@login_required
@admin_required
def admin_delete_all_default_lists(user_id):
    """관리자가 특정 사용자의 모든 기본 리스트 삭제"""
    try:
        user = User.query.get_or_404(user_id)
        
        # 해당 사용자의 기본 리스트들 조회
        default_lists = StockList.query.filter_by(
            user_id=user_id, 
            is_default=True
        ).all()
        
        if not default_lists:
            flash(f'{user.username}의 기본 리스트가 없습니다.', 'info')
            return jsonify({'success': True, 'deleted_count': 0})
        
        # 전체 리스트 수 확인 (최소 1개는 남겨야 함)
        total_lists = StockList.query.filter_by(user_id=user_id).count()
        
        if total_lists <= len(default_lists):
            # 모든 리스트가 기본 리스트인 경우, 하나만 남기고 삭제
            lists_to_delete = default_lists[1:]  # 첫 번째는 유지
            if lists_to_delete:
                for list_to_delete in lists_to_delete:
                    # 종목들을 남겨둘 리스트로 이동
                    keep_list = default_lists[0]
                    for stock in list_to_delete.stocks:
                        existing = Stock.query.filter_by(
                            ticker=stock.ticker, 
                            stock_list_id=keep_list.id
                        ).first()
                        if not existing:
                            stock.stock_list_id = keep_list.id
                    
                    db.session.delete(list_to_delete)
                    logger.info(f"관리자 {current_user.username}이 사용자 {user.username}의 기본 리스트 삭제: {list_to_delete.name}")
                
                deleted_count = len(lists_to_delete)
                flash(f'{user.username}의 기본 리스트 {deleted_count}개를 삭제했습니다. (1개는 유지됨)', 'success')
            else:
                deleted_count = 0
                flash(f'{user.username}의 기본 리스트가 1개뿐이므로 삭제하지 않았습니다.', 'info')
        else:
            # 기본이 아닌 리스트가 있는 경우, 모든 기본 리스트 삭제 가능
            for list_to_delete in default_lists:
                db.session.delete(list_to_delete)
                logger.info(f"관리자 {current_user.username}이 사용자 {user.username}의 기본 리스트 삭제: {list_to_delete.name}")
            
            deleted_count = len(default_lists)
            flash(f'{user.username}의 모든 기본 리스트 {deleted_count}개를 삭제했습니다.', 'success')
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"관리자 기본 리스트 삭제 실패: {current_user.username} -> {user.username} - {e}")
        flash('기본 리스트 삭제 중 오류가 발생했습니다.', 'error')
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/cleanup-debug-files')
@login_required
@admin_required
def cleanup_debug_files():
    """기존 debug 파일들을 날짜별 폴더로 정리"""
    try:
        from utils.file_manager import migrate_debug_files_to_date_folders
        
        moved_count, error_count = migrate_debug_files_to_date_folders()
        
        if moved_count > 0:
            flash(f'Debug 파일 정리 완료: {moved_count}개 파일 이동, {error_count}개 오류', 'success')
        else:
            flash('이동할 debug 파일이 없습니다.', 'info')
            
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        logger.error(f"Debug 파일 정리 중 오류: {e}")
        flash('Debug 파일 정리 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('admin.dashboard')) 

@admin_bp.route('/api/file-status/<ticker>')
@login_required
@admin_required
def api_get_file_status(ticker):
    """API: 특정 종목의 파일 상태 반환 (어드민용)"""
    try:
        logger.info(f"Getting file status for ticker: {ticker}")
        from utils.file_manager import get_stock_file_status
        file_status = get_stock_file_status(ticker)
        logger.info(f"File status result: {file_status}")
        
        # 간단한 응답 형식으로 변환
        response_data = {
            'success': True,
            'ticker': ticker,
            'chart_time': file_status['chart']['formatted_time'],
            'analysis_time': file_status['analysis']['formatted_time'],
            'chart_button_status': file_status['chart']['button_status'],
            'analysis_button_status': file_status['analysis']['button_status']
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
            'ticker': ticker,
            'chart_time': '생성 안됨',
            'analysis_time': '생성 안됨',
            'chart_button_status': 'normal',
            'analysis_button_status': 'normal'
        }), 500

@admin_bp.route('/api/analysis-status/<ticker>')
@login_required
@admin_required
def api_get_analysis_status(ticker):
    """API: 특정 종목의 분석 상태 확인 (어드민용)"""
    try:
        # 분석 상태 확인 로직 (실제 구현에 따라 수정 필요)
        # 여기서는 간단히 완료 상태로 반환
        return jsonify({
            'success': True,
            'ticker': ticker,
            'status': 'completed'
        })
        
    except Exception as e:
        logger.error(f"Error getting analysis status for {ticker}: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'ticker': ticker,
            'status': 'error'
        }), 500 

@admin_bp.route('/logs')
@login_required
@admin_required
def admin_logs():
    """로그 관리 페이지"""
    log_files = get_available_log_files()
    return render_template('admin/logs.html', log_files=log_files)

@admin_bp.route('/logs/stream')
@login_required
@admin_required
def stream_logs():
    """실시간 로그 스트리밍 (SSE)"""
    log_file = request.args.get('file', 'TL_Log_to_review.txt')  # 대문자 L로 수정
    
    def generate():
        try:
            streamer = LogStreamer(log_file)
            
            # 최근 로그 먼저 전송
            recent_logs = streamer.get_recent_logs(100)
            for log_line in recent_logs:
                yield f"data: {log_line}\n\n"
            
            # 실시간 로그 follow
            for log_line in streamer.follow_log_file():
                yield f"data: {log_line}\n\n"
                
        except Exception as e:
            yield f"data: 오류: {str(e)}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@admin_bp.route('/api/logs/files')
@login_required
@admin_required
def api_log_files():
    """사용 가능한 로그 파일 목록 API"""
    log_files = get_available_log_files()
    return jsonify(log_files)

@admin_bp.route('/api/logs/info')
@login_required
@admin_required
def api_log_info():
    """로그 파일 정보 API"""
    file_path = request.args.get('file')
    if not file_path:
        return jsonify({'error': '파일 경로가 필요합니다.'}), 400
    
    info = get_log_file_info(file_path)
    if not info:
        return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404
    
    return jsonify(info)

@admin_bp.route('/api/memory/status')
@login_required
@admin_required
def api_memory_status():
    """메모리 상태 API"""
    try:
        system_memory = get_memory_status()
        process_memory = get_process_memory_status()
        
        # GB 단위로 변환
        system_memory['total_gb'] = system_memory['total'] / (1024**3)
        system_memory['used_gb'] = system_memory['used'] / (1024**3)
        
        return jsonify({
            'success': True,
            'system': system_memory,
            'processes': process_memory
        })
    except Exception as e:
        logger.error(f"메모리 상태 조회 오류: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/batch/status')
@login_required
@admin_required
def api_batch_status():
    """배치 상태 조회 API"""
    try:
        batch_status = get_all_batch_status()
        return jsonify({
            'success': True,
            'batches': batch_status,
            'total_running': len(batch_status)
        })
    except Exception as e:
        logger.error(f"배치 상태 조회 실패: {e}")
        return jsonify({'error': '배치 상태 조회에 실패했습니다.'}), 500

@admin_bp.route('/api/batch/recover', methods=['POST'])
@login_required
@admin_required
def api_batch_recover():
    """배치 복구 시도 API"""
    try:
        recovery_tasks = check_and_recover_batches()
        
        if recovery_tasks:
            return jsonify({
                'success': True,
                'message': f'{len(recovery_tasks)}개의 배치 복구 작업이 생성되었습니다.',
                'recovery_tasks': recovery_tasks
            })
        else:
            return jsonify({
                'success': True,
                'message': '복구 가능한 배치가 없습니다.',
                'recovery_tasks': []
            })
            
    except Exception as e:
        logger.error(f"배치 복구 실패: {e}")
        return jsonify({'error': '배치 복구에 실패했습니다.'}), 500