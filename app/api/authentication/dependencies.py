# reusable protected-route verification
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredintials
from jose import jwt, JWTError

from .jwt_handler import SECRET_KEY, ALGORITHM

security = HTTPBearer()

def verify_token(
    credintials : HTTPAuthorizationCredintials = Depends(security)
):
    token = credintials.credentials

    try: 

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        return payload
    
    except JWTError:

        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials"
        )