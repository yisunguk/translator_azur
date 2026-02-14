"""
Permission Manager
Handles loading and saving user permissions using Azure Blob Storage
"""

import json
from azure.storage.blob import BlobServiceClient
from typing import Dict, List

class PermissionManager:
    def __init__(self, connection_string: str, container_name: str = "config"):
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_name = container_name
        self.blob_name = "permissions.json"
        self._ensure_container()
        
    def _ensure_container(self):
        """Ensure the configuration container exists"""
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            if not container_client.exists():
                container_client.create_container()
        except Exception as e:
            print(f"Error ensuring container: {e}")

    def load_permissions(self) -> Dict[str, List[str]]:
        """Load permissions from blob storage"""
        try:
            blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=self.blob_name)
            if blob_client.exists():
                download_stream = blob_client.download_blob()
                data = download_stream.readall()
                return json.loads(data)
            return {}
        except Exception as e:
            print(f"Error loading permissions: {e}")
            return {}

    def save_permissions(self, permissions_data: Dict[str, List[str]]) -> bool:
        """Save permissions to blob storage"""
        try:
            blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=self.blob_name)
            data = json.dumps(permissions_data, ensure_ascii=False, indent=2)
            blob_client.upload_blob(data, overwrite=True)
            return True
        except Exception as e:
            print(f"Error saving permissions: {e}")
            return False

    def get_user_permissions(self, email: str) -> List[str]:
        """Get permissions for a specific user"""
        all_perms = self.load_permissions()
        return all_perms.get(email, [])

    def set_user_permissions(self, email: str, permissions: List[str]) -> bool:
        """Set permissions for a specific user"""
        all_perms = self.load_permissions()
        all_perms[email] = permissions
        return self.save_permissions(all_perms)
