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
    flask_app = flask_app or create_flask_app_for_celery()

    celery = Celery(
        flask_app.import_name,
        broker=CELERY_BROKER_URL,
        backend=CELERY_RESULT_BACKEND,
        include=['tasks.newsletter_tasks']
    )
    celery.conf.update(flask_app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    celery.conf.update(
        task_track_started=True,
        task_time_limit=30 * 60,
        task_soft_time_limit=25 * 60,
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=1000,
        timezone='Asia/Seoul',
    )
    celery.conf.beat_schedule = {
        'send-daily-newsletters': {
            'task': 'tasks.newsletter_tasks.send_daily_newsletters',
            'schedule': crontab(hour=9, minute=0),
        },
        'send-weekly-newsletters': {
            'task': 'tasks.newsletter_tasks.send_weekly_newsletters',
            'schedule': crontab(day_of_week=1, hour=9, minute=0),
        },
        'send-monthly-newsletters': {
            'task': 'tasks.newsletter_tasks.send_monthly_newsletters',
            'schedule': crontab(day_of_month=1, hour=9, minute=0),
        },
    }
    return celery

def create_flask_app_for_celery():
    """Celery 초기화를 위한 간단한 Flask 앱을 생성합니다."""
    from app import create_app
    return create_app()

# 전역 Celery 인스턴스 (celery_worker.py 등에서 사용)
celery_app = create_celery_app() 