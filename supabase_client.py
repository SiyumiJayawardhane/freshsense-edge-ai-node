"""
supabase_client.py - Handles all database operations via direct PostgreSQL
connection using psycopg2. No supabase-py SDK needed.
"""

import os
import logging
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from datetime import datetime

log = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self):
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise EnvironmentError("DATABASE_URL must be set in .env")

        self.conn = psycopg2.connect(database_url)
        self.conn.autocommit = True
        self._sensor_columns: set[str] | None = None
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

    def insert_food_item(self, user_id: str, detection: dict, sensor_data: dict) -> str:
        """
        Inserts a food_items row unless the same user+name+freshness_status
        already exists. Returns the food item UUID.
        """
        now = datetime.utcnow().isoformat()

        with self._cursor() as cur:
            image_url = detection.get("image_url")
            cur.execute(
                """
                SELECT id
                FROM public.food_items
                WHERE user_id = %s
                  AND name = %s
                  AND freshness_status = %s
                LIMIT 1
                """,
                (user_id, detection["name"], detection["freshness_status"]),
            )
            existing = cur.fetchone()

            if existing:
                food_id = str(existing["id"])
                cur.execute(
                    """
                    UPDATE public.food_items SET
                        category = %s,
                        image_url = %s,
                        freshness_score = %s,
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
                        detection["confidence"],
                        detection["estimated_days_to_spoil"],
                        detection["storage_tips"],
                        now,
                        now,
                        food_id,
                    ),
                )
                log.info(
                    "Updated existing food_item: %s status=%s (%s)",
                    detection["name"],
                    detection["freshness_status"],
                    food_id,
                )
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
                log.info(
                    "Inserted new food_item: %s status=%s (%s)",
                    detection["name"],
                    detection["freshness_status"],
                    food_id,
                )

        return food_id

    def upsert_food_item(self, user_id: str, detection: dict, sensor_data: dict) -> str:
        """
        Backward-compatible alias. Behavior is insert-only.
        """
        return self.insert_food_item(user_id, detection, sensor_data)

    # ── Sensor Readings ────────────────────────────────────────────────────────

    def _get_sensor_columns(self) -> set[str]:
        if self._sensor_columns is not None:
            return self._sensor_columns
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'sensor_readings'
                """
            )
            self._sensor_columns = {row["column_name"] for row in cur.fetchall()}
        return self._sensor_columns

    @staticmethod
    def _pick_column(columns: set[str], options: list[str]) -> str | None:
        for name in options:
            if name in columns:
                return name
        return None

    def insert_sensor_reading(self, user_id: str, food_item_id: str, sensor_data: dict):
        """Logs one sensor reading row linked to a food item."""
        cols = self._get_sensor_columns()

        mq3_col = self._pick_column(cols, ["mq3_gas_value", "MQ3_gas_value"])
        mq135_col = self._pick_column(cols, ["mq135_gas_value", "MQ135_gas_value", "mq35_gas_value", "MQ35_gas_value"])
        legacy_col = self._pick_column(cols, ["gas_value"])

        # Accept multiple incoming key styles to avoid null writes.
        mq3_value = sensor_data.get("mq3_gas_value")
        if mq3_value is None:
            mq3_value = sensor_data.get("mq3_model_value")
        if mq3_value is None:
            mq3_value = sensor_data.get("mq3")

        mq135_value = sensor_data.get("mq135_gas_value")
        if mq135_value is None:
            mq135_value = sensor_data.get("mq135_model_value")
        if mq135_value is None:
            mq135_value = sensor_data.get("mq135")
        if mq135_value is None:
            mq135_value = sensor_data.get("gas_value")

        base_columns = ["user_id", "food_item_id", "humidity", "temperature", "recorded_at"]
        base_values = [
            user_id,
            food_item_id,
            sensor_data.get("humidity"),
            sensor_data.get("temperature"),
            datetime.utcnow().isoformat(),
        ]

        if mq3_col:
            base_columns.append(mq3_col)
            base_values.append(mq3_value)
        if mq135_col:
            base_columns.append(mq135_col)
            base_values.append(mq135_value)
        if (not mq3_col or not mq135_col) and legacy_col:
            # Keep backward compatibility with old single gas column.
            fallback_gas = mq135_value if mq135_value is not None else mq3_value
            base_columns.append(legacy_col)
            base_values.append(fallback_gas)

        if not mq3_col and not mq135_col and not legacy_col:
            log.warning(
                "No gas columns detected in sensor_readings. Available columns: %s",
                sorted(cols),
            )

        log.info(
            "Sensor insert mapping -> mq3_col=%s mq3_value=%s | mq135_col=%s mq135_value=%s | legacy_col=%s",
            mq3_col,
            mq3_value,
            mq135_col,
            mq135_value,
            legacy_col,
        )

        identifier_list = [sql.Identifier(col) for col in base_columns]
        placeholder_list = [sql.Placeholder()] * len(base_columns)
        query = sql.SQL("INSERT INTO public.sensor_readings ({}) VALUES ({})").format(
            sql.SQL(", ").join(identifier_list),
            sql.SQL(", ").join(placeholder_list),
        )

        with self._cursor() as cur:
            cur.execute(query, tuple(base_values))

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

    # ── Maintenance ────────────────────────────────────────────────────────────

    def cleanup_tables(self, table_names: list[str]) -> int:
        """
        Deletes all rows from the requested public tables.
        Ignores protected tables like profiles.
        Returns number of tables cleaned.
        """
        protected_tables = {"profiles"}
        requested = [t.strip() for t in table_names if t and t.strip()]
        cleaned = [t for t in requested if t not in protected_tables]
        skipped = [t for t in requested if t in protected_tables]

        if skipped:
            log.warning("Skipping protected tables during cleanup: %s", skipped)
        if not cleaned:
            log.info("Cleanup skipped: no eligible tables configured")
            return 0

        identifiers = [sql.SQL("public.{}").format(sql.Identifier(name)) for name in cleaned]
        query = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(identifiers)
        )
        with self._cursor() as cur:
            cur.execute(query)
        log.info("Cleanup complete for tables: %s", cleaned)
        return len(cleaned)

    def close(self):
        self.conn.close()
        log.info("DB connection closed.")
