import mysql.connector
from mysql.connector import Error

def get_db_connection():

    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="llm_generator_db"
    )

    return connection