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

    # ── Food Items ─────────────────────────────────────────────────────────────

    def upsert_food_item(self, user_id: str, detection: dict, sensor_data: dict) -> str:
        """
        Upserts a food_items row for this user+name combo.
        Returns the food item UUID.
        """
        now = datetime.utcnow().isoformat()

        with self._cursor() as cur:
            cur.execute(
                "SELECT id FROM public.food_items WHERE user_id = %s AND name = %s LIMIT 1",
                (user_id, detection["name"])
            )
            existing = cur.fetchone()

            image_url = detection.get("image_url")

            if existing:
                food_id = str(existing["id"])
                cur.execute(
                    """
                    UPDATE public.food_items SET
                        category = %s,
                        image_url = %s,
                        freshness_score = %s,
                        freshness_status = %s,
                        confidence = %s,
                        estimated_days_to_spoil = %s,
                        storage_tips = %s,
                        detected_at = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        detection["category"],
                        image_url,
                        detection["freshness_score"],
                        detection["freshness_status"],
                        detection["confidence"],
                        detection["estimated_days_to_spoil"],
                        detection["storage_tips"],
                        now, now, food_id,
                    )
                )
                log.info(f"Updated food_item: {detection['name']} ({food_id})")
            else:
                cur.execute(
                    """
                    INSERT INTO public.food_items
                        (user_id, name, category, image_url, freshness_score, freshness_status,
                         confidence, estimated_days_to_spoil, storage_tips,
                         detected_at, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        user_id, detection["name"], detection["category"],
                        image_url,
                        detection["freshness_score"], detection["freshness_status"],
                        detection["confidence"], detection["estimated_days_to_spoil"],
                        detection["storage_tips"], now, now, now,
                    )
                )
                food_id = str(cur.fetchone()["id"])
                log.info(f"Inserted food_item: {detection['name']} ({food_id})")

        return food_id

    # ── Sensor Readings ────────────────────────────────────────────────────────

    def insert_sensor_reading(self, user_id: str, food_item_id: str, sensor_data: dict):
        """Logs one sensor reading row linked to a food item."""
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.sensor_readings
                    (user_id, food_item_id, humidity, temperature, gas_value, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, food_item_id,
                    sensor_data.get("humidity"),
                    sensor_data.get("temperature"),
                    sensor_data.get("gas_value"),
                    datetime.utcnow().isoformat(),
                )
            )

    # ── Notifications ──────────────────────────────────────────────────────────

    def insert_notification(self, user_id: str, notif: dict):
        """Inserts a notification row."""
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.notifications
                    (user_id, food_item_id, title, message, severity, is_read, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, notif.get("food_item_id"),
                    notif["title"], notif["message"],
                    notif["severity"], False,
                    datetime.utcnow().isoformat(),
                )
            )

    def close(self):
        self.conn.close()
        log.info("DB connection closed.")
