"""Issue single-use recovery links to a private LOCAL file, never to an HTTP response."""
import argparse,json,os,secrets
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select,text
from app.core.config import DEMO_MODE
from app.core.security import digest
from app.db.session import SessionLocal
from app.models.entities import User,RecoveryRequest,now
from app.services.admin_portal import request_recovery,audit,scopes

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--actor-email',default='admin@vitalsync.demo')
    p.add_argument('--email',help='Solicita un enlace para una cuenta existente, únicamente en modo demostración')
    args=p.parse_args();created=False
    try:
        with SessionLocal.begin() as db:
            db.execute(text('SELECT pg_advisory_xact_lock(861998)'))
            actor=db.scalar(select(User).where(User.email==args.actor_email,User.role=='ADMIN',User.status=='ACTIVE'))
            if not actor or 'accounts' not in scopes(db,actor):raise ValueError('Actor administrativo no autorizado')
            if args.email:
                if not DEMO_MODE:raise ValueError('La solicitud directa local requiere modo demostración')
                target=db.scalar(select(User).where(User.email==args.email))
                if not target:raise ValueError('Cuenta inexistente')
                request_recovery(db,actor,target,'Recuperación local explícita de la cuenta de demostración')
            issued=[]
            for r in db.scalars(select(RecoveryRequest).where(RecoveryRequest.status=='PENDING').order_by(RecoveryRequest.id).with_for_update()):
                user=db.get(User,r.user_id)
                if user.status!='ACTIVE':continue
                if user.role=='ADMIN' and not scopes(db,user)<=scopes(db,actor):continue
                token=secrets.token_urlsafe(48);r.token_hash=digest(token);r.status='ISSUED';r.expires_at=now()+timedelta(hours=24)
                issued.append(dict(request_id=r.id,email=user.email,role=user.role,token=token,expires_at=r.expires_at.isoformat(),local_url='http://localhost:5188/recover#token='+token))
                audit(db,actor,'ACCESS_RECOVERY_ISSUED','account',user.id,'Enlace de un solo uso emitido mediante entrega local privada',{'request_id':r.id})
            fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);created=True
            with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump({'recovery_links':issued},f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        print(json.dumps({'issued':len(issued),'private_file':str(args.output),'passwords_changed':0}))
    except Exception:
        if created:args.output.unlink(missing_ok=True)
        raise SystemExit('No se emitieron enlaces: transacción revertida. Revisa cuenta, permisos y archivo exclusivo de salida.') from None

if __name__=='__main__':main()
