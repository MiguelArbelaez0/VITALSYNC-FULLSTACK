import os

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://vitalsync:local_demo_change_me@localhost:5488/vitalsync')
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'
HOLD_MINUTES = int(os.getenv('HOLD_MINUTES', '10'))
CANCELLATION_HOURS = int(os.getenv('CANCELLATION_HOURS', '2'))
SESSION_HOURS = int(os.getenv('SESSION_HOURS', '12'))
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5188,http://127.0.0.1:5188,http://localhost:8088').split(',')
