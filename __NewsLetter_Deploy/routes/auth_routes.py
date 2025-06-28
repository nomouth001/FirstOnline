import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse, urljoin
from models import db, User
from forms import LoginForm, RegistrationForm, ProfileForm, ChangePasswordForm

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """로그인 페이지"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('잘못된 사용자명 또는 비밀번호입니다.', 'error')
            return redirect(url_for('auth.login'))
        
        if not user.is_active:
            flash('계정이 비활성화되었습니다. 관리자에게 문의하세요.', 'error')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=form.remember_me.data)
        logger.info(f"사용자 로그인: {user.username}")
        
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('home')
        return redirect(next_page)
    
    return render_template('auth/login.html', title='로그인', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    """로그아웃"""
    logger.info(f"사용자 로그아웃: {current_user.username}")
    logout_user()
    return redirect(url_for('home'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """회원가입 페이지"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data
        )
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"새 사용자 등록: {user.username}")
        flash('회원가입이 완료되었습니다! 이제 로그인할 수 있습니다.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', title='회원가입', form=form)

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """프로필 페이지"""
    form = ProfileForm(original_email=current_user.email)
    if form.validate_on_submit():
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.email = form.email.data
        
        db.session.commit()
        logger.info(f"사용자 프로필 업데이트: {current_user.username}")
        flash('프로필이 업데이트되었습니다.', 'success')
        return redirect(url_for('auth.profile'))
    elif request.method == 'GET':
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.email.data = current_user.email
    
    return render_template('auth/profile.html', title='프로필', form=form)

@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """비밀번호 변경 페이지"""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('현재 비밀번호가 올바르지 않습니다.', 'error')
            return redirect(url_for('auth.change_password'))
        
        current_user.set_password(form.new_password.data)
        db.session.commit()
        
        logger.info(f"사용자 비밀번호 변경: {current_user.username}")
        flash('비밀번호가 변경되었습니다.', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/change_password.html', title='비밀번호 변경', form=form)

@auth_bp.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    """서비스 탈퇴 페이지"""
    if request.method == 'POST':
        # 탈퇴 확인
        if request.form.get('confirm_withdrawal') == 'yes':
            # 관리자는 탈퇴할 수 없음
            if current_user.is_administrator():
                flash('관리자는 서비스 탈퇴를 할 수 없습니다.', 'error')
                return redirect(url_for('auth.withdraw'))
            
            # 계정 탈퇴 처리
            current_user.withdraw_account()
            db.session.commit()
            
            logger.info(f"사용자 서비스 탈퇴: {current_user.username}")
            flash('서비스 탈퇴가 완료되었습니다. 그동안 이용해 주셔서 감사합니다.', 'success')
            
            # 로그아웃 처리
            logout_user()
            return redirect(url_for('home'))
        else:
            flash('탈퇴 확인에 체크해주세요.', 'error')
    
    return render_template('auth/withdraw.html', title='서비스 탈퇴') 