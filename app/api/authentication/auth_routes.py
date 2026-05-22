from fastapi import APIRouter, HTTPException

from .schemas import LoginRequest
from .jwt_handler import create_access_token
from app.database import cursor


router = APIRouter()


@router.post("/login")
def login(data: LoginRequest):

    if cursor is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection is currently unavailable. Please verify your backend configurations."
        )

    query = """
        SELECT * FROM users
        WHERE email = %s
        AND password = %s
    """

    values = (
        data.username,
        data.password
    )

    cursor.execute(query, values)

    user = cursor.fetchone()

    print(user)

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    access_token = create_access_token(
        data={
            "sub": user["email"],
            "user_id": user["id"]
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }