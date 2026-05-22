import os
import sys
import mysql.connector
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "llm_generator_db")

db = None
cursor = None

try:
    db = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = db.cursor(dictionary=True)
    print("Database connection successfully established.")
except mysql.connector.Error as err:
    print(f"Error: Connection to MySQL Database failed. Details: {err}", file=sys.stderr)
    print("Warning: The application will run without database connection. Features requiring DB will be unavailable.", file=sys.stderr)