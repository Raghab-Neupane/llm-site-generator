from fastapi import Header, HTTPException

from app.credentials.jwt_handler import (
    verify_access_token
)


def get_current_user(
    authorization: str = Header(None)
):

    if not authorization:

        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )

    token = authorization.replace(
        "Bearer ",
        ""
    )

    try:

        payload = verify_access_token(
            token
        )

        return payload

    except:

        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )