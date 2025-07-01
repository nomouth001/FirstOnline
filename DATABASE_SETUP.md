# 📘 데이터베이스 설정 가이드

## 🎯 **PostgreSQL 중심 아키텍처**

이 프로젝트는 **PostgreSQL을 기본 데이터베이스**로 사용하도록 최적화되었습니다.

## 🛠️ **환경별 설정**

### **1. 프로덕션 환경 (추천)**
```bash
# PostgreSQL 사용 (기본값)
export DATABASE_URL='postgresql://username:password@localhost/dbname'
```

### **2. 로컬 개발 환경**

#### **Option A: PostgreSQL 사용 (권장)**
```bash
# 로컬 PostgreSQL 서버 설치
sudo apt install postgresql postgresql-contrib

# 데이터베이스 생성
sudo -u postgres createdb newsletter_db
sudo -u postgres psql -c "CREATE USER newsletter WITH PASSWORD 'NewsLetter2025!';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE newsletter_db TO newsletter;"

# 환경변수 설정 (선택사항 - 기본값과 동일)
export DATABASE_URL='postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db'
```

#### **Option B: SQLite 사용 (간단한 테스트용)**
```bash
# SQLite 모드 활성화
export USE_SQLITE=true
```

## 📦 **필수 패키지**

### **PostgreSQL 연결용**
```bash
pip install psycopg2-binary==2.9.9
```

### **SQLite 연결용 (Python 기본 내장)**
- 별도 설치 불필요

## 🚀 **빠른 시작**

### **새 서버 배포**
```bash
# 1. 환경변수 설정
export DATABASE_URL='postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db'

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 데이터베이스 초기화
python3 init_postgresql_simple.py
python3 load_stocks_simple.py

# 4. 서비스 시작
python3 app.py
```

### **자동 배포 스크립트**
```bash
chmod +x deploy.sh
./deploy.sh
```

## 🔧 **데이터베이스 마이그레이션**

### **기존 SQLite에서 PostgreSQL로 이주**
```python
# 1. SQLite 데이터 백업
export USE_SQLITE=true
python3 backup_sqlite_data.py

# 2. PostgreSQL로 데이터 복원
export DATABASE_URL='postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db'
python3 restore_to_postgresql.py
```

## 🎛️ **설정 우선순위**

1. **USE_SQLITE=true** → SQLite 모드 (테스트용)
2. **DATABASE_URL 환경변수** → 지정된 PostgreSQL 서버
3. **기본값** → 로컬 PostgreSQL (newsletter:NewsLetter2025!@localhost/newsletter_db)

## 📊 **성능 비교**

| 데이터베이스 | 동시 접속 | 확장성 | 복잡한 쿼리 | 추천 용도 |
|-------------|----------|--------|-------------|-----------|
| PostgreSQL  | ✅ 우수  | ✅ 우수 | ✅ 우수     | 프로덕션 |
| SQLite      | ❌ 제한적 | ❌ 제한적 | ⚠️ 보통    | 개발/테스트 |

## 🚨 **주의사항**

- **MySQL 지원 중단**: PyMySQL 패키지 제거됨
- **프로덕션에서는 SQLite 사용 금지**: 동시 접속 제한
- **PostgreSQL 권장**: 모든 환경에서 PostgreSQL 사용 권장

## 🔍 **문제 해결**

### **PostgreSQL 연결 실패**
```bash
# 서비스 상태 확인
sudo systemctl status postgresql

# 연결 테스트
psql postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db
```

### **패키지 설치 실패**
```bash
# 시스템 패키지 설치
sudo apt install python3-dev libpq-dev

# Python 패키지 재설치
pip install --upgrade psycopg2-binary
``` 