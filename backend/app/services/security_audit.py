"""Independent durable metadata for denials/errors; never log request bodies or query strings."""
import logging
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import AdminEvent,SessionToken
from app.core.security import digest

def record(request,status):
    if status not in (401,403,500,503):return
    try:
        with SessionLocal.begin() as db:
            session=db.get(SessionToken,digest(request.cookies.get('vitalsync_session','')))
            route=request.scope.get('route')
            db.add(AdminEvent(actor_id=session.user_id if session else None,action='SECURITY_DENIED' if status in (401,403) else 'REQUEST_FAILED',resource='request',reason='Acceso denegado' if status in (401,403) else 'Operación revertida por error',details={'status':status,'method':request.method,'route':getattr(route,'path','unmatched')}))
    except Exception as error:
        logging.getLogger('vitalsync').warning('No se pudo persistir metadato de seguridad (%s)',type(error).__name__)
