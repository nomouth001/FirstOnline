# 🚀 안전한 배포 가이드

## ⚠️ 중요한 변경사항

**기존 배포 방식의 문제점**:
- 매번 `init_db.py`를 실행하여 데이터베이스를 초기화
- 기존 사용자 데이터, 주식 리스트, 분석 히스토리 등이 삭제됨
- 운영 환경에서 매우 위험한 방식

**새로운 안전한 배포 방식**:
- 기존 데이터를 보존하면서 스키마 업데이트
- 자동 백업 생성
- 버전 관리 시스템
- 안전한 마이그레이션 프로세스

## 🔄 배포 옵션 비교

### 1. 안전한 배포 (권장) 
```bash
./deploy_safe.sh
```

**특징**:
- ✅ 기존 데이터 보존
- ✅ 자동 백업 생성
- ✅ 안전한 스키마 업데이트
- ✅ 버전 관리
- ✅ 상세한 로그 및 상태 확인

### 2. 동기화 배포
```bash
./deploy_with_sync.sh [옵션]
```

**옵션**:
- `--sync-from-local`: 로컬 데이터를 온라인으로 동기화
- `--sync-from-remote`: 온라인 데이터를 로컬로 동기화
- `--compare-only`: 데이터베이스 상태만 비교

### 3. 기존 배포 (⚠️ 위험)
```bash
./deploy.sh
```

**주의**: 이 방식은 데이터를 초기화하므로 운영 환경에서 사용하지 마세요!

## 🛠️ 안전한 배포 단계별 가이드

### 1단계: 배포 전 준비

```bash
# 1. 현재 데이터베이스 상태 확인
python utils/db_migration.py status

# 2. 수동 백업 생성 (선택사항)
python utils/db_migration.py backup

# 3. 환경변수 확인
echo $ADMIN_PASSWORD
```

### 2단계: 안전한 배포 실행

```bash
# 안전한 배포 실행
./deploy_safe.sh
```

### 3단계: 배포 후 검증

```bash
# 1. 서비스 상태 확인
systemctl status newsletter

# 2. 데이터베이스 상태 확인
python utils/db_migration.py status

# 3. 로그 확인
tail -f logs/app.log

# 4. 웹 접속 테스트
curl -I http://localhost:5000
```

## 📊 데이터베이스 관리 명령어

### 마이그레이션 관리
```bash
# 현재 상태 확인
python utils/db_migration.py status

# 마이그레이션 실행
python utils/db_migration.py migrate

# 백업 생성
python utils/db_migration.py backup
```

### 데이터베이스 동기화
```bash
# 데이터베이스 비교
python utils/db_sync.py compare

# 로컬 → 온라인 동기화
python utils/db_sync.py sync-to-remote

# 온라인 → 로컬 동기화
python utils/db_sync.py sync-to-local

# 데이터 내보내기
python utils/db_sync.py export --file backup.json

# 데이터 가져오기
python utils/db_sync.py import --file backup.json
```

## 🔍 트러블슈팅

### 배포 실패 시 복구 방법

#### 1. 백업에서 데이터 복원
```bash
# 최근 백업 파일 찾기
ls -la migration_backup_*.json

# 백업 파일에서 데이터 복원
python utils/db_sync.py import --file migration_backup_YYYYMMDD_HHMMSS.json
```

#### 2. 서비스 재시작
```bash
# systemd 서비스 재시작
sudo systemctl restart newsletter

# 또는 수동 재시작
pkill -f "python app.py"
nohup python app.py > logs/app.log 2>&1 &
```

#### 3. 로그 확인
```bash
# 애플리케이션 로그
tail -f logs/app.log

# 시스템 로그
journalctl -u newsletter -f

# nginx 로그 (있는 경우)
tail -f /var/log/nginx/error.log
```

## 📋 배포 체크리스트

### 배포 전 체크리스트
- [ ] 환경변수 설정 확인 (`ADMIN_PASSWORD`, `DATABASE_URL` 등)
- [ ] 현재 데이터베이스 상태 확인
- [ ] 중요 데이터 백업 생성
- [ ] 서비스 상태 확인
- [ ] 디스크 공간 확인

### 배포 후 체크리스트
- [ ] 서비스 정상 실행 확인
- [ ] 데이터베이스 무결성 확인
- [ ] 웹 접속 테스트
- [ ] 로그 에러 확인
- [ ] 사용자 계정 로그인 테스트
- [ ] 백업 파일 보관

## 🔐 보안 고려사항

### 1. 환경변수 보안
```bash
# 환경변수 파일 권한 설정
chmod 600 .env

# 중요 정보 환경변수 설정
export ADMIN_PASSWORD="강력한_비밀번호"
export DATABASE_URL="postgresql://user:pass@host:port/db"
```

### 2. 백업 파일 보안
```bash
# 백업 파일 권한 설정
chmod 600 *.json

# 정기적인 백업 파일 정리
find . -name "migration_backup_*.json" -mtime +30 -delete
```

### 3. 로그 파일 관리
```bash
# 로그 파일 권한 설정
chmod 640 logs/*.log

# 로그 로테이션 설정
sudo logrotate -f /etc/logrotate.d/newsletter
```

## 📅 정기적인 유지보수

### 일일 작업
```bash
# 백업 생성
python utils/db_migration.py backup

# 로그 확인
tail -100 logs/app.log | grep ERROR
```

### 주간 작업
```bash
# 데이터베이스 상태 확인
python utils/db_migration.py status

# 오래된 백업 파일 정리
find . -name "migration_backup_*.json" -mtime +7 -delete
```

### 월간 작업
```bash
# 전체 데이터베이스 백업
python utils/db_sync.py export --file monthly_backup_$(date +%Y%m).json

# 시스템 리소스 확인
df -h
free -h
```

## 🚨 응급 상황 대응

### 서비스 완전 중단 시
```bash
# 1. 서비스 강제 종료
sudo systemctl stop newsletter
pkill -9 -f "python app.py"

# 2. 백업에서 데이터 복원
python utils/db_sync.py import --file [최신_백업_파일]

# 3. 서비스 재시작
sudo systemctl start newsletter
```

### 데이터베이스 손상 시
```bash
# 1. 서비스 중지
sudo systemctl stop newsletter

# 2. 데이터베이스 파일 백업
cp app.db app.db.damaged

# 3. 백업에서 복원
python utils/db_sync.py import --file [최신_백업_파일]

# 4. 마이그레이션 재실행
python utils/db_migration.py migrate

# 5. 서비스 재시작
sudo systemctl start newsletter
```

이제 안전하고 신뢰할 수 있는 배포 프로세스를 사용할 수 있습니다! 