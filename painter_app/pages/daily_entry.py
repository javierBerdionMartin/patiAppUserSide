import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, date, time
import sqlite3
from typing import List, Dict, Optional, Tuple

from shared.utils import validate_times, parse_time, format_time_range, calculate_hours

# Add parent directory to Python path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))
from shared.database import get_db_connection

def get_user_locations(user_id: int) -> List[Dict]:
    """Get all locations created by the user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, address FROM locations WHERE user_id = ? AND active = 1 ORDER BY name",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def sanitize_input(text: str, max_length: int = 100) -> str:
    """Sanitize user input by removing dangerous characters and limiting length."""
    if not text:
        return ""
    # Remove any dangerous characters
    sanitized = ''.join(c for c in text if c.isalnum() or c in ' -_.,()#')
    # Limit length and strip whitespace
    return sanitized[:max_length].strip()

def add_location(user_id: int, name: str, address: Optional[str] = None) -> Tuple[bool, str]:
    """Add a new location for the user."""
    # Input validation
    if not name:
        return False, "Location name cannot be empty"
    
    # Sanitize inputs
    name = sanitize_input(name, max_length=50)
    if not name:
        return False, "Location name contains no valid characters"
    
    if address:
        address = sanitize_input(address, max_length=100)
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Start transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # Check if location already exists for this user (case-insensitive)
        cursor.execute(
            "SELECT id FROM locations WHERE user_id = ? AND LOWER(name) = LOWER(?) AND active = 1",
            (user_id, name)
        )
        if cursor.fetchone():
            return False, f"Location '{name}' already exists"
        
        # Check total locations for user (limit to 100 per user)
        cursor.execute("SELECT COUNT(*) FROM locations WHERE user_id = ? AND active = 1", (user_id,))
        if cursor.fetchone()[0] >= 100:
            return False, "Maximum number of locations (100) reached"
        
        # Add new location
        cursor.execute(
            """
            INSERT INTO locations (user_id, name, address)
            VALUES (?, ?, ?)
            """,
            (user_id, name, address)
        )
        conn.commit()
        return True, f"Location '{name}' added successfully"
    except sqlite3.IntegrityError:
        if conn:
            conn.rollback()
        return False, "Database constraint violation"
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        return False, f"Database error: {str(e)}"
    finally:
        if conn:
            conn.close()

def get_todays_entry(user_id) -> Optional[Dict]:
    """Get today's time entry and locations for the user if it exists."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Get the entry
        cursor.execute(
            """
            SELECT id, start_time, end_time, break_start, break_end
            FROM daily_entries 
            WHERE user_id = ? AND entry_date = DATE('now')
            """,
            (user_id,)
        )
        entry = cursor.fetchone()
        if not entry:
            return None
            
        # Get the locations
        cursor.execute(
            """
            SELECT l.id, l.name, l.address, dl.sequence_order
            FROM daily_locations dl
            JOIN locations l ON dl.location_id = l.id
            WHERE dl.entry_id = ?
            ORDER BY dl.sequence_order
            """,
            (entry['id'],)
        )
        locations = cursor.fetchall()
        
        return {
            'id': entry['id'],
            'start_time': entry['start_time'],
            'end_time': entry['end_time'],
            'locations': [dict(loc) for loc in locations]
        }
    finally:
        conn.close()

def validate_time_entry(start_time: str, end_time: str) -> tuple[bool, str]:
    """Validate time entry constraints."""
    try:
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        
        if start >= end:
            return False, "Start time must be before end time"
            
        return True, ""
    except ValueError as e:
        return False, f"Invalid time format: {e}"

def save_entry(user_id: int, start_time: str, end_time: str, break_start: Optional[str], 
            break_end: Optional[str], location_ids: List[int]) -> tuple[bool, str]:
    """Save or update today's time entry with locations and break time."""
    # Validate times first
    is_valid, error = validate_times(
        parse_time(start_time),
        parse_time(break_start) if break_start else None,
        parse_time(break_end) if break_end else None,
        parse_time(end_time)
    )
    if not is_valid:
        return False, error
        
    if not location_ids:
        return False, "At least one location must be selected"
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Verify all locations exist and are active
        locations_str = ",".join("?" * len(location_ids))
        cursor.execute(
            f"""SELECT COUNT(*) as count FROM locations 
                WHERE id IN ({locations_str}) AND active = 1""",
            location_ids
        )
        if cursor.fetchone()['count'] != len(location_ids):
            return False, "One or more selected locations are inactive or do not exist"
        
        # Start a transaction
        cursor.execute('BEGIN TRANSACTION')
        
        try:
            # Insert/update the daily entry
            cursor.execute(
                """
                INSERT INTO daily_entries 
                    (user_id, entry_date, start_time, end_time, break_start, break_end)
                VALUES (?, DATE('now'), ?, ?, ?, ?)
                ON CONFLICT(user_id, entry_date) 
                DO UPDATE SET 
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    break_start = excluded.break_start,
                    break_end = excluded.break_end,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (user_id, start_time, end_time, break_start, break_end)
            )
            
            entry_id = cursor.fetchone()['id']
            
            # Delete existing locations for this entry
            cursor.execute(
                "DELETE FROM daily_locations WHERE entry_id = ?",
                (entry_id,)
            )
            
            # Insert new locations
            for order, loc_id in enumerate(location_ids, 1):
                try:
                    cursor.execute(
                        """
                        INSERT INTO daily_locations (entry_id, location_id, sequence_order)
                        VALUES (?, ?, ?)
                        """,
                        (entry_id, loc_id, order)
                    )
                except sqlite3.IntegrityError as e:
                    if "UNIQUE constraint failed" in str(e):
                        return False, f"Location sequence order {order} is already used"
                    raise
            
            conn.commit()
            return True, "Entry saved successfully"
            
        except sqlite3.IntegrityError as e:
            if "CHECK constraint failed" in str(e):
                return False, "Invalid time values. Please check your entry"
            raise
            
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Database error: {e}"
    finally:
        conn.close()

def calculate_break_time(start_time: time, end_time: time) -> Tuple[Optional[time], Optional[time]]:
    """Calculate break time based on work duration."""
    # Convert times to minutes since midnight
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute
    
    # Calculate total work duration in minutes
    total_minutes = end_minutes - start_minutes
    
    # If work duration is less than 6 hours, no break
    if total_minutes < 360:  # 6 hours
        return None, None
    
    # Calculate middle of work day
    mid_minutes = start_minutes + (total_minutes // 2)
    
    # Break starts 30 minutes before middle of day
    break_start_minutes = mid_minutes - 30
    break_end_minutes = mid_minutes + 30
    
    # Convert back to time objects
    break_start = time(break_start_minutes // 60, break_start_minutes % 60)
    break_end = time(break_end_minutes // 60, break_end_minutes % 60)
    
    return break_start, break_end

def main():
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        st.warning("Please log in first.")
        st.stop()
    
    st.title("Daily Time Entry")
    
    # Get today's date
    today = date.today()
    st.subheader(f"Time Entry for {today.strftime('%B %d, %Y')}")
    
    # Get user's locations
    locations = get_user_locations(st.session_state.user_id)
    
    # Get existing entry
    existing_entry = get_todays_entry(st.session_state.user_id)
    
    # Work time input fields
    st.subheader("Work Hours")
    col1, col2 = st.columns(2)
    
    with col1:
        default_start = time(8, 0) if not existing_entry else datetime.strptime(existing_entry['start_time'], "%H:%M").time()
        start_time = st.time_input("Start Time", value=default_start)
    
    with col2:
        default_end = time(17, 0) if not existing_entry else datetime.strptime(existing_entry['end_time'], "%H:%M").time()
        end_time = st.time_input("End Time", value=default_end)
        
    # Break time input fields
    st.subheader("Break Time")
    st.write("Enter your break time (if any). Breaks longer than 30 minutes will have a 30-minute deduction.")
    
    col1, col2 = st.columns(2)
    with col1:
        default_break_start = None if not existing_entry or not existing_entry.get('break_start') else \
            datetime.strptime(existing_entry['break_start'], "%H:%M").time()
        break_start = st.time_input("Break Start", value=default_break_start or time(12, 0))
    
    with col2:
        default_break_end = None if not existing_entry or not existing_entry.get('break_end') else \
            datetime.strptime(existing_entry['break_end'], "%H:%M").time()
        break_end = st.time_input("Break End", value=default_break_end or time(12, 30))
    
    # Calculate and show break deduction
    if break_start and break_end:
        hours, deduction = calculate_hours(start_time, break_start, break_end, end_time)
        if deduction > 0:
            st.warning(f"⚠️ Break is longer than 30 minutes. A {deduction}-minute deduction will be applied.")
        else:
            st.success("✓ Break is 30 minutes or less. No deduction will be applied.")
    
    # Location Management
    st.subheader("Work Locations")
    st.write("Add locations in the order you visited them. You can enter a new location or select an existing one.")
    
    # Initialize session states
    if 'selected_locations' not in st.session_state:
        st.session_state.selected_locations = (
            [loc['id'] for loc in existing_entry['locations']]
            if existing_entry and existing_entry.get('locations')
            else []
        )
    if 'location_input_mode' not in st.session_state:
        st.session_state.location_input_mode = 'new'  # or 'existing'
    
    # Location input mode selection
    input_mode = st.radio(
        "Location Input Mode",
        options=["Enter New Location", "Select Existing Location"],
        horizontal=True,
        index=0 if st.session_state.location_input_mode == 'new' else 1
    )
    st.session_state.location_input_mode = 'new' if input_mode == "Enter New Location" else 'existing'
    
    # Create columns for location input
    col1, col2, col3 = st.columns([2, 2, 1])
    
    if st.session_state.location_input_mode == 'new':
        with col1:
            new_location_name = st.text_input("Location Name", key="new_loc_name")
        with col2:
            new_location_address = st.text_input("Address (Optional)", key="new_loc_addr")
        with col3:
            add_new = st.button("Add Location")
            
        if add_new and new_location_name:
            # Check if location already exists
            existing = next((loc for loc in locations if loc['name'].lower() == new_location_name.lower()), None)
            if existing:
                st.error(f"Location '{new_location_name}' already exists. Please select it from 'Select Existing Location'.")
                # Switch to existing mode to show the location
                st.session_state.location_input_mode = 'existing'
                st.experimental_rerun()
            else:
                success, message = add_location(
                    st.session_state.user_id,
                    new_location_name,
                    new_location_address if new_location_address else None
                )
                if success:
                    st.success(message)
                    # Refresh locations to get the new location's ID
                    locations = get_user_locations(st.session_state.user_id)
                    # Find the newly added location
                    new_loc = next(loc for loc in locations if loc['name'].lower() == new_location_name.lower())
                    # Add it to the sequence
                    st.session_state.selected_locations.append(new_loc['id'])
                    st.experimental_rerun()
                else:
                    st.error(message)
    else:
        with col1:
            # Location dropdown
            if locations:
                location = st.selectbox(
                    "Select Location",
                    options=[{'id': l['id'], 'name': l['name'], 'address': l['address']} for l in locations],
                    format_func=lambda x: f"{x['name']} ({x['address'] if x['address'] else 'No address'})"
                )
            else:
                st.info("No locations available. Please add a new location.")
                location = None
        
        with col2:
            # Add to sequence button
            if location and st.button("Add to Sequence"):
                if location['id'] not in st.session_state.selected_locations:
                    st.session_state.selected_locations.append(location['id'])
                    st.experimental_rerun()
                else:
                    st.error(f"Location '{location['name']}' already added to sequence")
    

    
    # Show selected locations
    if st.session_state.selected_locations:
        st.write("Selected locations:")
        selected_locations = []
        for loc_id in st.session_state.selected_locations:
            loc = next((l for l in locations if l['id'] == loc_id), None)
            if loc:
                selected_locations.append(loc)
            
        # Clear invalid location IDs
        st.session_state.selected_locations = [loc['id'] for loc in selected_locations]
        
        for i, loc in enumerate(selected_locations):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"{i+1}. {loc['name']} ({loc['address'] if loc['address'] else 'No address'})")
            with col2:
                if st.button("Remove", key=f"remove_{loc['id']}"):
                    st.session_state.selected_locations.remove(loc['id'])
                    st.experimental_rerun()
    
    # Save entry button
    if st.button("Save Entry"):
        # Get break times from calculation
        break_start_str = break_start.strftime("%H:%M") if break_start else None
        break_end_str = break_end.strftime("%H:%M") if break_end else None
        
        success, message = save_entry(
            st.session_state.user_id,
            start_time.strftime("%H:%M"),
            end_time.strftime("%H:%M"),
            break_start_str,
            break_end_str,
            st.session_state.selected_locations
        )
        
        if success:
            st.success(message)
            st.experimental_rerun()
        else:
            st.error(message)
    
    # Show current entry
    if existing_entry:
        st.divider()
        st.subheader("Today's Entry")
        st.write(f"Work Hours: {format_time_range(parse_time(existing_entry['start_time']), parse_time(existing_entry['end_time']))}")
        
        if existing_entry.get('break_start') and existing_entry.get('break_end'):
            st.write(f"Break Time: {format_time_range(parse_time(existing_entry['break_start']), parse_time(existing_entry['break_end']))}")
        
        # Calculate duration and deduction
        hours, deduction = calculate_hours(
            parse_time(existing_entry['start_time']),
            parse_time(existing_entry['break_start']) if existing_entry.get('break_start') else None,
            parse_time(existing_entry['break_end']) if existing_entry.get('break_end') else None,
            parse_time(existing_entry['end_time'])
        )
        
        st.write(f"Total Hours Worked: {hours:.2f}")
        if deduction > 0:
            st.write(f"Break Deduction Applied: {deduction} minutes")
        
        if existing_entry.get('locations'):
            st.write("\nLocations visited:")
            for i, loc in enumerate(existing_entry['locations'], 1):
                st.write(f"{i}. {loc['name']} ({loc['address'] if loc['address'] else 'No address'})")

if __name__ == "__main__":
    main()
