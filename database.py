import os  # Import the os module
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Load environment variables from .env file (even if you are not using .env, Railway will provide the variables)
PGUSER = os.getenv('PGUSER')
PGPASSWORD = os.getenv('POSTGRES_PASSWORD')  # Update to POSTGRES_PASSWORD
PGHOST = os.getenv('PGHOST')
PGDATABASE = os.getenv('PGDATABASE')
PGPORT = os.getenv('PGPORT')

def connect_db():
    """Establish a connection to the PostgreSQL database."""
    try:
        logging.debug("Connecting to the database with the following settings:")
        logging.debug(f"PGUSER: {PGUSER}")
        logging.debug(f"PGPASSWORD: {'******' if PGPASSWORD else 'None'}")
        logging.debug(f"PGHOST: {PGHOST}")
        logging.debug(f"PGDATABASE: {PGDATABASE}")
        logging.debug(f"PGPORT: {PGPORT}")
        
        conn = psycopg2.connect(
            user=PGUSER,
            password=PGPASSWORD,
            host=PGHOST,
            database=PGDATABASE,
            port=PGPORT,
            cursor_factory=DictCursor
        )
        logging.debug("Database connection established successfully")
        return conn
    except psycopg2.Error as e:
        logging.error(f"Error connecting to database: {e}")
        return None

def create_user_downloads_table(conn):
    """Create the user_downloads table if it doesn't exist."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_downloads (
                user_id BIGINT PRIMARY KEY,
                download_count INTEGER NOT NULL,
                last_download_date DATE NOT NULL
            )
        """)
        conn.commit()
        logging.debug("Table user_downloads created successfully")
    except psycopg2.Error as e:
        logging.error(f"Error creating user_downloads table: {e}")

def ensure_user_in_db(conn, user_id):
    """Ensure the user exists in the database."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_downloads (user_id, download_count, last_download_date)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, 0, datetime.now().date()))
        conn.commit()
        logging.debug(f"User {user_id} ensured in the database")
    except psycopg2.Error as e:
        logging.error(f"Error ensuring user in database: {e}")

def get_download_count(conn, user_id):
    """Get the download count for a user."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT download_count FROM user_downloads WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        logging.debug(f"Download count for user {user_id}: {result['download_count'] if result else 0}")
        return result['download_count'] if result else 0
    except psycopg2.Error as e:
        logging.error(f"Error getting download count: {e}")
        return 0

def increment_download_count(conn, user_id):
    """Increment the download count for a user."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_downloads
            SET download_count = download_count + 1,
                last_download_date = %s
            WHERE user_id = %s
        """, (datetime.now().date(), user_id))
        conn.commit()
        logging.debug(f"Incremented download count for user {user_id}")
    except psycopg2.Error as e:
        logging.error(f"Error incrementing download count: {e}")

def reset_database():
    """Reset the user_downloads table in the database."""
    try:
        conn = connect_db()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS user_downloads")
        create_user_downloads_table(conn)
        conn.close()
        logging.debug("Database reset successfully")
        return True
    except psycopg2.Error as e:
        logging.error(f"Error resetting database: {e}")
        return False
