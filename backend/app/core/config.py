import os

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://vitalsync:local_demo_change_me@localhost:5488/vitalsync')
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'
HOLD_MINUTES = int(os.getenv('HOLD_MINUTES', '10'))
CANCELLATION_HOURS = int(os.getenv('CANCELLATION_HOURS', '2'))
TELECONSULT_ROOM_OPEN_MINUTES = int(os.getenv('TELECONSULT_ROOM_OPEN_MINUTES', '5'))
TELECONSULT_WAIT_GRACE_MINUTES = int(os.getenv('TELECONSULT_WAIT_GRACE_MINUTES', '15'))
SESSION_HOURS = int(os.getenv('SESSION_HOURS', '12'))
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5188,http://127.0.0.1:5188,http://localhost:8088').split(',')
LIVEKIT_ENABLED = os.getenv('LIVEKIT_ENABLED', 'false').lower() == 'true'
LIVEKIT_API_URL = os.getenv('LIVEKIT_API_URL', 'http://livekit:7880')
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY', '')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET', '')
LIVEKIT_PUBLIC_URL = os.getenv('LIVEKIT_PUBLIC_URL', 'ws://localhost:7880')
LIVEKIT_TOKEN_TTL_SECONDS = int(os.getenv('LIVEKIT_TOKEN_TTL_SECONDS', '600'))
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '').strip()
DOCTOR_CREDENTIAL_KEY = os.getenv('DOCTOR_CREDENTIAL_KEY', '').strip()
