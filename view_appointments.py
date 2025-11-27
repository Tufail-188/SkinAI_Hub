import sqlite3

# Connect to the database
conn = sqlite3.connect("database.db")
cur = conn.cursor()

# Fetch all appointments
cur.execute("SELECT * FROM appointments")
appointments = cur.fetchall()

print("\n--- Saved Appointments ---\n")

if len(appointments) == 0:
    print("No appointments found.")
else:
    for a in appointments:
        print(f"""
Appointment ID : {a[0]}
Doctor Name    : {a[1]}
Patient Name   : {a[2]}
Patient Email  : {a[3]}
Patient Phone  : {a[4]}
Date           : {a[5]}
Time           : {a[6]}
Created At     : {a[7]}
------------------------------------------
""")

conn.close()
