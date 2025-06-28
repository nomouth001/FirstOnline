#!/usr/bin/env python3
"""
관리자 비밀번호 재설정 스크립트
비밀번호를 까먹었을 때 사용하세요.

사용법:
python reset_admin_password.py
"""

from app import app, db
from models import User
from werkzeug.security import generate_password_hash
import getpass

def reset_admin_password():
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        
        if not admin:
            print("❌ Admin 사용자를 찾을 수 없습니다.")
            return
        
        print("🔐 관리자 비밀번호 재설정")
        print(f"현재 관리자: {admin.username} ({admin.email})")
        print()
        
        # 새 비밀번호 입력
        while True:
            new_password = getpass.getpass("새 비밀번호를 입력하세요: ")
            if len(new_password) < 6:
                print("❌ 비밀번호는 최소 6자 이상이어야 합니다.")
                continue
                
            confirm_password = getpass.getpass("비밀번호를 다시 입력하세요: ")
            if new_password != confirm_password:
                print("❌ 비밀번호가 일치하지 않습니다.")
                continue
            break
        
        # 비밀번호 변경
        admin.password_hash = generate_password_hash(new_password)
        
        try:
            db.session.commit()
            print("✅ 관리자 비밀번호가 성공적으로 변경되었습니다!")
            print(f"사용자명: {admin.username}")
            print("새 비밀번호로 로그인하세요.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ 비밀번호 변경 실패: {e}")

if __name__ == "__main__":
    reset_admin_password() 