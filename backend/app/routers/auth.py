from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
 
from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services.auth_service import authenticate_user, register_user


router = APIRouter(prefix= "/auth", tags=["auth"])

@router.post("/register", response_model= TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        user = register_user(
            db,
            email = payload.email,
            password= payload.password,
            full_name= payload.full_name
        )
    except ValueError as e:
        raise HTTPException(status_code= status.HTTP_400_BAD_REQUEST, detail= str(e))

    token = create_access_token(subject= user.id)
    return TokenResponse(token= token, user= UserOut.model_validate(user))


@router.post("/login", response_model= TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        user, token = authenticate_user(
            db, 
            email= payload.email,
            password= payload.password
        )
    except ValueError as e:
        raise HTTPException(status_code= status.HTTP_401_UNAUTHORIZED, detail= str(e))
    return TokenResponse(token= token, user= user)

@router.get("/me", response_model= UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user

