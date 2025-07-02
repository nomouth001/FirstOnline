#!/usr/bin/env python3
"""
AWS 서버의 시간대 정보를 확인하는 스크립트
"""

import datetime
import time
import os
import subprocess

def check_timezone_info():
    """시간대 관련 정보를 종합적으로 확인"""
    
    print("=" * 60)
    print("🌍 AWS 서버 시간대 정보 확인")
    print("=" * 60)
    
    # 1. Python datetime 정보
    print("\n📅 Python datetime 정보:")
    now = datetime.datetime.now()
    utc_now = datetime.datetime.utcnow()
    
    print(f"로컬 시간: {now}")
    print(f"UTC 시간: {utc_now}")
    print(f"시간 차이: {now - utc_now}")
    
    # 2. time 모듈 정보
    print("\n⏰ time 모듈 정보:")
    print(f"time.timezone: {time.timezone} 초")
    print(f"time.tzname: {time.tzname}")
    print(f"time.daylight: {time.daylight}")
    if hasattr(time, 'altzone'):
        print(f"time.altzone: {time.altzone} 초")
    
    # 3. 환경 변수 확인
    print("\n🔧 환경 변수:")
    tz_env = os.environ.get('TZ')
    print(f"TZ 환경변수: {tz_env if tz_env else '설정되지 않음'}")
    
    # 4. 시스템 명령어로 확인 (Linux에서만 동작)
    print("\n🖥️  시스템 시간대 정보:")
    try:
        # date 명령어
        result = subprocess.run(['date'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"date 명령어: {result.stdout.strip()}")
        else:
            print(f"date 명령어 실패: {result.stderr.strip()}")
    except Exception as e:
        print(f"date 명령어 실행 불가: {e}")
    
    try:
        # 시간대 파일 확인
        if os.path.exists('/etc/timezone'):
            with open('/etc/timezone', 'r') as f:
                timezone_file = f.read().strip()
            print(f"/etc/timezone: {timezone_file}")
        else:
            print("/etc/timezone: 파일 없음")
    except Exception as e:
        print(f"/etc/timezone 읽기 실패: {e}")
    
    try:
        # localtime 링크 확인
        if os.path.islink('/etc/localtime'):
            link_target = os.readlink('/etc/localtime')
            print(f"/etc/localtime -> {link_target}")
        else:
            print("/etc/localtime: 심볼릭 링크 아님")
    except Exception as e:
        print(f"/etc/localtime 확인 실패: {e}")
    
    # 5. 한국시간과의 차이 계산
    print("\n🇰🇷 한국시간과의 비교:")
    try:
        import pytz
        
        # 현재 시간을 한국 시간대로 변환
        korea_tz = pytz.timezone('Asia/Seoul')
        utc_tz = pytz.UTC
        
        current_utc = utc_tz.localize(datetime.datetime.utcnow())
        current_korea = current_utc.astimezone(korea_tz)
        
        print(f"한국 시간: {current_korea}")
        print(f"UTC 시간: {current_utc}")
        
    except ImportError:
        print("pytz 모듈이 설치되지 않음. 대략적 계산:")
        korea_offset = datetime.timedelta(hours=9)
        korea_time = utc_now + korea_offset
        print(f"한국 시간 (대략): {korea_time}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    check_timezone_info() 