import os
import logging
from celery import Celery
from celery.schedules import crontab
from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

logger = logging.getLogger(__name__)

# Celery 애플리케이션 생성
celery_app = Celery(
    'newsletter_tasks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['tasks.newsletter_tasks']
)

# Celery 설정
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/New_York',  # 미국 동부시간으로 변경
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30분
    task_soft_time_limit=25 * 60,  # 25분
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# 스케줄 설정
celery_app.conf.beat_schedule = {
    'send-daily-newsletters': {
        'task': 'tasks.newsletter_tasks.send_daily_newsletters',
        'schedule': crontab(hour=9, minute=0),  # 매일 EST 9시
    },
    'send-weekly-newsletters': {
        'task': 'tasks.newsletter_tasks.send_weekly_newsletters',
        'schedule': crontab(day_of_week=1, hour=9, minute=0),  # 매주 월요일 EST 9시
    },
    'send-monthly-newsletters': {
        'task': 'tasks.newsletter_tasks.send_monthly_newsletters',
        'schedule': crontab(day_of_month=1, hour=9, minute=0),  # 매월 1일 EST 9시
    },
    'auto-analyze-us-stocks': {
        'task': 'tasks.newsletter_tasks.auto_analyze_us_stocks',
        'schedule': crontab(
            day_of_week='1-5',  # 월요일~금요일 (1=월, 2=화, 3=수, 4=목, 5=금)
            hour=18,            # EST 18:00 (미국 시장 마감 후)
            minute=0
        ),
    },
    'auto-analyze-korean-stocks': {
        'task': 'tasks.newsletter_tasks.auto_analyze_korean_stocks',
        'schedule': crontab(
            day_of_week='1-5',  # 월요일~금요일
            hour=5,             # EST 05:00 (= KST 18:00/19:00, 서머타임 고려)
            minute=0
        ),
    },
}

if __name__ == '__main__':
    celery_app.start() 