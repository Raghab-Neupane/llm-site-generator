# create and verify JWT tokens
from datetime import datetime, timedelta
from jose import jwt

SECRET_KEY = "41a7eb9014160d87af2f0677a1f55d4824dfc78204487f784d00f20548eb425d"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict):

    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta (
        minutes= ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
    
    