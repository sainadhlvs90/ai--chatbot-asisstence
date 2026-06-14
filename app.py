import streamlit as st
from google import genai
from dotenv import load_dotenv
from pypdf import PdfReader
from PIL import Image
from duckduckgo_search import DDGS
import pandas as pd
import sqlite3
import hashlib
import os
import json
import uuid
import time

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

DB_FILE = "chatbot.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            username TEXT,
            chat_id TEXT,
            title TEXT,
            messages TEXT,
            PRIMARY KEY(username, chat_id)
        )
    """)

    conn.commit()
    conn.close()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def signup(username, password):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO users VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        conn.close()
        return True
    except:
        return False


def login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, hash_password(password))
    )
    user = c.fetchone()
    conn.close()
    return user is not None


def load_user_chats(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id, title, messages FROM chats WHERE username=?", (username,))
    rows = c.fetchall()
    conn.close()

    chats = {}

    for chat_id, title, messages in rows:
        chats[chat_id] = {
            "title": title,
            "messages": json.loads(messages)
        }

    return chats


def save_chat(username, chat_id, title, messages):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO chats VALUES (?, ?, ?, ?)",
        (username, chat_id, title, json.dumps(messages))
    )
    conn.commit()
    conn.close()


def create_new_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.current_chat_id = chat_id
    st.session_state.chats[chat_id] = {
        "title": "New Chat",
        "messages": []
    }


def extract_file_text(uploaded_file):
    if uploaded_file is None:
        return ""

    file_type = uploaded_file.name.split(".")[-1].lower()

    try:
        if file_type == "pdf":
            reader = PdfReader(uploaded_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text[:8000]

        elif file_type == "txt":
            return uploaded_file.read().decode("utf-8")[:8000]

        elif file_type == "csv":
            df = pd.read_csv(uploaded_file)
            return df.head(50).to_string()

        elif file_type in ["xlsx", "xls"]:
            df = pd.read_excel(uploaded_file)
            return df.head(50).to_string()

        return ""

    except Exception as e:
        return f"File reading error: {e}"


def web_search(query):
    try:
        results_text = ""

        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)

            for result in results:
                results_text += f"""
Title: {result.get('title')}
Link: {result.get('href')}
Summary: {result.get('body')}

"""

        return results_text

    except Exception as e:
        return f"Web search error: {e}"


def generate_ai_response(model, contents):
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents
        )
        return response.text

    except Exception as e:
        error_text = str(e)

        if "503" in error_text or "UNAVAILABLE" in error_text:
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=contents
                )
                return response.text
            except Exception:
                return "Gemini is currently busy due to high demand. Please wait 1-2 minutes and try again."

        return f"Error: {e}"


def generate_image_response(model, prompt, image):
    try:
        response = client.models.generate_content(
            model=model,
            contents=[prompt, image]
        )
        return response.text

    except Exception as e:
        error_text = str(e)

        if "503" in error_text or "UNAVAILABLE" in error_text:
            return "Gemini image model is currently busy. Please try again after 1-2 minutes."

        return f"Error: {e}"


def stream_response(text):
    placeholder = st.empty()
    displayed_text = ""

    for word in text.split():
        displayed_text += word + " "
        placeholder.markdown(displayed_text)
        time.sleep(0.02)

    return displayed_text


init_db()

st.set_page_config(
    page_title="SAINADH AI",
    page_icon="🤖",
    layout="wide"
)

st.markdown("""
<style>
[data-testid="stSidebar"] {
    background-color: #171717;
}

.main-title {
    text-align: center;
    font-size: 42px;
    font-weight: 700;
    margin-top: 30px;
}

.welcome-text {
    text-align: center;
    font-size: 22px;
    color: #cccccc;
    margin-bottom: 30px;
}

.card {
    padding: 18px;
    border-radius: 15px;
    background-color: #1f1f1f;
    border: 1px solid #333;
    text-align: center;
    font-size: 17px;
}

[data-testid="stChatInput"] {
    max-width: 850px;
    margin: auto;
}
</style>
""", unsafe_allow_html=True)


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


if not st.session_state.logged_in:
    st.title("🤖 SAINADH AI Login")

    tab1, tab2 = st.tabs(["Login", "Signup"])

    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login"):
            if login(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.chats = load_user_chats(username)

                if len(st.session_state.chats) == 0:
                    create_new_chat()
                else:
                    st.session_state.current_chat_id = list(st.session_state.chats.keys())[0]

                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        new_username = st.text_input("Create Username")
        new_password = st.text_input("Create Password", type="password")

        if st.button("Signup"):
            if signup(new_username, new_password):
                st.success("Account created successfully. Now login.")
            else:
                st.error("Username already exists")

    st.stop()


with st.sidebar:
    st.title("SAINADH AI")
    st.caption(f"Logged in as: {st.session_state.username}")

    if st.button("➕ New Chat", use_container_width=True):
        create_new_chat()
        st.rerun()

    if st.button("Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown("---")

    selected_model = st.selectbox(
        "Choose Model",
        ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]
    )

    web_mode = st.toggle("🌐 Web Search Mode")

    uploaded_file = st.file_uploader(
        "Upload File",
        type=["pdf", "txt", "csv", "xlsx", "png", "jpg", "jpeg"]
    )

    st.markdown("---")
    st.subheader("Chat History")

    for chat_id, chat in st.session_state.chats.items():
        if st.button(chat["title"][:30], key=chat_id, use_container_width=True):
            st.session_state.current_chat_id = chat_id
            st.rerun()


current_chat = st.session_state.chats[st.session_state.current_chat_id]
messages = current_chat["messages"]

st.markdown('<div class="main-title">🤖 SAINADH Chatbot</div>', unsafe_allow_html=True)

if len(messages) == 0:
    st.markdown(
        '<div class="welcome-text">What can I help you with today?</div>',
        unsafe_allow_html=True
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown('<div class="card">💡 Explain concepts</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">💻 Write code</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="card">📄 Summarize files</div>', unsafe_allow_html=True)

    with col4:
        st.markdown('<div class="card">🌐 Search web</div>', unsafe_allow_html=True)


for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


prompt = st.chat_input("Message SAINADH AI...")


if prompt:
    messages.append({"role": "user", "content": prompt})

    if current_chat["title"] == "New Chat":
        current_chat["title"] = prompt[:35]

    with st.chat_message("user"):
        st.markdown(prompt)

    system_prompt = """
You are SAINADH AI, an intelligent AI assistant similar to ChatGPT.
Answer clearly, professionally, and in an easy-to-understand way.
"""

    conversation = system_prompt + "\n\n"

    for msg in messages:
        conversation += f"{msg['role']}: {msg['content']}\n"

    file_text = extract_file_text(uploaded_file)

    if file_text:
        conversation += f"\n\nUploaded file content:\n{file_text}"

    if web_mode:
        search_results = web_search(prompt)
        conversation += f"\n\nWeb search results:\n{search_results}"

    with st.spinner("Thinking..."):
        if uploaded_file and uploaded_file.name.split(".")[-1].lower() in ["png", "jpg", "jpeg"]:
            image = Image.open(uploaded_file)
            reply = generate_image_response(selected_model, prompt, image)
        else:
            reply = generate_ai_response(selected_model, conversation)

    with st.chat_message("assistant"):
        stream_response(reply)

    messages.append({"role": "assistant", "content": reply})

    save_chat(
        st.session_state.username,
        st.session_state.current_chat_id,
        current_chat["title"],
        messages
    )