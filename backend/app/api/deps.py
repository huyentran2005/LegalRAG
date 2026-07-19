from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error= False)

def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    print("TOKEN =", token)
    credentials_error = HTTPException(
        status_code= status.HTTP_401_UNAUTHORIZED,
        detail = "Không thể xác minh phiên đăng nhập.",
        headers= {"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_error
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_error

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise credentials_error

    return user