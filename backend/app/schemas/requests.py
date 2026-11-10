import re
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator, model_validator

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Login(Input):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class Register(Login):
    given_names: str = Field(min_length=2, max_length=60)
    surnames: str = Field(min_length=2, max_length=60)
    password: str = Field(min_length=10, max_length=128)
    document_type: Literal['CC'] = 'CC'
    document_number: str
    phone: str = Field(min_length=7, max_length=30, pattern=r'^[+\d\s()\-]+$')
    privacy_accepted: Literal[True]

    @model_validator(mode='after')
    def full_name_fits_user_record(self):
        if len(self.given_names.strip()) + len(self.surnames.strip()) + 1 > 120:
            raise ValueError('El nombre completo debe tener como máximo 120 caracteres')
        return self

    @field_validator('document_number', mode='before')
    @classmethod
    def validate_document_number(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{6,10}', value):
            raise ValueError('La cédula debe tener de 6 a 10 dígitos, sin espacios ni puntos')
        return value

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, value):
        if not any(char.islower() for char in value) or not any(char.isupper() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError('Usa mayúsculas, minúsculas y al menos un número')
        return value

    @field_validator('phone')
    @classmethod
    def validate_phone_digits(cls, value):
        if not 7 <= sum(char.isdigit() for char in value) <= 15:
            raise ValueError('Ingresa un teléfono con entre 7 y 15 dígitos')
        return value


class Profile(Input):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default='', max_length=30, pattern=r'^[+\d\s()\-]*$')
    document_type: Literal['CC'] | None = None
    document_number: str | None = None
    privacy_accepted: Literal[True] | None = None

    @field_validator('document_number', mode='before')
    @classmethod
    def validate_optional_document_number(cls, value):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r'[0-9]{6,10}', value)):
            raise ValueError('La cédula debe tener de 6 a 10 dígitos, sin espacios ni puntos')
        return value

    @model_validator(mode='after')
    def document_fields_are_together(self):
        if (self.document_type is None) != (self.document_number is None):
            raise ValueError('Indica el tipo y el número de documento')
        return self

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
    event: Literal['ADVANCE_DEMO_CLOCK','OPEN_ROOM','PATIENT_JOIN','DOCTOR_JOIN','START','FINALIZE','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ERROR','RETRY'] | None = None
    status: Literal['SALA_DISPONIBLE','PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE'] | None = None
    reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode='after')
    def require_one_transition(self):
        if (self.event is None) == (self.status is None):
            raise ValueError('Indica un evento de teleconsulta')
        return self

class Cancel(Input):
    version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    confirmed: Literal[True]
