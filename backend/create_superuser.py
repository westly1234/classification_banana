# create_superuser.py

from db import SessionLocal
from models import User
from main import hash_password

db = SessionLocal()

email = "admin@banana.com"      # 관리자 이메일
password = "admin1234"          # 관리자 비밀번호
nickname = "관리자"

# 중복 체크
existing = db.query(User).filter(User.email == email).first()
if existing:
    print("⚠️ 이미 동일한 이메일이 존재합니다.")
else:
    superuser = User(
        nickname=nickname,
        email=email,
        password_hash=hash_password(password),
        is_verified=True,
        is_superuser=True
    )
    db.add(superuser)
    db.commit()
    print("✅ Superuser 계정 생성 완료:", email)

db.close()
