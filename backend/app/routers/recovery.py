from fastapi import APIRouter,Depends
from sqlalchemy import select,delete
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.admin import RecoveryInput
from app.core.security import digest,passwords
from app.models.entities import RecoveryRequest,User,DoctorAccount,Doctor,DoctorCredentialState,SessionToken,now
from app.services.admin_portal import fail,audit
router=APIRouter(tags=['auth'])

@router.post('/api/auth/recover')
def recover(data:RecoveryInput,db:Session=Depends(get_db,scope='function')):
    grant=db.scalar(select(RecoveryRequest).where(RecoveryRequest.token_hash==digest(data.token)).with_for_update())
    if not grant or grant.status!='ISSUED' or grant.expires_at<=now():fail('El enlace no está disponible o ha vencido. Solicita una nueva recuperación.',400)
    user=db.scalar(select(User).where(User.id==grant.user_id).with_for_update())
    if not user or user.status!='ACTIVE':fail('El enlace no está disponible o ha vencido. Solicita una nueva recuperación.',400)
    if user.role=='DOCTOR':
        doctor=db.scalar(select(Doctor).join(DoctorAccount,DoctorAccount.doctor_id==Doctor.id).where(DoctorAccount.user_id==user.id,Doctor.enabled))
        if not doctor:fail('La cuenta profesional no está habilitada',403)
    user.password_hash=passwords.hash(data.new_password)
    state=db.get(DoctorCredentialState,user.id)
    if state:state.must_change_password=False;state.changed_at=now()
    grant.status='USED';grant.consumed_at=now()
    db.execute(delete(SessionToken).where(SessionToken.user_id==user.id))
    audit(db,user,'ACCESS_RECOVERY_COMPLETED','account',user.id,'Contraseña elegida por el titular mediante un enlace de un solo uso')
    return {'message':'Contraseña guardada. Inicia sesión con tu nueva contraseña individual.'}
