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

   