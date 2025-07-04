# app.py - 메인 애플리케이션 파일

import logging
import os
from flask import Flask, render_template, session, flash, redirect, url_for
from flask_login import LoginManager, current_user, login_required
from config import SECRET_KEY, SESSION_TYPE, PERMANENT_SESSION_LIFETIME, LOGGING_ENABLED, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS
from models import db, User

# 로깅 설정을 가장 먼저 적용
try:
    if not os.path.exists('logs'):
        os.makedirs('logs', exist_ok=True)
except Exception:
    # 로그 디렉토리 생성 실패시 현재 디렉토리 사용
    pass

# 로깅 설정 강제 적용
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s',
    handlers=[
        logging.FileHandler('debug.log', encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ],
    force=True
)

# 로거 생성 및 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 파일 핸들러 추가
file_handler = logging.FileHandler('debug.log', encoding='utf-8', mode='a')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.info("애플리케이션 시작 - 로깅 설정 완료")

# Flask 애플리케이션 생성
app = Flask(__name__)

# 설정 적용
app.secret_key = SECRET_KEY
app.config['SESSION_TYPE'] = SESSION_TYPE
app.config['PERMANENT_SESSION_LIFETIME'] = PERMANENT_SESSION_LIFETIME
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = SQLALCHEMY_TRACK_MODIFICATIONS

# 데이터베이스 초기화
db.init_app(app)

# Flask-Login 초기화
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = '이 페이지에 접근하려면 로그인이 필요합니다.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    """사용자 로더"""
    return User.query.get(int(user_id))

logger.info("Flask 앱 설정 완료")

# Blueprint 임포트
from routes.stock_routes import stock_bp
from routes.analysis_routes import analysis_bp
from routes.file_management_routes import file_management_bp
# from routes.prompt_test_routes import prompt_test_bp  # 임시 폴더로 이동됨
from routes.auth_routes import auth_bp
from routes.user_stock_routes import user_stock_bp
from routes.admin_routes import admin_bp
from routes.newsletter_routes import newsletter_bp

# Blueprint 등록
app.register_blueprint(stock_bp)
app.register_blueprint(analysis_bp)
app.register_blueprint(file_management_bp)
# app.register_blueprint(prompt_test_bp)  # 임시 폴더로 이동됨
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(user_stock_bp, url_prefix='/user')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(newsletter_bp, url_prefix='/newsletter')

logger.info("Blueprint 등록 완료")

# 애플리케이션 컨텍스트에서 데이터베이스 테이블 생성 (Blueprint 등록 후)
with app.app_context():
    try:
        db.create_all()
        logger.info("데이터베이스 테이블 생성 완료")
        
        # 기본 관리자 계정 생성 (존재하지 않는 경우)
        from werkzeug.security import generate_password_hash
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                email='admin@example.com',
                first_name='Admin',
                last_name='User',
                is_verified=True,
                is_admin=True,
                password_hash=generate_password_hash('NewsLetter2025!')
            )
            db.session.add(admin_user)
            db.session.commit()
            logger.info("기본 관리자 계정 생성 완료")
        else:
            logger.info("기본 관리자 계정이 이미 존재합니다")
    except Exception as e:
        logger.error(f"데이터베이스 초기화 오류: {e}")
        # 에러가 발생해도 앱은 계속 실행

@app.before_request
def set_current_stock_list():
    """요청 전에 현재 주식 리스트를 설정합니다."""
    # 첫 번째 요청시 데이터베이스 테이블 확인
    try:
        # 테이블 존재 여부 확인
        with db.engine.connect() as conn:
            conn.execute(db.text("SELECT 1 FROM users LIMIT 1"))
    except:
        # 테이블이 없으면 생성
        try:
            db.create_all()
            logger.info("요청 처리 중 데이터베이스 테이블 생성")
            
            # 관리자 계정도 생성
            from werkzeug.security import generate_password_hash
            admin_user = User.query.filter_by(username='admin').first()
            if not admin_user:
                admin_user = User(
                    username='admin',
                    email='admin@example.com',
                    first_name='Admin',
                    last_name='User',
                    is_verified=True,
                    is_admin=True,
                    password_hash=generate_password_hash('NewsLetter2025!')
                )
                db.session.add(admin_user)
                db.session.commit()
                logger.info("요청 처리 중 관리자 계정 생성")
        except Exception as e:
            logger.error(f"요청 처리 중 데이터베이스 생성 오류: {e}")
    
    if current_user.is_authenticated and 'current_stock_list' not in session:
        # 사용자의 기본 리스트로 설정
        from models import StockList
        try:
            default_list = StockList.query.filter_by(user_id=current_user.id, is_default=True).first()
            if default_list:
                session['current_stock_list'] = default_list.name
            else:
                session['current_stock_list'] = 'default'
        except Exception as e:
            logger.error(f"주식 리스트 설정 오류: {e}")
            session['current_stock_list'] = 'default'

@app.context_processor
def inject_user():
    """템플릿에 사용자 정보 주입"""
    return dict(current_user=current_user)

@app.route("/")
def home():
    """메인 페이지 - 로그인 필요"""
    logger.info("메인 페이지 접근")
    
    if not current_user.is_authenticated:
        flash('서비스를 이용하려면 로그인이 필요합니다.', 'info')
        return redirect(url_for('auth.login'))
    
    if current_user.is_administrator():
        # 어드민용 홈페이지
        return render_template("index.html")
    else:
        # 일반 사용자용 홈페이지
        return render_template("user_home.html")

@app.route("/summary_page")
@login_required
def summary_page():
    """요약 페이지"""
    return render_template("summary.html")

@app.route("/multi_summary_page")
@login_required
def multi_summary_page():
    """다중 요약 페이지"""
    return render_template("multi_summary.html")

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
        is_admin=True
    )
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    logger.info(f"관리자 계정이 생성되었습니다: {username}")

if __name__ == "__main__":
    logger.info("Flask 서버 시작")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 