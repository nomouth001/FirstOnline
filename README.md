# 주식 분석 뉴스레터 시스템

AI 기반 주식 분석과 자동화된 뉴스레터 발송 시스템입니다.

## 🚀 주요 기능

### Phase 1: 사용자 관리 시스템 ✅
- 사용자 인증 (회원가입/로그인/로그아웃)
- 사용자별 종목 리스트 관리
- 관리자 권한 시스템

### Phase 2: 뉴스레터 시스템 ✅
- **AI 분석 시스템**: Google Gemini API를 활용한 주가 분석
- **차트 분석 시스템**: 기술적 지표 및 차트 생성
- **이메일 서비스**: SendGrid를 통한 뉴스레터 발송
- **스케줄링 시스템**: Celery + Redis를 통한 자동 발송
- **뉴스레터 관리**: 구독 설정, 미리보기, 발송 히스토리

## 📧 뉴스레터 시스템

### 기능
- **개인화된 뉴스레터**: 사용자별 종목 리스트 기반 분석
- **다양한 발송 빈도**: 일일/주간/월간 구독 설정
- **커스터마이징**: 요약, 차트, 상세 분석 포함 여부 설정
- **실시간 발송**: 설정된 시간에 자동 발송
- **발송 추적**: 이메일 발송 상태 및 히스토리 관리

### 사용법
1. **뉴스레터 설정**: `/newsletter/settings`에서 구독 설정
2. **미리보기**: `/newsletter/preview`에서 발송될 뉴스레터 확인
3. **테스트 발송**: 설정 페이지에서 테스트 뉴스레터 발송
4. **히스토리 확인**: `/newsletter/history`에서 발송 이력 확인

## 🛠️ 설치 및 설정

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정
```bash
# SendGrid 설정
export SENDGRID_API_KEY='your-sendgrid-api-key'
export SENDGRID_FROM_EMAIL='noreply@yourdomain.com'
export SENDGRID_FROM_NAME='주식 분석 뉴스레터'

# Google Gemini API
export GOOGLE_API_KEY='your-gemini-api-key'

# 기타 설정
export SECRET_KEY='your-secret-key'
export FLASK_DEBUG=True
```

### 3. 데이터베이스 초기화
```bash
# 기본 데이터베이스 생성
python init_db.py

# 뉴스레터 테이블 생성
python migrate_newsletter_tables.py
```

### 4. Redis 서버 시작
```bash
redis-server
```

### 5. Celery 워커 및 Beat 시작
```bash
# 워커 시작 (새 터미널)
celery -A celery_app worker --loglevel=info

# Beat 시작 (새 터미널)
celery -A celery_app beat --loglevel=info
```

### 6. Flask 앱 시작
```bash
python app.py
```

## 📁 프로젝트 구조

```
17_NewsLetter_TestScripts/
├── app.py                          # 메인 Flask 앱
├── config.py                       # 설정 파일
├── models.py                       # 데이터베이스 모델
├── celery_app.py                   # Celery 설정
├── requirements.txt                # 의존성 목록
├── routes/                         # 라우트 파일들
│   ├── newsletter_routes.py        # 뉴스레터 라우트
│   ├── auth_routes.py             # 인증 라우트
│   └── ...
├── services/                       # 서비스 파일들
│   ├── email_service.py           # 이메일 서비스
│   ├── newsletter_service.py      # 뉴스레터 서비스
│   └── ...
├── tasks/                         # Celery 태스크
│   └── newsletter_tasks.py        # 뉴스레터 발송 태스크
├── templates/                     # HTML 템플릿
│   ├── newsletter/                # 뉴스레터 템플릿
│   │   ├── settings.html         # 설정 페이지
│   │   ├── preview.html          # 미리보기 페이지
│   │   └── history.html          # 히스토리 페이지
│   └── ...
└── static/                        # 정적 파일들
    ├── analysis/                  # 분석 결과
    ├── charts/                    # 차트 이미지
    └── ...
```

## 🔧 API 엔드포인트

### 뉴스레터 관련
- `GET /newsletter/settings` - 뉴스레터 설정 페이지
- `POST /newsletter/update_settings` - 설정 업데이트
- `GET /newsletter/preview` - 뉴스레터 미리보기
- `GET /newsletter/send_test` - 테스트 뉴스레터 발송
- `GET /newsletter/history` - 발송 히스토리

### 관리자용
- `GET /newsletter/admin/send_bulk` - 대량 발송 페이지
- `POST /newsletter/admin/send_bulk` - 대량 발송 처리

## 📊 데이터베이스 스키마

### NewsletterSubscription
- `user_id`: 사용자 ID
- `is_active`: 구독 활성화 여부
- `frequency`: 발송 빈도 (daily/weekly/monthly)
- `send_time`: 발송 시간
- `include_charts`: 차트 포함 여부
- `include_summary`: 요약 포함 여부
- `include_technical_analysis`: 상세 분석 포함 여부

### EmailLog
- `user_id`: 사용자 ID
- `email_type`: 이메일 유형
- `subject`: 제목
- `status`: 발송 상태
- `sent_at`: 발송 시간
- `error_message`: 오류 메시지

## 🚀 배포

### Render.com 배포
1. GitHub 저장소 연결
2. 환경변수 설정
3. 빌드 명령어: `pip install -r requirements.txt`
4. 시작 명령어: `gunicorn app:app`

### 로컬 개발
```bash
# 개발 서버 시작
python app.py

# 테스트 실행
cd tests
python run_all_tests.py
```

## 📝 로그

- `debug.log`: 애플리케이션 로그
- `newsletter_test.log`: 뉴스레터 테스트 로그
- Celery 워커 로그: 터미널 출력

## 🤝 기여

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 🔐 관리자 계정 관리

### 기본 관리자 계정
- **사용자명**: `admin`
- **초기 비밀번호**: `NewsLetter2025!`

### 비밀번호를 까먹었을 때
비밀번호를 분실한 경우 다음 방법들을 사용할 수 있습니다:

#### 1. 비밀번호 재설정 스크립트 사용
```bash
python reset_admin_password.py
```
이 스크립트를 실행하면 새로운 비밀번호를 안전하게 설정할 수 있습니다.

#### 2. 데이터베이스 직접 접근
```python
from app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    admin.password_hash = generate_password_hash('새비밀번호')
    db.session.commit()
```

#### 3. 웹 인터페이스에서 변경
로그인 후 `/auth/profile` 페이지에서 비밀번호를 변경할 수 있습니다.

### 보안 권장사항
- 정기적으로 비밀번호 변경
- 강력한 비밀번호 사용 (대소문자, 숫자, 특수문자 포함)
- 비밀번호를 안전한 곳에 기록해 두기

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 📞 지원

문제가 있거나 질문이 있으시면 이슈를 생성해 주세요. 