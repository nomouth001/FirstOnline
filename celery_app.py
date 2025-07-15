import os
import logging
from celery import Celery
from celery.schedules import crontab
from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
from flask import Flask

logger = logging.getLogger(__name__)

def create_celery_app(flask_app=None):
    """
    Flask 앱과 연동된 Celery 앱을 생성합니다.
    - Flask 앱 컨텍스트 안에서 작업을 실행하도록 설정합니다.
    - Flask 설정을 Celery 설정으로 가져옵니다.
    """
    if flask_app is None:
        flask_app = create_minimal_flask_app()

    celery = Celery(
        flask_app.import_name,
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['tasks.newsletter_tasks']
)

    class ContextTask(celery.Task):
        """Make celery tasks work with Flask app context."""
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    
    # Celery 설정 업데이트
    celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Seoul',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30분
    task_soft_time_limit=25 * 60,  # 25분
    worker_prefetch_multiplier=1,
        task_acks_late=True,
        result_expires=3600,  # 1시간
    )
    
    # 주기적 작업 설정
    celery.conf.beat_schedule = {
        'send-monthly-newsletter': {
        'task': 'tasks.newsletter_tasks.send_monthly_newsletters',
            'schedule': crontab(day_of_month=1, hour=9, minute=0),
    },
}
    return celery

def create_minimal_flask_app():
    """Celery 초기화를 위한 최소한의 Flask 앱을 생성합니다."""
    app = Flask(__name__)
    
    # 필요한 최소 설정만 로드
    import config as app_config
    app.config.from_object(app_config)
    
    # 데이터베이스 초기화
    from models import db
    db.init_app(app)
    
    return app

# 전역 Celery 인스턴스 생성을 함수로 분리
def get_celery_app():
    """전역 Celery 인스턴스를 반환합니다."""
    return create_celery_app()

# 조건부 전역 인스턴스 생성 (celery worker 실행 시에만)
if os.environ.get('CELERY_WORKER') == '1':
    celery_app = get_celery_app()
else:
    celery_app = None

# systemd 서비스에서 celery_app:celery로 접근할 수 있도록 별칭 생성
celery = get_celery_app() 