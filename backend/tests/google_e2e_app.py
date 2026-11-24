"""Isolated E2E server: only certificate transport is replaced, never verification."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from app.db.session import engine

if not (os.getenv('GOOGLE_E2E_TRANSPORT') == 'true'
        and engine.url.database.startswith('vitalsync_test_audit_')
        and engine.url.database == os.getenv('VITALSYNC_TEST_DATABASE_NAME')):
    raise RuntimeError('Google fixture transport requires an explicitly isolated audit database')

from app.main import app
from app.routers import google_auth

def certificate_transport(*args, **kwargs):
    return SimpleNamespace(status=200, data=Path('/tmp/google-test-certificates.json').read_bytes())

google_auth.GoogleRequest = lambda: certificate_transport
