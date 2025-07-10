# AWS Lightsail 배포 오류 해결 가이드

## 개요
뉴스레터 애플리케이션을 AWS Lightsail에 배포하는 과정에서 발생한 오류들과 해결법을 정리한 문서입니다.

---

## 1. 구문 오류 (Syntax Error) 문제들

### 1.1 routes/analysis_routes.py 들여쓰기 오류

**오류 메시지:**
```
❌ 데이터베이스 연결 실패: expected an indented block after 'if' statement on line 125 (analysis_routes.py, line 126)
```

**원인:**
- 163번째 줄 `generate_multiple_lists_analysis_route` 함수에서 들여쓰기 문제
- except 블록의 들여쓰기가 잘못됨

**해결법:**
```python
# 잘못된 코드
try:
    # 코드...
except Exception as e:
logging.error(f"오류: {e}")  # 들여쓰기 없음

# 올바른 코드
try:
    # 코드...
except Exception as e:
    logging.error(f"오류: {e}")  # 적절한 들여쓰기
```

### 1.2 services/analysis_service.py 들여쓰기 오류

**오류 메시지:**
```
❌ 구문 오류: unexpected indent (<unknown>, line 755)
```

**원인:**
- 755번째 줄 `gemini_inputs = [` 부분의 들여쓰기 문제
- 주석 처리된 코드 블록 이후 들여쓰기 레벨이 잘못됨

**해결법:**
```python
# 잘못된 코드
        # 차트 이미지 전송 비활성화 - 텍스트만 전달
            gemini_inputs = [  # 잘못된 들여쓰기
                {"text": common_prompt}
            ]

# 올바른 코드
        # 차트 이미지 전송 비활성화 - 텍스트만 전달
        gemini_inputs = [  # 올바른 들여쓰기
            {"text": common_prompt}
        ]
```

### 1.3 services/progress_service.py 들여쓰기 오류

**오류 메시지:**
```
❌ 구문 오류: expected an indented block after 'try' statement on line 21 (<unknown>, line 22)
```

**원인:**
- `try:` 문 다음에 들여쓰기가 없는 코드
- 여러 함수에서 들여쓰기 일관성 문제

**해결법:**
```python
# 잘못된 코드
try:
logging.info("시작")  # 들여쓰기 없음

# 올바른 코드
try:
    logging.info("시작")  # 적절한 들여쓰기
```

---

## 2. SQLAlchemy 호환성 문제

### 2.1 table_names() 메서드 오류

**오류 메시지:**
```
❌ 데이터베이스 연결 실패: 'Engine' object has no attribute 'table_names'
```

**원인:**
- SQLAlchemy 최신 버전에서 `engine.table_names()` 메서드가 제거됨
- 구버전 API 사용

**해결법:**
```python
# 잘못된 코드 (구버전)
tables = db.engine.table_names()

# 올바른 코드 (신버전)
from sqlalchemy import inspect
inspector = inspect(db.engine)
tables = inspector.get_table_names()
```

---

## 3. 환경변수 설정 문제

### 3.1 하드코딩된 관리자 비밀번호

**문제:**
- `app.py`에서 관리자 비밀번호가 하드코딩됨
- 환경변수 `ADMIN_PASSWORD` 무시

**해결법:**
```python
# 잘못된 코드
admin_password = 'NewsLetter2025!'

# 올바른 코드
admin_password = os.getenv('ADMIN_PASSWORD', 'default_password')
```

### 3.2 bash 히스토리 확장 문제

**문제:**
- 비밀번호에 `!` 문자가 포함되어 bash 히스토리 확장 오류 발생

**해결법:**
```bash
# 문제가 되는 명령
export ADMIN_PASSWORD='NewsLetter2025!'

# 해결법 1: 작은따옴표 사용
export ADMIN_PASSWORD='NewsLetter2025!'

# 해결법 2: 히스토리 확장 비활성화
set +H
export ADMIN_PASSWORD='NewsLetter2025!'
set -H
```

---

## 4. 데이터베이스 연결 문제

### 4.1 SQLite와 PostgreSQL 혼용

**문제:**
- 설정에서는 PostgreSQL을 사용하도록 되어 있으나 실제로는 SQLite 사용
- 환경변수 `DATABASE_URL` 미설정

**해결법:**
```bash
# AWS Lightsail에서 환경변수 설정
export DATABASE_URL='postgresql://newsletter:NewsLetter2025!@localhost:5432/newsletter_db'
export ADMIN_PASSWORD='NewsLetter2025!'
export GOOGLE_API_KEY='your_api_key'
export SECRET_KEY='your_secret_key'
```

---

## 5. 파일 권한 문제

### 5.1 deploy.sh 실행 권한 없음

**오류 메시지:**
```
-bash: ./deploy.sh: Permission denied
```

**해결법:**
```bash
# 실행 권한 부여
chmod +x deploy.sh

# 실행
./deploy.sh
```

---

## 6. IDE와 실제 환경의 차이

### 6.1 IDE에서 감지하지 못하는 오류들

**문제 유형:**
1. **줄 끝 문자 차이**: Windows(CRLF) vs Linux(LF)
2. **탭 vs 스페이스 혼용**: 보이지 않는 문자 차이
3. **인코딩 문제**: UTF-8 vs 다른 인코딩
4. **라이브러리 버전 차이**: 로컬과 서버 환경 차이

**해결법:**
```bash
# Python 구문 검사로 정확한 오류 확인
python -c "
import ast
try:
    with open('파일명.py', 'r', encoding='utf-8') as f:
        content = f.read()
    ast.parse(content)
    print('✅ 구문 분석 성공')
except SyntaxError as e:
    print(f'❌ 구문 오류: {e}')
    print(f'라인: {e.lineno}')
    print(f'위치: {e.offset}')
    print(f'텍스트: {e.text}')
"
```

---

## 7. 배포 프로세스 최적화

### 7.1 자동화된 배포 스크립트

**deploy.sh 구성:**
```bash
#!/bin/bash
echo "🚀 AWS Lightsail 배포 시작..."

# 1. 코드 업데이트
git reset --hard HEAD
git pull origin main

# 2. 가상환경 활성화
source venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 데이터베이스 초기화
python init_db.py

# 5. 서비스 재시작
sudo systemctl restart newsletter-app
sudo systemctl restart nginx

echo "🎉 배포 완료!"
```

### 7.2 GitHub Actions 자동 배포

**.github/workflows/deploy.yml:**
```yaml
name: Deploy to AWS Lightsail

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - name: Deploy to server
      uses: appleboy/ssh-action@v0.1.5
      with:
        host: ${{ secrets.HOST }}
        username: ${{ secrets.USERNAME }}
        key: ${{ secrets.KEY }}
        script: |
          cd ~/newsletter-app
          git pull origin main
          source venv/bin/activate
          pip install -r requirements.txt
          python init_db.py
          sudo systemctl restart newsletter-app
```

---

## 8. 디버깅 도구

### 8.1 데이터베이스 연결 디버깅

**debug_db_connection.py:**
```python
def check_database_connection():
    try:
        from app import app, db
        with app.app_context():
            db.session.execute(db.text("SELECT 1"))
            print("✅ 데이터베이스 연결 성공")
    except Exception as e:
        print(f"❌ 데이터베이스 연결 실패: {e}")
```

### 8.2 환경변수 확인

```python
def check_environment():
    env_vars = ['DATABASE_URL', 'ADMIN_PASSWORD', 'GOOGLE_API_KEY', 'SECRET_KEY']
    for var in env_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value[:10]}...")
        else:
            print(f"❌ {var}: 설정되지 않음")
```

---

## 9. 최종 해결 순서

1. **구문 오류 수정**: Python AST 파서로 정확한 오류 위치 확인
2. **환경변수 설정**: AWS Lightsail에서 모든 필수 환경변수 설정
3. **데이터베이스 연결**: PostgreSQL 연결 확인
4. **의존성 업데이트**: requirements.txt 기반 패키지 설치
5. **서비스 재시작**: Flask 앱 및 Nginx 재시작
6. **테스트**: 웹 브라우저에서 기능 확인

---

## 10. 예방 조치

### 10.1 코드 품질 관리
- **린터 사용**: flake8, pylint 등으로 코드 품질 검사
- **포맷터 사용**: black, autopep8로 일관된 코드 스타일 유지
- **타입 힌트**: mypy로 타입 검사

### 10.2 배포 전 체크리스트
- [ ] 로컬에서 Python 구문 검사 완료
- [ ] 환경변수 설정 확인
- [ ] 데이터베이스 연결 테스트
- [ ] requirements.txt 업데이트
- [ ] 보안 설정 확인

### 10.3 모니터링 설정
```bash
# 로그 모니터링
tail -f app.log

# 서비스 상태 확인
systemctl status newsletter-app

# 시스템 리소스 모니터링
htop
```

---

## 결론

AWS Lightsail 배포 과정에서 발생한 주요 문제들은 대부분 **구문 오류**와 **환경 설정** 문제였습니다. 

**핵심 교훈:**
1. IDE가 모든 오류를 잡지 못하므로 실제 Python 인터프리터로 검증 필요
2. 환경변수 설정은 배포 성공의 핵심
3. 자동화된 배포 스크립트로 실수 방지
4. 체계적인 디버깅 도구 활용

이러한 경험을 바탕으로 향후 배포 시에는 더욱 안정적이고 효율적인 프로세스를 구축할 수 있을 것입니다. 



완성된 문서입니다! 📝
AWS_배포_오류_해결_가이드.md 파일을 생성했습니다. 이 문서는 다음과 같은 내용을 포함합니다:
📋 주요 내용
구문 오류 문제들 - 3개 파일의 들여쓰기 오류와 해결법
SQLAlchemy 호환성 문제 - table_names() 메서드 오류
환경변수 설정 문제 - 하드코딩된 비밀번호, bash 히스토리 확장 문제
데이터베이스 연결 문제 - SQLite/PostgreSQL 혼용 문제
파일 권한 문제 - deploy.sh 실행 권한
IDE와 실제 환경의 차이 - 감지하지 못하는 오류들
배포 프로세스 최적화 - 자동화 스크립트, GitHub Actions
디버깅 도구 - 데이터베이스 연결 체크, 환경변수 확인
최종 해결 순서 - 체계적인 문제 해결 과정
예방 조치 - 코드 품질 관리, 체크리스트, 모니터링
🎯 핵심 교훈
IDE 한계: IDE가 모든 오류를 잡지 못하므로 실제 Python 인터프리터로 검증 필요
환경변수 중요성: 배포 성공의 핵심
자동화 필요성: 배포 스크립트로 실수 방지
체계적 디버깅: 단계별 문제 해결 도구 활용
이 문서는 향후 비슷한 배포 작업 시 참고 자료로 활용할 수 있으며, 다른 개발자들과 공유하여 같은 문제를 예방하는 데 도움이 될 것입니다! 🚀
