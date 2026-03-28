from werkzeug.security import generate_password_hash
import sqlite3

# Connect to database
conn = sqlite3.connect('instance/kyera.db')
c = conn.cursor()

# Get all farmers without passwords
c.execute("SELECT id, name, phone FROM farmers WHERE password IS NULL")
farmers = c.fetchall()

if farmers:
    print(f"Found {len(farmers)} farmers without passwords")
    for farmer in farmers:
        # Set default password: first 4 digits of phone number
        default_password = farmer[2][-6:] if farmer[2] else '123456'
        hashed = generate_password_hash(default_password)
        c.execute("UPDATE farmers SET password = ? WHERE id = ?", (hashed, farmer[0]))
        print(f"  {farmer[1]} ({farmer[2]}) -> password: {default_password}")
    conn.commit()
    print("\n✅ Passwords set for all farmers!")
else:
    print("✅ All farmers already have passwords")

conn.close()
