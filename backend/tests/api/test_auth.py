# Function to generate JWT token
import datetime

import jwt

from api.app import maybe_get_current_user
from common.config import GOTRUE_JWT_SECRET


def create_test_jwt():
    payload = {
        "sub": "1234567890",  # Example user ID (you can replace with a valid user ID)
        "email": "test@example.com",  # Example email
        "user_metadata": {
            "username": "testuser"
        },
        "aud": "authenticated",  # Audience
        "iat": datetime.datetime.utcnow(),  # Issued at time
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=30),  # Expiration time
    }

    token = jwt.encode(payload, GOTRUE_JWT_SECRET, algorithm="HS256")
    return token


def test_maybe_get_current_user():
    token = create_test_jwt()
    # useful if you need to pass it into Curl or Postman
    print("Token: ", token)

    current_user = maybe_get_current_user(access_token=token)
    assert current_user.email == "test@example.com"
