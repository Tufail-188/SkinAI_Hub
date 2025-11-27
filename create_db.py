import sqlite3

# OPEN CONNECTION
conn = sqlite3.connect("database.db")
cur = conn.cursor()

# -----------------------
# USERS TABLE
# -----------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# -----------------------
# APPOINTMENTS TABLE
# -----------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_name TEXT NOT NULL,
    patient_name TEXT NOT NULL,
    patient_email TEXT NOT NULL,
    patient_phone TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# SAVE & CLOSE
conn.commit()
conn.close()

print("Database updated successfully! Users & Appointments tables created.")
