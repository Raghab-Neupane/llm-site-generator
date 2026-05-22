#login endpoint
from fastapi import APIRouter, HTTPException

from .schemas import LoginRequest
from .jwt_handler import create_access_token

router = APIRouter()

@router.post("/login")
def login(data:LoginRequest):
    
    if data.username != "admin" or data.password != "123456":
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials"
        )
        
    access_token = create_access_token(
        data={
            "sub":data.username
        }
    )

    return {"access_token":access_token,"token_type":"bearer"}
        