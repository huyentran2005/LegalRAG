from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User



def register_user(db:Session, email: str, password: str, full_name: str|None) -> User:

    existing = db.query(User).filter(User.email == email).first()

    if existing is not None:
        raise ValueError("Email này đã được đăng ký.")

    user = User(
        email = email,
        hashed_password = hash_password(password),
        full_name = full_name
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Email này đã được đăng ký.")

    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> tuple[User, str]:
    user = db.query(User).filter(User.email == email).first()

    if user is None or not verify_password(password, user.hashed_password):
        raise ValueError("Email hoặc mật khẩu không đúng.")

    if not user.is_active:
        raise ValueError("Tài khoản bị khóa. Vui lòng liên hệ quản trị viên.")

    token = create_access_token(subject= user.id) # type: ignore
    return user, token # type: ignore