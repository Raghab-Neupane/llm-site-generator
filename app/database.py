import mysql.connector


db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="llm_generator_db"
)


cursor = db.cursor(dictionary=True)