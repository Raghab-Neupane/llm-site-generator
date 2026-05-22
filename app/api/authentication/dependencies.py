# reusable protected-route verification
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from .jwt_handler import SECRET_KEY, ALGORITHM

security = HTTPBearer()

def verify_token(
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try: 

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        return payload
    
    except JWTError:

        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials"
        )