import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to Python path for imports
sys.path.append(str(Path(__file__).parent.parent))

from shared.database import get_db_connection, init_db
from shared.utils import is_session_expired

# Configuration
SESSION_TIMEOUT_MINUTES = 30  # Set to 1 for testing

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None

def login(username, password):
    """Verify login credentials."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password)
        )
        user = cursor.fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

def check_session():
    """Check if the session is valid and update last activity."""
    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = None
    
    if st.session_state.get('logged_in'):
        if is_session_expired(st.session_state.last_activity, SESSION_TIMEOUT_MINUTES):
            # Clear session state
            for key in ['logged_in', 'username', 'user_id', 'last_activity']:
                if key in st.session_state:
                    del st.session_state[key]
            st.warning("Your session has expired. Please log in again.")
            st.experimental_rerun()
        else:
            # Update last activity
            st.session_state.last_activity = datetime.utcnow()

def main():
    st.title("Painter Timesheet App")
    
    # Check session status
    check_session()
    
    if not st.session_state.get('logged_in'):
        st.subheader("Login")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                if not username or not password:
                    st.error("Please enter both username and password")
                else:
                    user = login(username, password)
                    if user:
                        st.session_state.logged_in = True
                        st.session_state.username = user['full_name']
                        st.session_state.user_id = user['id']
                        st.session_state.last_activity = datetime.utcnow()
                        st.success("Login successful!")
                        st.experimental_rerun()
                    else:
                        st.error("Invalid username or password")
    else:
        st.write(f"Welcome {st.session_state.username}!")
        if st.button("Logout"):
            for key in ['logged_in', 'username', 'user_id', 'last_activity']:
                if key in st.session_state:
                    del st.session_state[key]
            st.success("Logged out successfully!")
            st.experimental_rerun()

if __name__ == "__main__":
    # Initialize database on first run
    init_db()
    main()
