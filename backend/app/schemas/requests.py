from typing import Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Login(Input):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class Register(Login):
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)

class Profile(Input):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default='', max_length=30, pattern=r'^[+\d\s()\-]*$')

PaymentStatus = Literal['APPROVED', 'REJECTED', 'PENDING', 'IN_RECONCILIATION']

class PaymentInput(Input):
    kind: Literal['PLAN', 'COPAY']
    target_id: int = Field(gt=0)
    status: PaymentStatus
    idempotency_key: str = Field(min_length=16, max_length=80)

class Reconcile(Input):
    status: Literal['APPROVED', 'REJECTED']

class CancelPlanInput(Input):
    plan_id: int = Field(gt=0)
    confirmed: Literal[True]

class HoldInput(Input):
    availability_id: int = Field(gt=0)
    modality: Literal['PRESENCIAL', 'VIRTUAL'] = 'PRESENCIAL'

class TeleconsultationStatus(Input):
    status: Literal['SALA_DISPONIBLE','PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE']

class Cancel(Input):
    version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    confirmed: Literal[True]
