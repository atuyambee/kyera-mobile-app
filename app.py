#!/usr/bin/env python3
"""
Kyera Smart Agriculture App - Complete Working Version with Simulators
"""

import os
import sqlite3
import requests
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import africastalking
from apscheduler.schedulers.background import BackgroundScheduler

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'kyera-smart-agriculture-secret-key-2025')
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path
DATABASE = os.path.join(os.path.dirname(__file__), 'instance', 'kyera.db')
os.makedirs(os.path.dirname(DATABASE), exist_ok=True)

# Africa's Talking credentials
AT_USERNAME = os.getenv('AFRICASTALKING_USERNAME')
AT_API_KEY = os.getenv('AFRICASTALKING_API_KEY')
AT_SENDER_ID = os.getenv('AFRICASTALKING_SENDER_ID', 'KYERAAG')

# Initialize Africa's Talking if credentials exist
sms = None
if AT_USERNAME and AT_API_KEY and AT_API_KEY != 'your_api_key':
    try:
        africastalking.initialize(AT_USERNAME, AT_API_KEY)
        sms = africastalking.SMS
        logger.info("✅ Africa's Talking initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️ Africa's Talking initialization failed: {e}")
else:
    logger.warning("⚠️ No Africa's Talking API key found. SMS will be simulated.")

# Weather API configuration
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
MBARARA_LAT = os.getenv('MBARARA_LAT', '-0.607')
MBARARA_LON = os.getenv('MBARARA_LON', '30.654')

print(f"\n🔧 Configuration:")
print(f"   Weather API Key: {WEATHER_API_KEY[:10] if WEATHER_API_KEY else 'None'}...")
print(f"   Location: {MBARARA_LAT}, {MBARARA_LON}")
print(f"   Africa's Talking: {'✅' if sms else '⚠️ Simulated'}")

# ==================== Database Functions ====================

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Farmers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS farmers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                main_crop TEXT,
                village TEXT,
                other_crops TEXT,
                farm_size REAL,
                language TEXT DEFAULT 'en',
                is_admin INTEGER DEFAULT 0,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP,
                login_token TEXT,
                token_expiry TIMESTAMP
            )
        ''')
        
        # Alerts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id INTEGER,
                pest TEXT,
                risk TEXT,
                message TEXT,
                advice TEXT,
                prevention TEXT,
                treatment TEXT,
                sent_via TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                was_read BOOLEAN DEFAULT 0,
                read_date TIMESTAMP,
                action_taken TEXT,
                FOREIGN KEY (farmer_id) REFERENCES farmers (id)
            )
        ''')
        
        # Rules table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crop TEXT,
                pest TEXT,
                pest_runyankole TEXT,
                temp_min REAL,
                temp_max REAL,
                humidity_min REAL,
                rain_min REAL,
                days INTEGER,
                risk TEXT,
                advice TEXT,
                prevention_tips TEXT,
                treatment_tips TEXT
            )
        ''')
        
        # Weather data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weather_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                temperature REAL,
                humidity REAL,
                rainfall REAL,
                wind_speed REAL,
                forecast_date DATE,
                conditions TEXT
            )
        ''')
        
        # Feedback table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id INTEGER,
                alert_id INTEGER,
                rating INTEGER,
                comment TEXT,
                pest_observed TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (farmer_id) REFERENCES farmers (id),
                FOREIGN KEY (alert_id) REFERENCES alerts (id)
            )
        ''')
        
        # Questions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id INTEGER,
                crop TEXT,
                title TEXT,
                question TEXT,
                images TEXT,
                status TEXT DEFAULT 'pending',
                views INTEGER DEFAULT 0,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated TIMESTAMP,
                FOREIGN KEY (farmer_id) REFERENCES farmers (id)
            )
        ''')
        
        # Answers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                farmer_id INTEGER,
                answer TEXT,
                is_best BOOLEAN DEFAULT 0,
                likes INTEGER DEFAULT 0,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (question_id) REFERENCES questions (id),
                FOREIGN KEY (farmer_id) REFERENCES farmers (id)
            )
        ''')
        
        # Answer likes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS answer_likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                answer_id INTEGER,
                farmer_id INTEGER,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (answer_id) REFERENCES answers (id),
                FOREIGN KEY (farmer_id) REFERENCES farmers (id)
            )
        ''')
        
        # Notifications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id INTEGER,
                type TEXT,
                title TEXT,
                message TEXT,
                link TEXT,
                is_read BOOLEAN DEFAULT 0,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (farmer_id) REFERENCES farmers (id)
            )
        ''')
        
        # Insert default admin if not exists
        cursor.execute('SELECT id FROM farmers WHERE is_admin = 1')
        if not cursor.fetchone():
            admin_password = generate_password_hash('admin123')
            cursor.execute('''
                INSERT INTO farmers (name, phone, password, main_crop, village, is_admin)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', ('Admin User', '+256700000001', admin_password, 'maize', 'Kyera Admin', 1))
            logger.info("✅ Admin user created")
        
        # Insert default farmers if not exists
        cursor.execute('SELECT COUNT(*) FROM farmers WHERE is_admin = 0')
        if cursor.fetchone()[0] < 6:
            test_farmers = [
                ('Kyera Farmer', '256700000000', generate_password_hash('kyerafarmer123'), 'maize', 'Kyera Village', 0),
                ('Gilbert Nuwahereza', '0778123456', generate_password_hash('gilbertnuwahereza123'), 'maize', 'Kyera Village', 0),
                ('NATUHWERA SHARROT', '0771362693', generate_password_hash('natuherwasharrot123'), 'bananas', 'Kyera Village', 0),
                ('Mubangizi Peterson', '0761337823', generate_password_hash('mubangizipeterson123'), 'beans', 'Kyera Village', 0),
                ('KTUSIIME OLIVER', '07079284349', generate_password_hash('ktusiimeoliver123'), 'maize', 'Kyera Village', 0),
                ('ARINDA LOLAND', '0705907859', generate_password_hash('arindaloland123'), 'bananas', 'Kyera Village', 0),
            ]
            for farmer in test_farmers:
                cursor.execute('''
                    INSERT OR IGNORE INTO farmers (name, phone, password, main_crop, village, is_admin)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', farmer)
            logger.info("✅ Test farmers created")
        
        # Insert default rules if empty
        cursor.execute('SELECT COUNT(*) FROM rules')
        if cursor.fetchone()[0] == 0:
            default_rules = [
                ('maize', 'Fall Armyworm', 'Enyegenyebe', 25, 30, 70, 0, 3, 'High',
                 'Scout fields daily. Apply neem extract if >5 larvae per m².',
                 'Plant early, use certified seeds, rotate crops',
                 'Spray with emamectin benzoate or neem extract'),
                ('maize', 'Maize Streak Virus', 'Endwara y\'emigoye', 20, 28, 0, 0, 7, 'High',
                 'Rogue infected plants. Control leafhopper vectors.',
                 'Use resistant varieties. Plant at optimal spacing.',
                 'Apply systemic insecticide to control vectors'),
                ('bananas', 'Banana Xanthomonas Wilt', 'Kawuka', 22, 28, 0, 15, 3, 'High',
                 'Disinfect tools. Remove male buds weekly.',
                 'Use clean planting materials. Avoid contaminated tools.',
                 'Cut and burn infected plants. Apply copper-based bactericides'),
                ('bananas', 'Black Sigatoka', 'Endwara y\'ebibala', 20, 25, 80, 10, 0, 'High',
                 'Apply fungicide at first symptoms. Remove infected leaves.',
                 'Maintain spacing for air circulation. Remove infected leaves.',
                 'Apply protective fungicide every 14-21 days during wet season'),
                ('beans', 'Angular Leaf Spot', 'Endwara y\'ebijanja', 18, 24, 85, 0, 0, 'High',
                 'Apply copper-based fungicide. Improve air circulation.',
                 'Use certified seeds. Practice crop rotation.',
                 'Apply copper-based fungicide at 7-10 day intervals'),
                ('beans', 'Bean Rust', 'Engore', 15, 25, 90, 0, 6, 'High',
                 'Remove infected leaves. Apply fungicide.',
                 'Plant resistant varieties. Avoid overhead irrigation.',
                 'Apply fungicide containing propiconazole or tebuconazole'),
            ]
            for rule in default_rules:
                cursor.execute('''
                    INSERT INTO rules (crop, pest, pest_runyankole, temp_min, temp_max, humidity_min, rain_min, days, risk, advice, prevention_tips, treatment_tips)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', rule)
            logger.info(f"✅ Inserted {len(default_rules)} default rules")
        
        conn.commit()
        logger.info("✅ Database initialized successfully")

# ==================== Helper Functions ====================

def fetch_weather():
    """Fetch real weather data from OpenWeatherMap API"""
    if not WEATHER_API_KEY:
        logger.warning("No weather API key found")
        return {'temp': 22.5, 'humidity': 65, 'rainfall': 0, 'wind_speed': 5, 'conditions': 'Data unavailable'}
    
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {'lat': MBARARA_LAT, 'lon': MBARARA_LON, 'units': 'metric', 'appid': WEATHER_API_KEY}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'temp': data['main']['temp'],
                'humidity': data['main']['humidity'],
                'rainfall': data.get('rain', {}).get('1h', 0),
                'wind_speed': data['wind']['speed'],
                'conditions': data['weather'][0]['description']
            }
        else:
            logger.error(f"Weather API error: {response.status_code}")
            return {'temp': 22.5, 'humidity': 65, 'rainfall': 0, 'wind_speed': 5, 'conditions': 'API Error'}
    except Exception as e:
        logger.error(f"Weather fetch error: {e}")
        return {'temp': 22.5, 'humidity': 65, 'rainfall': 0, 'wind_speed': 5, 'conditions': 'Connection Error'}

def send_sms(phone_number, message):
    """Send SMS using Africa's Talking or simulate"""
    if sms:
        try:
            response = sms.send(message, [phone_number], sender=AT_SENDER_ID)
            logger.info(f"📱 SMS sent to {phone_number}")
            return True
        except Exception as e:
            logger.error(f"SMS error: {e}")
            return False
    else:
        logger.info(f"[SMS SIMULATED] To {phone_number}: {message[:100]}...")
        return True

def generate_and_send_alerts():
    """Generate alerts based on current weather and send to farmers"""
    try:
        logger.info(f"🔄 Running alert generation at {datetime.now()}")
        
        weather = fetch_weather()
        if not weather:
            logger.error("Could not fetch weather data")
            return
        
        logger.info(f"🌤️ Weather: {weather['temp']}°C, {weather['humidity']}% humidity")
        
        with get_db() as db:
            # Save weather
            db.execute('''
                INSERT INTO weather_data (temperature, humidity, rainfall, wind_speed, forecast_date, conditions)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (weather['temp'], weather['humidity'], weather['rainfall'], 
                  weather['wind_speed'], datetime.now().date(), weather['conditions']))
            db.commit()
            
            farmers = db.execute('SELECT id, name, phone, main_crop FROM farmers WHERE phone IS NOT NULL').fetchall()
            alerts_created = 0
            
            for farmer in farmers:
                rules = db.execute('SELECT * FROM rules WHERE crop = ?', (farmer['main_crop'],)).fetchall()
                
                for rule in rules:
                    temp_ok = (rule['temp_min'] <= weather['temp'] <= rule['temp_max'])
                    humidity_ok = (weather['humidity'] >= rule['humidity_min'])
                    rain_ok = (weather['rainfall'] >= rule['rain_min']) if rule['rain_min'] > 0 else True
                    
                    if temp_ok and humidity_ok and rain_ok:
                        existing = db.execute('''
                            SELECT id FROM alerts WHERE farmer_id = ? AND pest = ? AND date(date) = date('now')
                        ''', (farmer['id'], rule['pest'])).fetchone()
                        
                        if not existing:
                            message = f"⚠️ ALERT: {rule['risk']} risk for {rule['pest']} on your {rule['crop']}!\n\n{rule['advice']}"
                            
                            db.execute('''
                                INSERT INTO alerts (farmer_id, pest, risk, message, advice, prevention, treatment, sent_via)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (farmer['id'], rule['pest'], rule['risk'], message, 
                                  rule['advice'], rule['prevention_tips'], rule['treatment_tips'], 'sms'))
                            db.commit()
                            alerts_created += 1
                            logger.info(f"📢 Alert for {farmer['name']}: {rule['risk']} risk for {rule['pest']}")
                            send_sms(farmer['phone'], message[:160])
            
            logger.info(f"✅ Alert generation completed: {alerts_created} new alerts")
            return alerts_created
            
    except Exception as e:
        logger.error(f"❌ Error generating alerts: {e}")
        return None

# ==================== USSD Handler ====================

@app.route('/ussd', methods=['POST', 'GET'])
def ussd():
    """USSD callback handler for Africa's Talking"""
    if request.method == 'GET':
        return "USSD endpoint active. Configure this URL in Africa's Talking dashboard."
    
    session_id = request.values.get('sessionId')
    phone_number = request.values.get('phoneNumber')
    text = request.values.get('text', '')
    
    logger.info(f"USSD: {session_id} | {phone_number} | text='{text}'")
    
    inputs = text.split('*') if text else []
    level = len(inputs)
    
    if level == 0:
        return "CON Welcome to Kyera Smart Agriculture\nSelect language:\n1. English\n2. Runyankole"
    elif level == 1:
        lang = inputs[0]
        if lang == '1':
            return "CON Main Menu:\n1. Weather\n2. Pest Alerts\n3. Report Pest\n4. My Profile\n0. Exit"
        elif lang == '2':
            return "CON Kyera Oburizi Bw'ebyobuhinzi\n1. Obushuhe\n2. Oburizi bw'ebidduka\n3. Okuteeka oburwaza\n4. Ebyange\n0. Ggwa"
        else:
            return "END Invalid selection"
    elif level == 2:
        if inputs[0] == '1' and inputs[1] == '1':
            weather = fetch_weather()
            if weather:
                return f"CON 🌤️ Weather in Mbarara\nTemp: {weather['temp']}°C\nHumidity: {weather['humidity']}%\nRainfall: {weather['rainfall']}mm\nConditions: {weather['conditions']}\n\nReply 0 to main menu:"
            return "END Could not fetch weather"
        elif inputs[0] == '1' and inputs[1] == '2':
            return "CON No active alerts\nReply 0 to main menu:"
        elif inputs[0] == '1' and inputs[1] == '0':
            return "END Thank you for using Kyera Smart Agriculture!"
    return "END Session timeout"

# ==================== Admin Routes ====================

@app.route('/admin')
def admin_dashboard():
    """Admin dashboard"""
    if 'farmer_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('index'))
    
    with get_db() as db:
        farmer = db.execute('SELECT * FROM farmers WHERE id = ?', (session['farmer_id'],)).fetchone()
        if not farmer or farmer['is_admin'] != 1:
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
    
    return render_template("admin.html")

@app.route('/api/admin/stats')
def api_admin_stats():
    """Get admin statistics"""
    with get_db() as db:
        total_farmers = db.execute('SELECT COUNT(*) FROM farmers WHERE is_admin = 0').fetchone()[0]
        total_alerts = db.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
        today_alerts = db.execute("SELECT COUNT(*) FROM alerts WHERE date(date) = date('now')").fetchone()[0]
        total_questions = db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
        
        return jsonify({
            'success': True,
            'data': {
                'total_farmers': total_farmers,
                'total_alerts': total_alerts,
                'today_alerts': today_alerts,
                'total_questions': total_questions
            }
        })

@app.route('/api/admin/farmers')
def api_admin_farmers():
    """Get all farmers for admin"""
    with get_db() as db:
        farmers = db.execute('SELECT id, name, phone, main_crop, village, is_admin, created FROM farmers ORDER BY id').fetchall()
        return jsonify({'success': True, 'data': [dict(f) for f in farmers]})

# ==================== Simulator Routes ====================

@app.route('/sms-simulator')
def sms_simulator():
    """SMS Simulator Dashboard"""
    return render_template('sms_simulator.html')

@app.route('/ussd-simulator')
def ussd_simulator():
    """USSD Simulator Dashboard"""
    return render_template('ussd_simulator.html')

@app.route('/simulators')
def simulators_index():
    """Simulators Index Page"""
    return render_template('simulators_index.html')

# ==================== API Routes ====================

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/api/weather', methods=['GET'])
def api_weather():
    """Get current weather data"""
    weather = fetch_weather()
    return jsonify({'success': True, 'data': weather})

@app.route('/api/weather/history', methods=['GET'])
def api_weather_history():
    """Get weather history"""
    days = request.args.get('days', 7, type=int)
    with get_db() as db:
        history = db.execute('''
            SELECT temperature, humidity, rainfall, conditions, timestamp 
            FROM weather_data 
            ORDER BY id DESC LIMIT ?
        ''', (days,)).fetchall()
        return jsonify({'success': True, 'data': [dict(row) for row in history]})

@app.route('/api/alerts/<crop>', methods=['GET'])
def api_alerts_by_crop(crop):
    """Get alerts for specific crop"""
    with get_db() as db:
        if crop == 'general':
            alerts = db.execute('''
                SELECT id, pest, risk, message, advice, prevention, treatment, date 
                FROM alerts WHERE date(date) >= date('now', '-7 days')
                ORDER BY date DESC LIMIT 10
            ''').fetchall()
        else:
            alerts = db.execute('''
                SELECT a.id, a.pest, a.risk, a.message, a.advice, a.prevention, a.treatment, a.date 
                FROM alerts a
                JOIN farmers f ON a.farmer_id = f.id
                WHERE f.main_crop = ? AND date(a.date) >= date('now', '-7 days')
                ORDER BY a.date DESC LIMIT 10
            ''', (crop,)).fetchall()
        return jsonify([dict(alert) for alert in alerts])

@app.route('/api/alerts/all', methods=['GET'])
def api_alerts_all():
    """Get all alerts"""
    with get_db() as db:
        alerts = db.execute('''
            SELECT a.id, a.pest, a.risk, a.message, a.advice, a.prevention, a.treatment, a.date, f.name as farmer_name
            FROM alerts a
            JOIN farmers f ON a.farmer_id = f.id
            ORDER BY a.date DESC LIMIT 50
        ''').fetchall()
        return jsonify([dict(alert) for alert in alerts])

@app.route('/api/history/<crop>', methods=['GET'])
def api_history(crop):
    """Get historical alerts for a crop"""
    with get_db() as db:
        if crop == 'all':
            alerts = db.execute('''
                SELECT a.id, a.pest, a.risk, a.date, f.name as farmer_name
                FROM alerts a
                JOIN farmers f ON a.farmer_id = f.id
                ORDER BY a.date DESC LIMIT 30
            ''').fetchall()
        else:
            alerts = db.execute('''
                SELECT a.id, a.pest, a.risk, a.date, f.name as farmer_name
                FROM alerts a
                JOIN farmers f ON a.farmer_id = f.id
                WHERE f.main_crop = ?
                ORDER BY a.date DESC LIMIT 30
            ''', (crop,)).fetchall()
        return jsonify([dict(alert) for alert in alerts])

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Get dashboard statistics"""
    with get_db() as db:
        farmers = db.execute('SELECT COUNT(*) FROM farmers WHERE is_admin = 0').fetchone()[0]
        total_alerts = db.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
        today_alerts = db.execute("SELECT COUNT(*) FROM alerts WHERE date(date) = date('now')").fetchone()[0]
        return jsonify({
            'success': True,
            'data': {
                'farmers': farmers,
                'total_alerts': total_alerts,
                'alerts_today': today_alerts
            }
        })

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Login endpoint - accepts name OR phone number"""
    data = request.json
    identifier = data.get('phone') or data.get('name')
    password = data.get('password')
    
    if not identifier or not password:
        return jsonify({'success': False, 'error': 'Please provide name/phone and password'}), 400
    
    with get_db() as db:
        farmer = db.execute('SELECT * FROM farmers WHERE phone = ? OR name = ?', 
                           (identifier, identifier)).fetchone()
        
        if farmer and check_password_hash(farmer['password'], password):
            session['farmer_id'] = farmer['id']
            session['farmer_name'] = farmer['name']
            session['is_admin'] = farmer['is_admin']
            return jsonify({
                'success': True,
                'authenticated': True,
                'farmer': {
                    'id': farmer['id'],
                    'name': farmer['name'],
                    'phone': farmer['phone'],
                    'main_crop': farmer['main_crop'],
                    'village': farmer['village'],
                    'is_admin': farmer['is_admin']
                }
            })
    
    return jsonify({'success': False, 'error': 'Invalid name/phone or password'}), 401

@app.route('/api/auth/check', methods=['GET'])
def api_auth_check():
    """Check if user is logged in"""
    if 'farmer_id' in session:
        with get_db() as db:
            farmer = db.execute('SELECT id, name, phone, main_crop, village, is_admin FROM farmers WHERE id = ?', 
                               (session['farmer_id'],)).fetchone()
            if farmer:
                return jsonify({'authenticated': True, 'farmer': dict(farmer)})
    return jsonify({'authenticated': False}), 401

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """Logout endpoint - clears session and forms"""
    session.clear()
    return jsonify({'success': True})

@app.route('/api/farmer/<phone>', methods=['GET'])
def api_farmer(phone):
    """Get farmer by phone"""
    with get_db() as db:
        farmer = db.execute('SELECT id, name, phone, main_crop, village, farm_size, other_crops, language FROM farmers WHERE phone = ?', (phone,)).fetchone()
        if farmer:
            return jsonify(dict(farmer))
        return jsonify({'error': 'Farmer not found'}), 404

@app.route('/api/farmer/<int:farmer_id>/stats', methods=['GET'])
def api_farmer_stats(farmer_id):
    """Get farmer statistics"""
    with get_db() as db:
        total_alerts = db.execute('SELECT COUNT(*) FROM alerts WHERE farmer_id = ?', (farmer_id,)).fetchone()[0]
        read_count = db.execute('SELECT COUNT(*) FROM alerts WHERE farmer_id = ? AND was_read = 1', (farmer_id,)).fetchone()[0]
        feedback_count = db.execute('SELECT COUNT(*) FROM feedback WHERE farmer_id = ?', (farmer_id,)).fetchone()[0]
        return jsonify({'total_alerts': total_alerts, 'read_count': read_count, 'feedback_count': feedback_count})

@app.route('/api/farmers/list', methods=['GET'])
def api_farmers_list():
    """Get list of all farmers"""
    with get_db() as db:
        farmers = db.execute('SELECT id, name, phone, main_crop FROM farmers WHERE is_admin = 0 ORDER BY name').fetchall()
        return jsonify([dict(f) for f in farmers])

@app.route('/api/register', methods=['POST'])
def api_register():
    """Register new farmer"""
    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    password = generate_password_hash(data.get('password', 'password123'))
    main_crop = data.get('main_crop', 'maize')
    village = data.get('village', '')
    farm_size = data.get('farm_size', 0)
    other_crops = data.get('other_crops', '')
    language = data.get('language', 'en')
    
    with get_db() as db:
        existing = db.execute('SELECT id FROM farmers WHERE phone = ?', (phone,)).fetchone()
        if existing:
            return jsonify({'success': False, 'error': 'Phone number already registered', 'message': 'Phone already registered'}), 400
        
        db.execute('''
            INSERT INTO farmers (name, phone, password, main_crop, village, farm_size, other_crops, language)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, phone, password, main_crop, village, farm_size, other_crops, language))
        db.commit()
        
        return jsonify({'success': True, 'message': 'Registration successful! You can now login.'})

@app.route('/api/alerts/trigger', methods=['POST'])
def api_trigger_alerts():
    """Manually trigger alert generation"""
    result = generate_and_send_alerts()
    return jsonify({'success': True, 'alerts_created': result})

@app.route('/api/questions', methods=['GET', 'POST'])
def api_questions():
    """Handle questions"""
    if request.method == 'GET':
        crop = request.args.get('crop', 'all')
        with get_db() as db:
            questions = db.execute('''
                SELECT q.*, f.name as farmer, 
                       (SELECT COUNT(*) FROM answers WHERE question_id = q.id) as answers
                FROM questions q
                JOIN farmers f ON q.farmer_id = f.id
                ORDER BY q.created DESC LIMIT 20
            ''').fetchall()
            return jsonify({'questions': [dict(q) for q in questions]})
    
    elif request.method == 'POST':
        if 'farmer_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        data = request.json
        with get_db() as db:
            db.execute('''
                INSERT INTO questions (farmer_id, crop, title, question)
                VALUES (?, ?, ?, ?)
            ''', (session['farmer_id'], data.get('crop'), data.get('title'), data.get('question')))
            db.commit()
            return jsonify({'success': True})

@app.route('/api/questions/<int:question_id>', methods=['GET'])
def api_question_detail(question_id):
    """Get question details"""
    with get_db() as db:
        db.execute('UPDATE questions SET views = views + 1 WHERE id = ?', (question_id,))
        db.commit()
        
        question = db.execute('''
            SELECT q.*, f.name as farmer
            FROM questions q
            JOIN farmers f ON q.farmer_id = f.id
            WHERE q.id = ?
        ''', (question_id,)).fetchone()
        
        answers = db.execute('''
            SELECT a.*, f.name as farmer,
                   (SELECT COUNT(*) FROM answer_likes WHERE answer_id = a.id) as likes
            FROM answers a
            JOIN farmers f ON a.farmer_id = f.id
            WHERE a.question_id = ?
            ORDER BY a.is_best DESC, a.created ASC
        ''', (question_id,)).fetchall()
        
        result = dict(question)
        result['answers'] = [dict(a) for a in answers]
        return jsonify(result)

@app.route('/api/questions/<int:question_id>/answers', methods=['POST'])
def api_add_answer(question_id):
    """Add answer to question"""
    if 'farmer_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    with get_db() as db:
        db.execute('''
            INSERT INTO answers (question_id, farmer_id, answer)
            VALUES (?, ?, ?)
        ''', (question_id, session['farmer_id'], data.get('answer')))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/answers/<int:answer_id>/like', methods=['POST'])
def api_like_answer(answer_id):
    """Like an answer"""
    if 'farmer_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    with get_db() as db:
        existing = db.execute('SELECT id FROM answer_likes WHERE answer_id = ? AND farmer_id = ?',
                              (answer_id, session['farmer_id'])).fetchone()
        if existing:
            db.execute('DELETE FROM answer_likes WHERE id = ?', (existing['id'],))
            db.execute('UPDATE answers SET likes = likes - 1 WHERE id = ?', (answer_id,))
        else:
            db.execute('INSERT INTO answer_likes (answer_id, farmer_id) VALUES (?, ?)', (answer_id, session['farmer_id']))
            db.execute('UPDATE answers SET likes = likes + 1 WHERE id = ?', (answer_id,))
        db.commit()
        return jsonify({'success': True})

# ==================== Scheduler ====================

scheduler = BackgroundScheduler()
scheduler.add_job(func=generate_and_send_alerts, trigger="interval", hours=6, id="alert_generation")
scheduler.start()
logger.info("✅ Alert scheduler started (runs every 6 hours)")

# ==================== Main Entry Point ====================


@app.route('/api/pest-rules', methods=['GET'])
def get_pest_rules():
    return jsonify({'rules': [
        {'id': 1, 'pest_name': 'Armyworm', 'crop_type': 'maize', 'recommended_action': 'Spray pesticide', 'threshold': 30},
        {'id': 2, 'pest_name': 'Aphids', 'crop_type': 'beans', 'recommended_action': 'Neem oil', 'threshold': 50}
    ]})

@app.route('/api/farming-tips', methods=['GET'])
def get_farming_tips():
    return jsonify({'tips': [
        {'id': 1, 'title': 'Water Conservation', 'content': 'Water early morning', 'date': '2024-01-01'},
        {'id': 2, 'title': 'Soil Health', 'content': 'Test pH regularly', 'date': '2024-01-01'}
    ]})

@app.route('/api/experts', methods=['GET'])
def get_experts():
    with get_db() as db:
        experts = db.execute('SELECT id, name, phone, main_crop FROM farmers WHERE is_expert = 1 LIMIT 10').fetchall()
        return jsonify({'experts': [dict(e) for e in experts]})

@app.route('/api/alerts/list', methods=['GET'])
def get_alerts_list():
    with get_db() as db:
        alerts = db.execute('SELECT id, message, "info" as type, date FROM alerts ORDER BY date DESC LIMIT 20').fetchall()
        return jsonify([dict(a) for a in alerts])

def get_pest_rules():
    with get_db() as db:
        rules = db.execute('SELECT id, pest_name, crop_type, recommended_action, threshold FROM pest_rules').fetchall()
        return jsonify({'rules': [dict(r) for r in rules]})

def get_farming_tips():
    with get_db() as db:
        tips = db.execute('SELECT id, title, content, date FROM farming_tips ORDER BY date DESC').fetchall()
        return jsonify({'tips': [dict(t) for t in tips]})

def get_experts():
    with get_db() as db:
        experts = db.execute('SELECT id, name, phone, main_crop, village FROM farmers WHERE is_expert = 1').fetchall()
        return jsonify({'experts': [dict(e) for e in experts]})

def get_alerts_list():
    with get_db() as db:
        alerts = db.execute('SELECT id, message, "info" as type, date FROM alerts ORDER BY date DESC LIMIT 20').fetchall()
        return jsonify([dict(a) for a in alerts])
if __name__ == '__main__':
    init_db()
    print("\n" + "="*60)
    print("🚀 Kyera Smart Agriculture App Started!")
    print("="*60)
    print("\n🔐 LOGIN CREDENTIALS:")
    print("   Admin: Phone: +256700000001 | Password: admin123")
    print("   Farmer: Phone: 256700000000 | Password: kyerafarmer123")
    print("\n🌐 ACCESS:")
    print("   Main App: http://127.0.0.1:5000")
    print("   Admin Dashboard: http://127.0.0.1:5000/admin")
    print("   SMS Simulator: http://127.0.0.1:5000/sms-simulator")
    print("   USSD Simulator: http://127.0.0.1:5000/ussd-simulator")
    print("   Simulators Index: http://127.0.0.1:5000/simulators")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)

@app.route('/login')
def login_page():
    return render_template('login.html')

    with get_db() as db:
        rules = db.execute('SELECT id, pest_name, crop_type, recommended_action, threshold FROM pest_rules LIMIT 50').fetchall()
        return jsonify({'rules': [dict(r) for r in rules]})

def get_farming_tips_admin():
    with get_db() as db:
        tips = db.execute('SELECT id, title, content, date FROM farming_tips ORDER BY date DESC LIMIT 50').fetchall()
        return jsonify({'tips': [dict(t) for t in tips]})

@app.route('/api/broadcast/send', methods=['POST'])
def send_broadcast():
    data = request.json
    message = data.get('message')
    if not message:
        return jsonify({'success': False, 'message': 'Message required'}), 400
    
    with get_db() as db:
        farmers = db.execute('SELECT COUNT(*) as count FROM farmers WHERE is_admin = 0').fetchone()
        db.execute('INSERT INTO alerts (message, type) VALUES (?, ?)', (f'📢 BROADCAST: {message}', 'broadcast'))
        db.commit()
        return jsonify({'success': True, 'message': f'Broadcast sent to {farmers["count"]} farmers'})

def get_experts_list():
    with get_db() as db:
        experts = db.execute('SELECT id, name, phone, main_crop, village FROM farmers WHERE is_expert = 1 LIMIT 50').fetchall()
        return jsonify({'experts': [dict(e) for e in experts]})

    with get_db() as db:
        rules = db.execute('SELECT id, pest_name, crop_type, recommended_action, threshold FROM pest_rules').fetchall()
        return jsonify({'rules': [dict(r) for r in rules]})

def get_farming_tips_admin():
    with get_db() as db:
        tips = db.execute('SELECT id, title, content, date FROM farming_tips ORDER BY date DESC').fetchall()
        return jsonify({'tips': [dict(t) for t in tips]})

def get_experts_admin():
    with get_db() as db:
        experts = db.execute('SELECT id, name, phone, main_crop, village FROM farmers WHERE is_expert = 1').fetchall()
        return jsonify({'experts': [dict(e) for e in experts]})

def get_alerts_list_admin():
    with get_db() as db:
        alerts = db.execute('SELECT id, message, "info" as type, date FROM alerts ORDER BY date DESC LIMIT 20').fetchall()
        return jsonify([dict(a) for a in alerts])

def get_pest_rules():
    return jsonify({'rules': [
        {'id': 1, 'pest_name': 'Armyworm', 'crop_type': 'maize', 'recommended_action': 'Spray pesticide', 'threshold': 30},
        {'id': 2, 'pest_name': 'Aphids', 'crop_type': 'beans', 'recommended_action': 'Neem oil', 'threshold': 50}
    ]})

def get_farming_tips():
    return jsonify({'tips': [
        {'id': 1, 'title': 'Water Smart', 'content': 'Water early morning', 'date': '2024-01-01'},
        {'id': 2, 'title': 'Soil Health', 'content': 'Test pH regularly', 'date': '2024-01-01'}
    ]})

def get_experts():
    with get_db() as db:
        experts = db.execute('SELECT id, name, phone, main_crop FROM farmers WHERE is_expert = 1 LIMIT 10').fetchall()
        return jsonify({'experts': [dict(e) for e in experts]})

def get_alerts_list():
    with get_db() as db:
        alerts = db.execute('SELECT id, message, "info" as type, date FROM alerts ORDER BY date DESC LIMIT 20').fetchall()
        return jsonify([dict(a) for a in alerts])

# ============ ALERTS CRUD ============
@app.route('/api/alerts/add', methods=['POST'])
def add_alert():
    data = request.json
    with get_db() as db:
        db.execute('INSERT INTO alerts (message, risk, pest, advice, prevention, treatment) VALUES (?, ?, ?, ?, ?, ?)',
                   (data['message'], data.get('risk', 'info'), data.get('pest', 'General'), 
                    data.get('advice', ''), data.get('prevention', ''), data.get('treatment', '')))
        db.commit()
        return jsonify({'success': True, 'message': 'Alert added'})

@app.route('/api/alerts/update/<int:alert_id>', methods=['PUT'])
def update_alert(alert_id):
    data = request.json
    with get_db() as db:
        db.execute('UPDATE alerts SET message=?, risk=?, pest=?, advice=?, prevention=?, treatment=? WHERE id=?',
                   (data['message'], data.get('risk', 'info'), data.get('pest', 'General'),
                    data.get('advice', ''), data.get('prevention', ''), data.get('treatment', ''), alert_id))
        db.commit()
        return jsonify({'success': True, 'message': 'Alert updated'})

@app.route('/api/alerts/delete/<int:alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    with get_db() as db:
        db.execute('DELETE FROM alerts WHERE id=?', (alert_id,))
        db.commit()
        return jsonify({'success': True, 'message': 'Alert deleted'})

# ============ PEST RULES CRUD ============
@app.route('/api/pest-rules/add', methods=['POST'])
def add_pest_rule():
    data = request.json
    with get_db() as db:
        db.execute('INSERT INTO pest_rules (pest_name, crop_type, recommended_action, threshold) VALUES (?, ?, ?, ?)',
                   (data['pest_name'], data.get('crop_type', 'general'), data['recommended_action'], data.get('threshold', 70)))
        db.commit()
        return jsonify({'success': True, 'message': 'Pest rule added'})

@app.route('/api/pest-rules/update/<int:rule_id>', methods=['PUT'])
def update_pest_rule(rule_id):
    data = request.json
    with get_db() as db:
        db.execute('UPDATE pest_rules SET pest_name=?, crop_type=?, recommended_action=?, threshold=? WHERE id=?',
                   (data['pest_name'], data.get('crop_type', 'general'), data['recommended_action'], data.get('threshold', 70), rule_id))
        db.commit()
        return jsonify({'success': True, 'message': 'Pest rule updated'})

@app.route('/api/pest-rules/delete/<int:rule_id>', methods=['DELETE'])
def delete_pest_rule(rule_id):
    with get_db() as db:
        db.execute('DELETE FROM pest_rules WHERE id=?', (rule_id,))
        db.commit()
        return jsonify({'success': True, 'message': 'Pest rule deleted'})

# ============ FARMING TIPS CRUD ============
@app.route('/api/farming-tips/add', methods=['POST'])
def add_farming_tip():
    data = request.json
    with get_db() as db:
        db.execute('INSERT INTO farming_tips (title, content) VALUES (?, ?)',
                   (data['title'], data['content']))
        db.commit()
        return jsonify({'success': True, 'message': 'Farming tip added'})

@app.route('/api/farming-tips/update/<int:tip_id>', methods=['PUT'])
def update_farming_tip(tip_id):
    data = request.json
    with get_db() as db:
        db.execute('UPDATE farming_tips SET title=?, content=? WHERE id=?',
                   (data['title'], data['content'], tip_id))
        db.commit()
        return jsonify({'success': True, 'message': 'Farming tip updated'})

@app.route('/api/farming-tips/delete/<int:tip_id>', methods=['DELETE'])
def delete_farming_tip(tip_id):
    with get_db() as db:
        db.execute('DELETE FROM farming_tips WHERE id=?', (tip_id,))
        db.commit()
        return jsonify({'success': True, 'message': 'Farming tip deleted'})

# ============ EXPERTS MANAGEMENT ============
@app.route('/api/experts/make/<int:farmer_id>', methods=['POST'])
def make_expert(farmer_id):
    with get_db() as db:
        db.execute('UPDATE farmers SET is_expert = 1 WHERE id=?', (farmer_id,))
        db.commit()
        return jsonify({'success': True, 'message': 'Farmer marked as expert'})

@app.route('/api/experts/remove/<int:farmer_id>', methods=['POST'])
def remove_expert(farmer_id):
    with get_db() as db:
        db.execute('UPDATE farmers SET is_expert = 0 WHERE id=?', (farmer_id,))
        db.commit()
        return jsonify({'success': True, 'message': 'Expert status removed'})
