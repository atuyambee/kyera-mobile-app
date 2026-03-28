from werkzeug.security import generate_password_hash
import sqlite3

print("Setting up passwords for farmers...")
conn = sqlite3.connect('instance/kyera.db')
c = conn.cursor()

# Get all farmers
c.execute("SELECT id, name, phone FROM farmers")
farmers = c.fetchall()

print(f"Found {len(farmers)} farmers\n")

for farmer in farmers:
    farmer_id, name, phone = farmer
    
    # Use last 6 digits of phone as password
    if phone and len(str(phone)) >= 6:
        default_password = str(phone)[-6:]
    else:
        default_password = '123456'
    
    hashed = generate_password_hash(default_password)
    c.execute("UPDATE farmers SET password = ? WHERE id = ?", (hashed, farmer_id))
    print(f"✅ {name} ({phone}) -> password: {default_password}")

conn.commit()
print("\n✅ All passwords set!")
conn.close()
