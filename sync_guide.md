# 데이터베이스 동기화 가이드

## 🔄 로컬 ↔ 온라인 데이터베이스 동기화 시스템

로컬 SQLite와 온라인 PostgreSQL 간의 데이터 동기화를 위한 완전한 솔루션입니다.

## 📋 주요 기능

### 1. 데이터베이스 비교
두 데이터베이스의 테이블별 레코드 수를 비교합니다.

```bash
# 로컬에서 실행
python utils/db_sync.py compare

# 온라인 서버에서 실행
python utils/db_sync.py compare
```

### 2. 데이터 내보내기/가져오기
JSON 형태로 데이터를 백업하고 복원합니다.

```bash
# 현재 데이터베이스 내보내기
python utils/db_sync.py export --file backup_20250711.json

# 백업 파일에서 데이터 가져오기
python utils/db_sync.py import --file backup_20250711.json
```

### 3. 데이터베이스 동기화
한 방향으로 데이터를 완전히 동기화합니다.

```bash
# 로컬 → 온라인 동기화
python utils/db_sync.py sync-to-remote

# 온라인 → 로컬 동기화
python utils/db_sync.py sync-to-local
```

## 🚀 배포 시 자동 동기화

### 기본 배포 (동기화 없음)
```bash
./deploy.sh
```

### 로컬 데이터를 온라인으로 동기화하며 배포
```bash
./deploy_with_sync.sh --sync-from-local
```

### 온라인 데이터를 로컬로 동기화하며 배포
```bash
./deploy_with_sync.sh --sync-from-remote
```

### 데이터베이스 상태만 확인
```bash
./deploy_with_sync.sh --compare-only
```

## 📊 동기화 대상 데이터

- **사용자 계정** (users)
- **주식 리스트** (stock_lists)
- **주식 종목** (stocks)
- **분석 히스토리** (analysis_history)
- **뉴스레터 구독** (newsletter_subscriptions)
- **이메일 로그** (email_logs)

## 🔧 설정 방법

### 1. 환경변수 설정
온라인 데이터베이스 연결을 위해 환경변수를 설정합니다.

```bash
# 로컬 개발 환경
export DATABASE_URL="postgresql://user:password@host:port/database"

# 또는 .env 파일에 추가
DATABASE_URL=postgresql://user:password@host:port/database
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

## 🛡️ 안전 장치

### 자동 백업
동기화 전에 기존 데이터를 자동으로 백업합니다.

```
backup_local_20250711_120000.json
backup_remote_20250711_120000.json
```

### 참조 무결성
데이터 가져오기 시 외래 키 관계를 고려한 순서로 진행합니다.

1. users (사용자)
2. stock_lists (주식 리스트)
3. stocks (주식 종목)
4. analysis_history (분석 히스토리)
5. newsletter_subscriptions (뉴스레터 구독)
6. email_logs (이메일 로그)

## 📝 사용 시나리오

### 시나리오 1: 개발 → 운영 배포
```bash
# 로컬에서 개발 완료 후
./deploy_with_sync.sh --sync-from-local
```

### 시나리오 2: 운영 데이터 백업
```bash
# 온라인 서버에서
python utils/db_sync.py export --file production_backup.json
```

### 시나리오 3: 로컬 개발 환경 업데이트
```bash
# 로컬에서 운영 데이터 가져오기
python utils/db_sync.py sync-to-local
```

### 시나리오 4: 정기적인 상태 확인
```bash
# 크론잡 또는 정기적으로 실행
python utils/db_sync.py compare
```

## ⚠️ 주의사항

1. **완전 동기화**: 동기화 시 대상 데이터베이스의 기존 데이터가 삭제됩니다.
2. **백업 확인**: 자동 생성된 백업 파일을 확인하여 안전하게 보관하세요.
3. **환경변수**: DATABASE_URL이 올바르게 설정되어 있는지 확인하세요.
4. **네트워크**: 온라인 데이터베이스 연결이 가능한 환경에서 실행하세요.

## 🔍 트러블슈팅

### 연결 오류
```bash
# 데이터베이스 연결 상태 확인
python debug_db_connection.py
```

### 권한 오류
```bash
# 데이터베이스 사용자 권한 확인
# PostgreSQL의 경우 CREATE, DROP, INSERT, UPDATE, DELETE 권한 필요
```

### 큰 데이터 동기화
```bash
# 큰 데이터의 경우 타임아웃 설정 증가
# 또는 부분적 동기화 고려
```

## 📅 정기적인 동기화

### 크론잡 설정 예시
```bash
# 매일 오전 3시에 비교
0 3 * * * cd /path/to/project && python utils/db_sync.py compare

# 매주 일요일 오전 2시에 백업
0 2 * * 0 cd /path/to/project && python utils/db_sync.py export --file weekly_backup_$(date +\%Y\%m\%d).json
```

이 시스템을 통해 로컬과 온라인 데이터베이스를 안전하고 효율적으로 동기화할 수 있습니다. 