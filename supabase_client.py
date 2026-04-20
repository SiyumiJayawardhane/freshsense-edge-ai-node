"""
supabase_client.py - Handles all database operations via direct PostgreSQL
connection using psycopg2. No supabase-py SDK needed.
"""

import os
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime

log = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self):
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise EnvironmentError("DATABASE_URL must be set in .env")

        self.conn = psycopg2.connect(database_url)
        self.conn.autocommit = True
        log.info("PostgreSQL connection established.")

    def _cursor(self):
        """Returns a cursor, reconnecting if the connection dropped."""
        try:
            self.conn.isolation_level  # cheap check
        except Exception:
            log.warning("DB connection lost — reconnecting...")
            self.conn = psycopg2.connect(os.getenv("DATABASE_URL"))
            self.conn.autocommit = True
        return self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    

    def close(self):
        self.conn.close()
        log.info("DB connection closed.")
