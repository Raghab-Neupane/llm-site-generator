#Pydantic login request models
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str