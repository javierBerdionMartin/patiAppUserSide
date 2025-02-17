# Painter Timesheet App

A streamlit-based application for tracking painter work hours and locations.

## Features

- User authentication
- Daily time entry tracking
- Break time management with automatic deductions
- Location tracking with custom location support
- User-specific location management

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Initialize the database:
```bash
python shared/database.py
```

4. Run the application:
```bash
streamlit run painter_app/main.py
```

## Usage

1. Log in with your credentials
2. Enter your work hours for the day
3. Add break time if applicable (breaks > 30 minutes will have a 30-minute deduction)
4. Add locations you visited
5. Save your entry

## Development

The application is structured as follows:
- `painter_app/`: Main application code
  - `main.py`: Entry point and login handling
  - `pages/`: Streamlit pages
    - `daily_entry.py`: Daily timesheet entry page
- `shared/`: Shared utilities and database code
- `database/`: Database schema and storage
