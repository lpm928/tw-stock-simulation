import json
import os
import hashlib
import streamlit as st

USER_DB_FILE = "users.json"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USER_DB_FILE):
        return {}
    try:
        with open(USER_DB_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USER_DB_FILE, "w", encoding='utf-8') as f:
        json.dump(users, f)

def login_user(username, password):
    users = load_users()
    if username in users:
        if users[username] == hash_password(password):
            return True
    return False

def register_user(username, password):
    users = load_users()
    if username in users:
        return False, "帳號已存在"
    
    users[username] = hash_password(password)
    save_users(users)
    return True, "註冊成功，請登入"

def render_login_ui():
    st.title("🔐 平台登入")
    
    tab1, tab2 = st.tabs(["登入", "註冊新帳號"])
    
    with tab1:
        u = st.text_input("帳號", key="l_u")
        p = st.text_input("密碼", type="password", key="l_p")
        if st.button("登入"):
            if login_user(u, p):
                st.session_state['logged_in'] = True
                st.session_state['username'] = u
                st.success("登入成功！")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤")
                
    with tab2:
        nu = st.text_input("新帳號", key="r_u")
        np = st.text_input("新密碼", type="password", key="r_p")
        np2 = st.text_input("確認密碼", type="password", key="r_p2")
        if st.button("註冊"):
            if np != np2:
                st.error("兩次密碼不符")
            elif not nu or not np:
                st.error("請輸入帳號密碼")
            else:
                ok, msg = register_user(nu, np)
                if ok: st.success(msg)
                else: st.error(msg)
