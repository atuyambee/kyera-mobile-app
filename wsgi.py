import sys
import os

# Add your project directory to the path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.insert(0, path)

# Import your app
from app import app as application

# For PythonAnywhere, you need this
application.secret_key = os.getenv('SECRET_KEY', 'kyera-smart-agriculture-secret-key-2025')
