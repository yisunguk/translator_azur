"""
Authentication Manager (Secrets-based)
Handles user authentication using Streamlit Secrets
"""

import streamlit as st
from typing import Optional, Tuple, Dict

from utils.permission_manager import PermissionManager

class AuthManager:
    def __init__(self, connection_string: str = None):
        # Load users from secrets
        self.users = self._load_users()
        # Initialize PermissionManager if connection string is provided
        self.permission_manager = PermissionManager(connection_string) if connection_string else None
    
    def _load_users(self) -> Dict:
        """Load users from st.secrets"""
        try:
            return st.secrets.get("auth_users", {})
        except FileNotFoundError:
            return {}
        except Exception:
            return {}
            
    def _get_effective_permissions(self, email: str, default_permissions: list) -> list:
        """Get effective permissions (Blob storage overrides secrets)"""
        if self.permission_manager:
            dynamic_perms = self.permission_manager.get_user_permissions(email)
            if dynamic_perms:
                return dynamic_perms
        return default_permissions
    
    def login(self, email: str, password: str) -> Tuple[bool, Optional[Dict], str]:
        """
        Authenticate user against secrets
        """
        # Iterate through users in secrets to find matching email
        input_email = email.strip().lower()
        
        for username, user_data in self.users.items():
            stored_email = str(user_data.get("email", "")).strip().lower()
            
            if stored_email == input_email:
                # Check password (exact match required)
                # Handle both string and integer passwords from secrets
                stored_password = str(user_data.get("password", ""))
                if stored_password == str(password):
                    # Login Success
                    # Get permissions from blob if available, else use secrets
                    base_perms = user_data.get('permissions', [])
                    effective_perms = self._get_effective_permissions(stored_email, base_perms)
                    
                    user_info = {
                        'id': username,  # Use key as ID
                        'email': user_data['email'],
                        'name': user_data['name'],
                        'role': user_data.get('role', 'user'),
                        'permissions': effective_perms
                    }
                    return True, user_info, f"환영합니다, {user_data['name']}님!"
                else:
                    return False, None, "비밀번호가 올바르지 않습니다."
        
        return False, None, "등록되지 않은 이메일입니다."
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user information by email"""
        input_email = email.strip().lower()
        for username, user_data in self.users.items():
            stored_email = str(user_data.get("email", "")).strip().lower()
            if stored_email == input_email:
                base_perms = user_data.get('permissions', [])
                effective_perms = self._get_effective_permissions(stored_email, base_perms)
                
                return {
                    'id': username,
                    'email': user_data['email'],
                    'name': user_data['name'],
                    'role': user_data.get('role', 'user'),
                    'permissions': effective_perms
                }
        return None
    
    def get_all_users(self) -> list:
        """Get all users (admin only)"""
        users_list = []
        for username, user_data in self.users.items():
            email = str(user_data.get("email", "")).strip().lower()
            base_perms = user_data.get('permissions', [])
            effective_perms = self._get_effective_permissions(email, base_perms)
            
            users_list.append({
                'id': username,
                'email': user_data['email'],
                'name': user_data['name'],
                'role': user_data.get('role', 'user'),
                'permissions': effective_perms
            })
        return users_list

    def update_user_permissions(self, email: str, permissions: list) -> Tuple[bool, str]:
        """Update user permissions in Blob Storage"""
        if not self.permission_manager:
            return False, "권한 관리자가 초기화되지 않았습니다 (Azure 연결 문자열 누락)."
            
        if self.permission_manager.set_user_permissions(email, permissions):
            return True, "권한이 업데이트되었습니다."
        else:
            return False, "권한 저장 중 오류가 발생했습니다."
