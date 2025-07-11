#!/usr/bin/env python3
"""
관리자 계정 정보 확인 스크립트
현재 설정된 관리자 정보를 확인할 때 사용하세요.

사용법:
python show_admin_info.py
"""

from app import app
from models import User

def show_admin_info():
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        
        if not admin:
            print("❌ Admin 사용자를 찾을 수 없습니다.")
            return
        
        print("👤 관리자 계정 정보")
        print("=" * 30)
        print(f"사용자명: {admin.username}")
        print(f"이메일: {admin.email}")
        print(f"관리자 권한: {'예' if admin.is_admin else '아니오'}")
        print(f"계정 생성일: {admin.created_at}")
        print(f"비밀번호 해시: {admin.password_hash[:30]}...")
        print()
        # 실제 비밀번호 확인
        import os
        admin_password = os.getenv('ADMIN_PASSWORD')
        if not admin_password:
            print("💡 현재 비밀번호: CHANGE_ME_IMMEDIATELY_123!")
            print("   (⚠️ 임시 비밀번호입니다. 보안상 변경을 권장합니다)")
        else:
            print("💡 현재 비밀번호: [환경변수에서 설정된 비밀번호]")
            print("   (비밀번호를 변경했다면 변경된 비밀번호를 사용하세요)")
        print()
        print("🔄 비밀번호 재설정이 필요하면:")
        print("   python reset_admin_password.py")

if __name__ == "__main__":
    show_admin_info() 