"""
notifier.py - Generates notifications based on food freshness detections.
"""

import logging

log = logging.getLogger(__name__)


def generate_notifications(food_item_ids: list[tuple]) -> list[dict]:
    """
    food_item_ids: list of (food_id: str, detection: dict)
    Returns list of notification dicts ready for Supabase insert.
    """
    notifications = []

    for food_id, detection in food_item_ids:
        status = detection["freshness_status"]
        name = detection["name"].capitalize()
        days = detection.get("estimated_days_to_spoil", 0)
        score = detection["freshness_score"]

        if status == "spoiled":
            notifications.append({
                "food_item_id": food_id,
                "title": f"[SPOILED] {name} has spoiled!",
                "message": (
                    f"Your {name.lower()} has a freshness score of {score}/100 and appears to be spoiled. "
                    f"Please discard it to avoid food safety issues."
                ),
                "severity": "critical",
            })

        elif status == "at_risk":
            notifications.append({
                "food_item_id": food_id,
                "title": f"[WARNING] {name} expiring soon",
                "message": (
                    f"Your {name.lower()} has about {days} day(s) remaining "
                    f"(freshness score: {score}/100). Use it soon!"
                ),
                "severity": "warning",
            })

        elif status == "fresh" and days <= 3:
            notifications.append({
                "food_item_id": food_id,
                "title": f"[INFO] {name} is fresh",
                "message": (
                    f"Your {name.lower()} looks good! Estimated {days} day(s) before it expires."
                ),
                "severity": "info",
            })

    log.info(f"Generated {len(notifications)} notification(s).")
    return notifications
