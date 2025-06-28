import logging
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, NewsletterSubscription, EmailLog
from services.newsletter_service import newsletter_service
from services.email_service import email_service

logger = logging.getLogger(__name__)

newsletter_bp = Blueprint('newsletter', __name__, url_prefix='/newsletter')

@newsletter_bp.route('/settings')
@login_required
def settings():
    """뉴스레터 설정 페이지"""
    try:
        subscription = NewsletterSubscription.query.filter_by(user_id=current_user.id).first()
        
        if not subscription:
            # 기본 구독 설정 생성
            subscription = NewsletterSubscription(
                user_id=current_user.id,
                is_active=True,
                frequency='daily',
                include_charts=True,
                include_summary=True,
                include_technical_analysis=True
            )
            db.session.add(subscription)
            db.session.commit()
        
        return render_template('newsletter/settings.html', subscription=subscription)
        
    except Exception as e:
        logger.error(f"뉴스레터 설정 페이지 오류: {e}")
        flash('설정을 불러오는 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('home'))

@newsletter_bp.route('/update_settings', methods=['POST'])
@login_required
def update_settings():
    """뉴스레터 설정 업데이트"""
    try:
        subscription = NewsletterSubscription.query.filter_by(user_id=current_user.id).first()
        
        if not subscription:
            subscription = NewsletterSubscription(user_id=current_user.id)
            db.session.add(subscription)
        
        # 설정 업데이트
        subscription.is_active = request.form.get('is_active') == 'on'
        subscription.frequency = request.form.get('frequency', 'daily')
        subscription.include_charts = request.form.get('include_charts') == 'on'
        subscription.include_summary = request.form.get('include_summary') == 'on'
        subscription.include_technical_analysis = request.form.get('include_technical_analysis') == 'on'
        
        # 발송 시간 설정
        send_time = request.form.get('send_time', '09:00')
        try:
            from datetime import datetime
            subscription.send_time = datetime.strptime(send_time, '%H:%M').time()
        except ValueError:
            subscription.send_time = datetime.strptime('09:00', '%H:%M').time()
        
        db.session.commit()
        
        flash('뉴스레터 설정이 업데이트되었습니다.', 'success')
        return redirect(url_for('newsletter.settings'))
        
    except Exception as e:
        logger.error(f"뉴스레터 설정 업데이트 오류: {e}")
        flash('설정 업데이트 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('newsletter.settings'))

@newsletter_bp.route('/preview')
@login_required
def preview():
    """뉴스레터 미리보기"""
    try:
        from models import StockList
        
        # 사용자의 종목 리스트 가져오기 (기본 리스트 우선, 없으면 다른 리스트)
        stock_list = StockList.query.filter_by(user_id=current_user.id, is_default=True).first()
        if not stock_list:
            # 기본 리스트가 없으면 사용자의 첫 번째 리스트 사용
            stock_list = StockList.query.filter_by(user_id=current_user.id).first()
            if not stock_list:
                flash('종목 리스트가 없습니다. 먼저 종목을 추가해주세요.', 'warning')
                return redirect(url_for('user_stock.create_stock_list'))
        
        # 뉴스레터 콘텐츠 생성
        content = newsletter_service.generate_newsletter_content(current_user, stock_list)
        if not content:
            flash('뉴스레터 콘텐츠를 생성할 수 없습니다. 먼저 종목 분석을 실행해주세요. (최근 7일간 분석 결과를 찾을 수 없음)', 'warning')
            return redirect(url_for('newsletter.settings'))
        
        return render_template('newsletter/preview.html', content=content)
        
    except Exception as e:
        logger.error(f"뉴스레터 미리보기 오류: {e}")
        flash('미리보기를 생성하는 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('newsletter.settings'))

@newsletter_bp.route('/preview_multi')
@login_required
def preview_multi():
    """멀티 리스트 뉴스레터 미리보기"""
    try:
        from models import StockList
        
        # 사용자의 모든 종목 리스트 가져오기
        stock_lists = StockList.query.filter_by(user_id=current_user.id).all()
        if not stock_lists:
            flash('종목 리스트가 없습니다. 먼저 종목을 추가해주세요.', 'warning')
            return redirect(url_for('user_stock.create_stock_list'))
        
        # 멀티 리스트 뉴스레터 콘텐츠 생성
        content = newsletter_service.generate_multi_list_newsletter_content(current_user, stock_lists)
        if not content:
            flash('뉴스레터 콘텐츠를 생성할 수 없습니다. 먼저 종목 분석을 실행해주세요. (최근 7일간 분석 결과를 찾을 수 없음)', 'warning')
            return redirect(url_for('newsletter.settings'))
        
        return render_template('newsletter/preview.html', content=content, is_multi_list=True)
        
    except Exception as e:
        logger.error(f"멀티 리스트 뉴스레터 미리보기 오류: {e}")
        flash('미리보기를 생성하는 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('newsletter.settings'))

@newsletter_bp.route('/send_test')
@login_required
def send_test():
    """테스트 뉴스레터 발송"""
    try:
        from models import StockList
        
        # 사용자의 종목 리스트 가져오기 (기본 리스트 우선, 없으면 다른 리스트)
        stock_list = StockList.query.filter_by(user_id=current_user.id, is_default=True).first()
        if not stock_list:
            # 기본 리스트가 없으면 사용자의 첫 번째 리스트 사용
            stock_list = StockList.query.filter_by(user_id=current_user.id).first()
            if not stock_list:
                return jsonify({'success': False, 'message': '종목 리스트가 없습니다.'})
        
        # 뉴스레터 콘텐츠 생성
        content = newsletter_service.generate_newsletter_content(current_user, stock_list)
        if not content:
            return jsonify({'success': False, 'message': '뉴스레터 콘텐츠를 생성할 수 없습니다. 먼저 종목 분석을 실행해주세요.'})
        
        # 테스트 이메일 발송
        subject = f"📧 테스트 뉴스레터 - {current_user.get_full_name()}님"
        success, result = email_service.send_newsletter(
            current_user, subject, content['html'], content['text']
        )
        
        if success:
            return jsonify({'success': True, 'message': '테스트 뉴스레터가 발송되었습니다.'})
        else:
            return jsonify({'success': False, 'message': f'발송 실패: {result}'})
        
    except Exception as e:
        logger.error(f"테스트 뉴스레터 발송 오류: {e}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'})

@newsletter_bp.route('/history')
@login_required
def history():
    """이메일 발송 히스토리"""
    try:
        # 최근 50개의 이메일 로그 가져오기
        email_logs = EmailLog.query.filter_by(user_id=current_user.id)\
            .order_by(EmailLog.sent_at.desc())\
            .limit(50)\
            .all()
        
        return render_template('newsletter/history.html', email_logs=email_logs)
        
    except Exception as e:
        logger.error(f"이메일 히스토리 조회 오류: {e}")
        flash('히스토리를 불러오는 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('newsletter.settings'))

@newsletter_bp.route('/unsubscribe/<token>')
def unsubscribe(token):
    """뉴스레터 구독 해제 (토큰 기반)"""
    try:
        # 토큰으로 구독 정보 찾기
        subscription = NewsletterSubscription.query.filter_by(unsubscribe_token=token).first()
        
        if not subscription:
            flash('유효하지 않은 구독 해제 링크입니다.', 'error')
            return redirect(url_for('home'))
        
        # 구독 해제 처리
        subscription.is_active = False
        db.session.commit()
        
        flash(f'{subscription.user.get_full_name()}님의 뉴스레터 구독이 해제되었습니다.', 'info')
        return render_template('newsletter/unsubscribed.html', user=subscription.user)
        
    except Exception as e:
        logger.error(f"구독 해제 오류: {e}")
        flash('구독 해제 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('home'))

# 관리자용 뉴스레터 관리 라우트
@newsletter_bp.route('/admin/send_bulk')
@login_required
def admin_send_bulk():
    """관리자용 대량 뉴스레터 발송"""
    if not current_user.is_administrator():
        flash('관리자 권한이 필요합니다.', 'error')
        return redirect(url_for('home'))
    
    try:
        from models import User, NewsletterSubscription
        
        # 활성 구독자 목록 가져오기
        active_subscriptions = NewsletterSubscription.query.filter_by(is_active=True).all()
        users = [sub.user for sub in active_subscriptions if sub.user.is_active]
        
        return render_template('newsletter/admin_bulk_send.html', users=users)
        
    except Exception as e:
        logger.error(f"대량 발송 페이지 오류: {e}")
        flash('페이지를 불러오는 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('admin.dashboard'))

@newsletter_bp.route('/admin/send_bulk', methods=['POST'])
@login_required
def admin_send_bulk_post():
    """관리자용 대량 뉴스레터 발송 처리"""
    if not current_user.is_administrator():
        return jsonify({'success': False, 'message': '관리자 권한이 필요합니다.'})
    
    try:
        from models import User, NewsletterSubscription
        
        user_ids = request.form.getlist('user_ids')
        newsletter_type = request.form.get('newsletter_type', 'daily')
        
        success_count = 0
        error_count = 0
        
        for user_id in user_ids:
            try:
                if newsletter_type == 'daily':
                    success = newsletter_service.send_daily_newsletter(int(user_id))
                elif newsletter_type == 'weekly':
                    success = newsletter_service.send_weekly_newsletter(int(user_id))
                else:
                    continue
                
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"사용자 {user_id} 뉴스레터 발송 실패: {e}")
                error_count += 1
        
        message = f"발송 완료: 성공 {success_count}건, 실패 {error_count}건"
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        logger.error(f"대량 발송 처리 오류: {e}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'})

@newsletter_bp.route('/send_test_multi')
@login_required
def send_test_multi():
    """통합 테스트 뉴스레터 발송 (모든 리스트 포함)"""
    try:
        from models import StockList
        
        # 사용자의 모든 종목 리스트 가져오기
        stock_lists = StockList.query.filter_by(user_id=current_user.id).all()
        if not stock_lists:
            return jsonify({'success': False, 'message': '종목 리스트가 없습니다.'})
        
        # 멀티 리스트 뉴스레터 콘텐츠 생성
        content = newsletter_service.generate_multi_list_newsletter_content(current_user, stock_lists)
        if not content:
            return jsonify({'success': False, 'message': '뉴스레터 콘텐츠를 생성할 수 없습니다. 먼저 종목 분석을 실행해주세요.'})
        
        # 테스트 이메일 발송
        subject = f"📧 통합 테스트 뉴스레터 - {current_user.get_full_name()}님 ({content['list_count']}개 리스트)"
        success, result = email_service.send_newsletter(
            current_user, subject, content['html'], content['text']
        )
        
        if success:
            return jsonify({
                'success': True, 
                'message': f'통합 테스트 뉴스레터가 발송되었습니다.',
                'stock_count': content['stock_count'],
                'list_count': content['list_count']
            })
        else:
            return jsonify({'success': False, 'message': f'발송 실패: {result}'})
        
    except Exception as e:
        logger.error(f"통합 테스트 뉴스레터 발송 오류: {e}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}) 