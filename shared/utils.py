from datetime import datetime, time
from typing import Optional, Tuple

def parse_time(time_str: str) -> Optional[time]:
    """Parse time string to time object."""
    try:
        return datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        return None

def validate_times(
    work_start: time,
    break_start: Optional[time],
    break_end: Optional[time],
    work_end: time
) -> Tuple[bool, str]:
    """
    Validate work and break times.
    Returns (is_valid, error_message).
    """
    # Basic work day validation
    if work_start >= work_end:
        return False, "Work start time must be before work end time"
        
    # If no break times, just validate work hours
    if not break_start and not break_end:
        return True, ""
        
    # If one break time is set, both must be set
    if bool(break_start) != bool(break_end):
        return False, "Both break start and end times must be set"
        
    # Validate break times
    if break_start and break_end:
        if break_start >= break_end:
            return False, "Break start time must be before break end time"
            
        if break_start <= work_start:
            return False, "Break cannot start before work starts"
            
        if break_end >= work_end:
            return False, "Break cannot end after work ends"
    
    return True, ""

def format_time_range(start: time, end: time) -> str:
    """Format a time range for display."""
    return f"{start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}"

def calculate_break_deduction(break_start: time, break_end: time) -> int:
    """Calculate break time deduction in minutes based on actual break duration."""
    def time_to_minutes(t: time) -> int:
        return t.hour * 60 + t.minute
    
    break_duration = time_to_minutes(break_end) - time_to_minutes(break_start)
    
    # If break is 30 minutes or less, no deduction
    if break_duration <= 30:
        return 0
    # If break is more than 30 minutes, deduct 30 minutes
    else:
        return 30

def calculate_hours(
    work_start: time,
    break_start: Optional[time],
    break_end: Optional[time],
    work_end: time
) -> Tuple[float, int]:
    """Calculate total work hours and break deduction.
    Returns (total_hours, break_deduction_minutes)"""
    
    def time_to_minutes(t: time) -> int:
        return t.hour * 60 + t.minute
    
    total_minutes = time_to_minutes(work_end) - time_to_minutes(work_start)
    break_deduction = 0
    
    if break_start and break_end:
        actual_break = time_to_minutes(break_end) - time_to_minutes(break_start)
        break_deduction = calculate_break_deduction(break_start, break_end)
        total_minutes -= actual_break
    
    return round(total_minutes / 60, 2), break_deduction

def is_session_expired(last_activity: datetime, timeout_minutes: int = 30) -> bool:
    """Check if the session has expired based on last activity."""
    if not last_activity:
        return True
        
    now = datetime.utcnow()
    diff = now - last_activity
    return diff.total_seconds() / 60 > timeout_minutes
