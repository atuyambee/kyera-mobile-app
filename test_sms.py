import os
import requests

# Read .env manually
env = {}
with open('.env', 'r') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#'):
            if '=' in line:
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip().strip('"').strip("'")

username = env.get('AFRICASTALKING_USERNAME')
api_key = env.get('AFRICASTALKING_API_KEY')
print(f"Username: {username}")
print(f"API Key starts with: {api_key[:20] if api_key else 'None'}...")

if not username or not api_key:
    print("❌ Missing credentials")
    exit(1)

# Choose endpoint based on username
if username == 'sandbox':
    endpoint = "https://api.sandbox.africastalking.com"
else:
    endpoint = "https://api.africastalking.com"

url = f"{endpoint}/version1/messaging"

# The phone number must be in international format (e.g., +256...)
to_number = "+256778624568"  # replace with your actual test number
data = {"username": username, "to": to_number, "message": "Test from Kyera"}

try:
    response = requests.post(url, auth=(username, api_key), data=data, timeout=10)
    print(f"Status: {response.status_code}")
    print(response.text)
    if response.status_code == 201:
        print("✅ SMS sent successfully! Account is active.")
    elif response.status_code == 401:
        print("❌ Authentication failed. Please verify:")
        print("   - Your email is verified (check dashboard for activation banner).")
        print("   - Your username matches your environment (sandbox or live).")
        print("   - If in sandbox, you have added the recipient number to Sandbox → Phone Numbers.")
        print("   - If in live, you have sufficient credit.")
    else:
        print("⚠️ Unexpected response.")
except Exception as e:
    print(f"Error: {e}")
