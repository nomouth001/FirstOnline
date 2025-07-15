# app.py - 메인 애플리케이션 파일

import logging
import os
from flask import Flask, render_template, session, flash, redirect, url_for, request, g, jsonify
from flask_login import LoginManager, current_user, login_required
from flask_migrate import Migrate
import config as app_config # config 모듈을 직접 임포트
from models import db, User, StockList, Stock
from utils.file_manager import get_stock_file_status
from utils.memory_monitor import initialize_memory_monitoring

# 로깅 설정을 가장 먼저 적용
try:
    if not os.path.exists('logs'):
        os.makedirs('logs', exist_ok=True)
except Exception:
    # 로그 디렉토리 생성 실패시 현재 디렉토리 사용
    pass

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_app():
    """Flask 앱 팩토리 함수"""
    app = Flask(__name__)
    
    # 설정 로드
    app.config.from_object(app_config)
    
    # 데이터베이스 초기화
    db.init_app(app)
    
    # 마이그레이션 초기화
    migrate = Migrate(app, db)
    
    # 로그인 매니저 설정
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '로그인이 필요합니다.'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Celery 초기화 (지연 임포트)
    from celery_app import create_celery_app
    celery = create_celery_app(app)
    
    # 블루프린트 등록
    from routes import register_blueprints
    register_blueprints(app)
    
    # 글로벌 컨텍스트 프로세서
    @app.context_processor
    def inject_global_vars():
        return {
            'current_user': current_user,
            'stock_file_status': get_stock_file_status()
        }
    
    # 요청 전 처리
    @app.before_request
    def before_request():
        g.user = current_user
        
        # 로그인 사용자의 세션 정보 업데이트
        if current_user.is_authenticated:
            session['user_id'] = current_user.id
            session['username'] = current_user.username
            
            # 현재 주식 리스트 설정
            if 'current_stock_list' not in session:
                try:
                    default_list = StockList.query.filter_by(user_id=current_user.id, is_default=True).first()
                    if default_list:
                        session['current_stock_list'] = default_list.name
                    else:
                        session['current_stock_list'] = 'default'
                except Exception as e:
                    logger.error(f"주식 리스트 설정 오류: {e}")
                    session['current_stock_list'] = 'default'
    
    # 홈 페이지
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('user_home'))
        return render_template('index.html')
    
    # 사용자 홈 페이지
    @app.route('/user_home')
    @login_required
    def user_home():
        try:
            # 사용자의 주식 리스트 조회
            stock_lists = StockList.query.filter_by(user_id=current_user.id).all()
            
            # 각 리스트별 주식 수 계산
            for stock_list in stock_lists:
                stock_list.stock_count = len(stock_list.stocks)
            
            return render_template('user_home.html', stock_lists=stock_lists)
        except Exception as e:
            logging.error(f"사용자 홈 페이지 로드 중 오류: {e}")
            flash('페이지를 불러오는 중 오류가 발생했습니다.', 'error')
            return render_template('user_home.html', stock_lists=[])
    
    # 프로필 페이지
    @app.route('/profile')
    @login_required
    def profile():
        return render_template('auth/profile.html')
    
    # 차트 페이지
    @app.route('/charts')
    @login_required
    def charts():
        return render_template('charts.html')
    
    # 요약 페이지
    @app.route('/summary')
    @login_required
    def summary():
        return render_template('summary.html')
    
    # 멀티 요약 페이지
    @app.route('/multi_summary')
    @login_required
    def multi_summary():
        return render_template('multi_summary.html')
    
    # 프롬프트 테스트 페이지
    @app.route('/prompt_test')
    @login_required
    def prompt_test():
        return render_template('prompt_test.html')
    
    # 404 에러 핸들러
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    # 500 에러 핸들러
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    # 데이터베이스 초기화 (첫 번째 요청 시)
    with app.app_context():
        try:
            db.create_all()
            logger.info("데이터베이스 테이블 생성 완료")
            
            # 기본 관리자 계정 생성 (존재하지 않는 경우)
            from werkzeug.security import generate_password_hash
            admin_user = User.query.filter_by(username='admin').first()
            if not admin_user:
                admin_password = os.getenv('ADMIN_PASSWORD', 'CHANGE_ME_IMMEDIATELY_123!')
                if not os.getenv('ADMIN_PASSWORD'):
                    logger.warning("ADMIN_PASSWORD 환경변수가 설정되지 않았습니다! 기본 임시 비밀번호를 사용합니다.")
                
                admin_user = User(
                    username='admin',
                    email='admin@example.com',
                    first_name='Admin',
                    last_name='User',
                    is_verified=True,
                    is_admin=True,
                    password_hash=generate_password_hash(admin_password)
                )
                db.session.add(admin_user)
                db.session.commit()
                logger.info(f"기본 관리자 계정 생성 완료")
            else:
                logger.info("기본 관리자 계정이 이미 존재합니다")
        except Exception as e:
            logger.error(f"데이터베이스 초기화 오류: {e}")
    
    # 메모리 모니터링 초기화
    initialize_memory_monitoring(app)
    
    return app

# CLI 명령어들
def register_cli_commands(app):
    """CLI 명령어 등록"""
    @app.cli.command("init-db")
    def init_db():
        """데이터베이스 초기화"""
        db.create_all()
        logger.info("데이터베이스 테이블이 생성되었습니다.")

    @app.cli.command("create-admin")
    def create_admin():
        """관리자 계정 생성"""
        from werkzeug.security import generate_password_hash
        
        username = input("관리자 사용자명: ")
        email = input("관리자 이메일: ")
        password = input("관리자 비밀번호: ")
        
        user = User(
            username=username,
            email=email,
            first_name="Admin",
            last_name="User",
            is_verified=True,
            is_admin=True,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"관리자 계정이 생성되었습니다: {username}")

# Flask 앱 생성
app = create_app()
register_cli_commands(app)

if __name__ == "__main__":
    logger.info("Flask 서버 시작")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 