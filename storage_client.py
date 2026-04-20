"""
storage_client.py - Uploads food images to Supabase Storage (food-images bucket)
using the Supabase Storage REST API directly. No supabase-py SDK needed.
"""

import os
import logging
import requests

log = logging.getLogger(__name__)


class StorageClient:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not self.supabase_url or not self.service_role_key:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env for image uploads."
            )

        self.bucket = "food-images"
        self.base_url = f"{self.supabase_url}/storage/v1/object"
        self.headers = {
            "Authorization": f"Bearer {self.service_role_key}",
        }

    def upload_image(self, user_id: str, image_path: str, food_name: str) -> str | None:
        """
        Uploads a food image to Supabase Storage.
        Path format: food-images/{user_id}/{food_name}_{timestamp}.jpg

        Returns the public URL of the uploaded image, or None on failure.
        """
        import time
        timestamp = int(time.time())
        filename = f"{food_name}_{timestamp}.jpg"
        storage_path = f"{user_id}/{filename}"

        
        except Exception as e:
            log.warning(f"Image upload error: {e}")
            return None
