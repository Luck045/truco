import sqlite3

DB = "data/truco.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

print("Tabelas:")
for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"):
    print(" -", row[0])

print("\nUsers:")
for row in cur.execute("SELECT id, username FROM users ORDER BY id;"):
    print(row)

conn.close()
