from typing import Literal
from datetime import date,time
from pydantic import Field,EmailStr,AwareDatetime,model_validator,field_validator
from app.schemas.requests import Input,DoctorPasswordChange

Modality=Literal['VIRTUAL','PRESENCIAL']
class Reason(Input):
    reason:str=Field(min_length=6,max_length=1000)
class DoctorInput(Reason):
    name:str=Field(min_length=3,max_length=120)
    specialty_id:int=Field(gt=0)
    bio:str=Field(min_length=10,max_length=4000)
    modalities:list[Modality]=Field(min_length=1,max_length=2)
    enabled:bool=True
class DoctorCreate(DoctorInput):
    email:EmailStr
class SpecialtyInput(Reason):
    name:str=Field(min_length=3,max_length=100)
class AccountStatus(Reason):
    status:Literal['ACTIVE','DISABLED']
class PlanInput(Reason):
    name:str=Field(min_length=2,max_length=50)
    description:str=Field(min_length=5,max_length=4000)
    price:int=Field(ge=0,le=100000000)
    duration_days:int=Field(gt=0,le=730)
    copay:int=Field(ge=0,le=100000000)
    virtual_copay:int|None=Field(default=None,ge=0,le=100000000)
    onsite_copay:int|None=Field(default=None,ge=0,le=100000000)
    consultation_limit:int|None=Field(default=None,gt=0,le=10000)
    specialty_ids:list[int]=Field(min_length=1,max_length=100)
    modalities:list[Modality]=Field(min_length=1,max_length=2)
    enabled:bool=True
    benefits:str=Field(default='',max_length=4000)
    restrictions:str=Field(default='',max_length=4000)
    version:int=Field(default=1,gt=0)
    @field_validator('specialty_ids')
    @classmethod
    def distinct_positive(cls,v):
        if min(v)<=0 or len(set(v))!=len(v):raise ValueError('Selecciona especialidades distintas válidas')
        return v
class SlotInput(Reason):
    doctor_id:int=Field(gt=0)
    starts_at:AwareDatetime
    ends_at:AwareDatetime
    modalities:list[Modality]=Field(min_length=1,max_length=2)
    published:bool=True
    @model_validator(mode='after')
    def times(self):
        if self.ends_at<=self.starts_at or (self.ends_at-self.starts_at).total_seconds()>14400:raise ValueError('El turno debe durar de 1 minuto a 4 horas')
        return self
class ScheduleInput(Reason):
    doctor_id:int=Field(gt=0)
    first_day:date
    last_day:date
    start_time:time
    end_time:time
    minutes:Literal[15,20,30,45,60]=30
    weekdays:list[int]=Field(default_factory=lambda:list(range(7)),min_length=1,max_length=7)
    modalities:list[Modality]=Field(min_length=1,max_length=2)
    published:bool=True
    @model_validator(mode='after')
    def range(self):
        if not 0<=(self.last_day-self.first_day).days<=30 or self.end_time<=self.start_time or any(x<0 or x>6 for x in self.weekdays):raise ValueError('Jornada inválida: máximo 31 días y final posterior al inicio')
        return self
class BlockInput(Reason):
    doctor_id:int=Field(gt=0)
    starts_at:AwareDatetime
    ends_at:AwareDatetime
    @model_validator(mode='after')
    def times(self):
        if self.ends_at<=self.starts_at:raise ValueError('La fecha final debe ser posterior a la inicial')
        return self
class ReconcileInput(Reason):
    status:Literal['APPROVED','REJECTED']
class RefundCreate(Reason):
    payment_id:int=Field(gt=0)
    operation_key:str=Field(min_length=8,max_length=80)
class RefundStep(Reason):
    status:Literal['REVIEWING','APPROVED','REJECTED','AUTHORIZED','PROCESSED','FAILED']
    version:int=Field(gt=0)
    operation_key:str=Field(min_length=8,max_length=80)
class RescheduleInput(Reason):
    replacement_id:int=Field(gt=0)
class PermissionInput(Reason):
    scopes:list[str]=Field(max_length=12)
class AdminCreate(PermissionInput):
    name:str=Field(min_length=3,max_length=120)
    email:EmailStr
class RecoveryInput(Input):
    token:str=Field(min_length=40,max_length=128)
    new_password:str=Field(min_length=12,max_length=128)
    confirm_password:str=Field(min_length=12,max_length=128)
    @model_validator(mode='after')
    def secure(self):
        if self.new_password!=self.confirm_password or not all((any(c.isupper() for c in self.new_password),any(c.islower() for c in self.new_password),any(c.isdigit() for c in self.new_password))):raise ValueError('La contraseña debe coincidir y contener mayúscula, minúscula y número')
        return self
class SettingsInput(Reason):
    display_name:str=Field(min_length=3,max_length=120)
    support_email:EmailStr
    support_phone:str=Field(min_length=7,max_length=30,pattern=r'^[+0-9 ()-]+$')
