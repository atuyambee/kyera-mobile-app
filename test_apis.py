#!/usr/bin/env python3
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# ----------------- OpenWeatherMap Test -----------------
print("🌤️ Testing OpenWeatherMap...")
owm_key = os.getenv('OPENWEATHER_API_KEY')
if not owm_key:
    print("   ❌ Missing OpenWeatherMap API key")
else:
    lat = os.getenv('MBARARA_LAT')
    lon = os.getenv('MBARARA_LON')
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {'lat': lat, 'lon': lon, 'units': 'metric', 'appid': owm_key}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ Success: {data['main']['temp']}°C, {data['main']['humidity']}% humidity")
        else:
            print(f"   ❌ Error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"   ❌ Exception: {e}")

# ----------------- Africa's Talking Test -----------------
print("\n📱 Testing Africa's Talking...")
at_username = os.getenv('AFRICASTALKING_USERNAME')
at_key = os.getenv('AFRICASTALKING_API_KEY')
if not at_username or not at_key:
    print("   ❌ Missing Africa's Talking credentials")
else:
    # Try sandbox endpoint first (since username may be 'sandbox')
    for endpoint in ['sandbox', '']:  # '' for live
        base = f"https://api{'.sandbox' if endpoint == 'sandbox' else ''}.africastalking.com"
        url = f"{base}/version1/messaging"
        data = {"username": at_username, "to": "+256778624568", "message": "Test from Kyera"}
        try:
            r = requests.post(url, auth=(at_username, at_key), data=data, timeout=10)
            print(f"   Endpoint: {base} → Status {r.status_code}")
            if r.status_code in (200, 201):
                print(f"   ✅ Success: {r.text}")
                break
            else:
                print(f"   ⚠️ Response: {r.text}")
        except Exception as e:
            print(f"   ❌ Exception: {e}")
