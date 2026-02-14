"""
Login Page Module
Renders login UI
"""

import streamlit as st
import time
from utils.auth_manager import AuthManager
from datetime import datetime, timedelta

def render_login_page(auth_manager: AuthManager, cookie_manager):
    """
    Render login page
    
    Args:
        auth_manager: AuthManager instance
        cookie_manager: CookieManager instance
    """
    # Custom CSS for login page
    st.markdown("""
    <style>
        /* Header styling */
        .login-header {
            text-align: center;
            margin-bottom: 10px;
        }
        
        .login-title {
            font-size: 18px;
            color: #333;
            margin: 0;
        }
        
        .login-subtitle {
            font-size: 14px;
            color: #666;
            margin: 5px 0 30px 0;
        }
        
        /* Form styling */
        .stTextInput > label {
            font-size: 14px;
            font-weight: 500;
            color: #333;
        }
        
        /* Button styling */
        .stButton > button {
            width: 100%;
            background-color: #1E88E5;
            color: white;
            font-weight: 600;
            border-radius: 8px;
            padding: 12px;
            border: none;
            font-size: 16px;
        }
        
        .stButton > button:hover {
            background-color: #1565C0;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Logo and Title (Outside columns for full width centering)
    st.markdown("""
    <div style="text-align: center; padding-top: 5vh; padding-bottom: 2rem;">
        <h1 style="font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem;">🏗️ 인텔리전트 다큐먼트</h1>
        <p style="font-size: 1.2rem; color: #666;">RAG 기반 지능형 문서 분석 시스템</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Use columns to center the login form
    _, col_center, _ = st.columns([1, 1.5, 1])
    
    with col_center:
        with st.form("login_form", clear_on_submit=False):
            # Initialize session state for login form defaults if not present
            if "login_form_defaults" not in st.session_state:
                st.session_state.login_form_defaults = {"email": "", "password": ""}
                st.session_state.cookies_checked = False

            # Attempt to get saved credentials only once to prevent infinite re-renders
            if not st.session_state.get("cookies_checked", False):
                try:
                    # Use unique keys for get calls just in case (though get doesn't typically need them like set)
                    saved_email = cookie_manager.get("remember_email")
                    saved_password = cookie_manager.get("remember_password")
                    
                    if saved_email:
                        st.session_state.login_form_defaults["email"] = saved_email
                    if saved_password:
                        st.session_state.login_form_defaults["password"] = saved_password
                    
                    # Mark as checked so we don't call get() again this session
                    st.session_state.cookies_checked = True
                    
                    # If we found data, we might need a rerun to update the UI immediately
                    # But since we use st.session_state in widgets, it should reflect on next script run
                    # A rerun here ensures the fields populate instantly if they were just fetched
                    if saved_email or saved_password:
                        time.sleep(0.1)
                        st.rerun()
                        
                except Exception as e:
                    print(f"Cookie read error: {e}")
                    # Mark as checked to prevent retry loop on error
                    st.session_state.cookies_checked = True

            default_email = st.session_state.login_form_defaults["email"]
            default_password = st.session_state.login_form_defaults["password"]
            
            email = st.text_input("이메일", value=default_email, placeholder="example@email.com")
            password = st.text_input("비밀번호", value=default_password, type="password", placeholder="비밀번호를 입력하세요")
            
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("로그인", use_container_width=True, type="primary")
            
            if submitted:
                if not email or not password:
                    st.error("이메일과 비밀번호를 입력해주세요.")
                else:
                    with st.spinner("인증 중..."):
                        success, user_info, message = auth_manager.login(email, password)
                        
                        if success:
                            st.session_state.is_logged_in = True
                            st.session_state.user_info = user_info
                            
                            # Set auto-login cookie (expires in 7 days)
                            expires = datetime.now() + timedelta(days=7)
                            cookie_manager.set("auth_email", email, expires_at=expires, key="set_auth_email")
                            
                            # Set persistent remember-me cookies (expires in 30 days)
                            # These allow the form to be pre-filled even if auto-login fails or user logged out
                            remember_expires = datetime.now() + timedelta(days=30)
                            cookie_manager.set("remember_email", email, expires_at=remember_expires, key="set_rem_email")
                            cookie_manager.set("remember_password", password, expires_at=remember_expires, key="set_rem_pass")
                            
                            st.success(message)
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(message)
        
        st.markdown("""
        <p style="text-align: center; color: #6c757d; font-size: 0.9rem; margin-top: 1rem;">
            ℹ️ 계정 생성 및 비밀번호 초기화는 관리자에게 문의하세요.
        </p>
        """, unsafe_allow_html=True)


