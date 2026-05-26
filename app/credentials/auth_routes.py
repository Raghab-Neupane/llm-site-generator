from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta

from app.credentials.database import get_db_connection

from app.credentials.schemas import (
    SignupRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest
)

from app.credentials.security import (
    hash_password,
    verify_password
)

from app.credentials.jwt_handler import (
    create_access_token,
    verify_access_token
)

from app.credentials.mail_service import send_reset_email

router = APIRouter()


def init_db():
    """
    Self-healing initialization to ensure the password_resets table exists
    with the correct relational columns and constraints.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Check if the legacy table exists and has the 'email' column
        cursor.execute("SHOW TABLES LIKE 'password_resets'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            cursor.execute("SHOW COLUMNS FROM password_resets LIKE 'email'")
            has_email_col = cursor.fetchone()
            if has_email_col:
                print("[DB] Legacy non-relational password_resets table detected. Dropping for schema migration...")
                cursor.execute("DROP TABLE IF EXISTS password_resets")
                connection.commit()
                
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"[DB] Error checking/dropping legacy password_resets table: {e}")

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                reset_token VARCHAR(500) NOT NULL,
                expires_at DATETIME NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        connection.commit()
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"[DB] Error initializing relational password_resets table: {e}")


@router.post("/signup")
def signup(payload: SignupRequest):

    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE email = %s",
        (payload.email,)
    )

    existing_user = cursor.fetchone()

    if existing_user:

        raise HTTPException(
            status_code=400,
            detail="User already exists"
        )

    hashed_password = hash_password(
        payload.password
    )

    cursor.execute(
        """
        INSERT INTO users (
            email,
            password_hash
        )
        VALUES (%s, %s)
        """,
        (
            payload.email,
            hashed_password
        )
    )

    connection.commit()

    return {
        "message": "Signup successful"
    }


@router.post("/login")
def login(payload: LoginRequest):

    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE email = %s",
        (payload.email,)
    )

    user = cursor.fetchone()

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    password_valid = verify_password(
        payload.password,
        user["password_hash"]
    )

    if not password_valid:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    token = create_access_token({
        "user_id": user["id"],
        "email": user["email"]
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }


def process_forgot_password(payload: ForgotPasswordRequest):
    print(f"[DB] User lookup: Initiated for email: {payload.email}")
    init_db()
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # 1. Verify user exists and fetch user_id
    cursor.execute(
        "SELECT id, email FROM users WHERE email = %s",
        (payload.email,)
    )
    user = cursor.fetchone()
    if not user:
        print(f"[DB] User lookup: Failed. No user found with email: {payload.email}")
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="User with this email does not exist"
        )
    user_id = user["id"]
    print(f"[DB] User lookup: Successful. User ID: {user_id}")

    # 2. Generate secure reset token
    print(f"[AUTH] Token generation: Initiating for user ID: {user_id}")
    token = create_access_token({
        "email": user["email"],
        "type": "reset"
    })
    print("[AUTH] Token generation: Successful")

    # 3. Store token in relational password_resets table
    expires_at = datetime.utcnow() + timedelta(minutes=60)
    print(f"[DB] Token insert: Storing reset token for user ID {user_id} (Expires at: {expires_at})")
    try:
        cursor.execute(
            "INSERT INTO password_resets (user_id, reset_token, expires_at) VALUES (%s, %s, %s)",
            (user_id, token, expires_at)
        )
        connection.commit()
        print("[DB] Token insert: Successful")
    except Exception as e:
        print(f"[DB] Token insert: Failed: {e}")
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=500,
            detail=f"Database error storing reset token: {e}"
        )

    # 4. Send email via Mailpit using send_reset_email()
    reset_link = f"http://localhost:5174/reset-password?token={token}"
    print(f"[MAIL] Mail sending: Dispatching password reset email to: {user['email']}")
    try:
        send_reset_email(user["email"], reset_link)
    except Exception as e:
        # Clean up database entry if sending failed
        print(f"[MAIL] Mail sending: Failed: {e}. Cleaning up database record.")
        try:
            cursor.execute("DELETE FROM password_resets WHERE reset_token = %s", (token,))
            connection.commit()
        except Exception:
            pass
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=503,
            detail="Mail delivery service (Mailpit) is unavailable. Please make sure Mailpit is running on port 1025."
        )

    cursor.close()
    connection.close()

    return {
        "message": "Reset email sent successfully"
    }


@router.post("/resetlogin")
def resetlogin(payload: ForgotPasswordRequest):
    return process_forgot_password(payload)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    return process_forgot_password(payload)


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest):
    try:
        decoded = verify_access_token(payload.token)
        if decoded.get("type") != "reset":
            raise HTTPException(
                status_code=400,
                detail="Invalid token type"
            )
        email = decoded.get("email")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired reset token"
        )

    init_db()
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Verify that the token exists in relational password_resets table and has not expired
    current_time = datetime.utcnow()
    cursor.execute(
        """
        SELECT pr.*, u.email 
        FROM password_resets pr
        JOIN users u ON pr.user_id = u.id
        WHERE u.email = %s AND pr.reset_token = %s AND pr.expires_at > %s
        """,
        (email, payload.token, current_time)
    )
    reset_record = cursor.fetchone()
    if not reset_record:
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="Reset token is invalid, expired, or has already been used"
        )

    # Verify user still exists
    cursor.execute(
        "SELECT * FROM users WHERE email = %s",
        (email,)
    )
    user = cursor.fetchone()
    if not user:
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="User not found"
        )

    # Update password and hash it
    hashed = hash_password(payload.new_password)
    cursor.execute(
        "UPDATE users SET password_hash = %s WHERE email = %s",
        (hashed, email)
    )

    # Delete the used token so it cannot be used again
    cursor.execute(
        "DELETE FROM password_resets WHERE user_id = %s AND reset_token = %s",
        (reset_record["user_id"], payload.token)
    )

    connection.commit()
    cursor.close()
    connection.close()

    return {
        "message": "Password reset successful"
    }