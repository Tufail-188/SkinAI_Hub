import sqlite3

# Connect to your SQLite database
conn = sqlite3.connect("database.db")
cur = conn.cursor()

# Query all users
cur.execute("SELECT id, username, created_at FROM users")
users = cur.fetchall()

print("\n--- Registered Users ---\n")
for u in users:
    print(f"ID: {u[0]}, Username: {u[1]}, Created At: {u[2]}")

conn.close()
