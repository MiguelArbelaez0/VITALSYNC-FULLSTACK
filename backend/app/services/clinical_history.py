"""Fictional clinical read model with treatment-relationship authorization."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, text, inspect
from app.core.config import DEMO_MODE
from app.models.entities import (User, Patient, Doctor, Specialty, Appointment, DemoPatient, ClinicalHistory,
    ClinicalBackground, ClinicalAllergy, ClinicalMedication, ClinicalEncounter, AuditEvent, now)
from app.core.security import passwords
import secrets

MARKER = 'DATOS FICTICIOS DE DEMOSTRACIÓN'
AUTHORIZED_STATES = ('CONFIRMED','IN_PROGRESS','ATTENDED')


def has_relationship(db, doctor_id, patient_id, lock=False):
    query=select(Appointment.id).where(Appointment.doctor_id==doctor_id,
        Appointment.patient_id==patient_id,Appointment.status.in_(AUTHORIZED_STATES)).limit(1)
    return db.scalar(query.with_for_update(read=True) if lock else query) is not None


def available(db, doctor_id, patient_id):
    return bool(DEMO_MODE and has_relationship(db,doctor_id,patient_id) and db.scalar(
        select(ClinicalHistory.id).where(ClinicalHistory.patient_id==patient_id)))


def authorized_history(db, doctor, patient_id):
    if not has_relationship(db,doctor.id,patient_id,lock=True):
        raise HTTPException(404,'Historia clínica no disponible para tu relación asistencial')
    if not DEMO_MODE:
        raise HTTPException(403,'Los registros ficticios están disponibles solo en el entorno académico')
    history=db.scalar(select(ClinicalHistory).where(ClinicalHistory.patient_id==patient_id))
    if not history:
        raise HTTPException(404,'No hay una historia ficticia registrada para este paciente')
    return history


def encounter_summary(row, doctor_name, specialty):
    return dict(id=row.id,occurred_at=row.occurred_at,doctor=doctor_name,specialty=specialty,
                reason=row.reason,diagnosis=row.diagnosis)


def read_history(db, doctor, actor, patient_id):
    history=authorized_history(db,doctor,patient_id)
    user=db.get(User,patient_id)
    today=now().astimezone(ZoneInfo('America/Bogota')).date()
    age=None
    if history.birth_date:
        age=today.year-history.birth_date.year-((today.month,today.day)<(history.birth_date.month,history.birth_date.day))
    rows=db.execute(select(ClinicalEncounter,Doctor.name,Specialty.name).join(Doctor,Doctor.id==ClinicalEncounter.doctor_id)
        .join(Specialty,Specialty.id==ClinicalEncounter.specialty_id).where(ClinicalEncounter.history_id==history.id)
        .order_by(ClinicalEncounter.occurred_at.desc(),ClinicalEncounter.id.desc())).all()
    db.add(AuditEvent(actor_id=actor.id,action='CLINICAL_HISTORY_VIEWED',entity_id=history.id))
    db.flush()  # Do not deliver clinical content if the required audit cannot persist.
    return dict(id=history.id,demo_marker=history.demo_marker,read_only=True,
        patient=dict(id=patient_id,name=user.name,birth_date=history.birth_date,age=age,demographic_note=history.demographic_note),
        backgrounds=[dict(category=b.category,description=b.description) for b in db.scalars(select(ClinicalBackground).where(ClinicalBackground.history_id==history.id).order_by(ClinicalBackground.category))],
        allergies=[dict(substance=a.substance,reaction=a.reaction) for a in db.scalars(select(ClinicalAllergy).where(ClinicalAllergy.history_id==history.id).order_by(ClinicalAllergy.id))],
        medications=[dict(name=m.name,note=m.note,status=m.status) for m in db.scalars(select(ClinicalMedication).where(ClinicalMedication.history_id==history.id).order_by(ClinicalMedication.id))],
        encounters=[encounter_summary(*row) for row in rows])


def read_encounter(db, doctor, actor, patient_id, encounter_id):
    history=authorized_history(db,doctor,patient_id)
    row=db.execute(select(ClinicalEncounter,Doctor.name,Specialty.name).join(Doctor,Doctor.id==ClinicalEncounter.doctor_id)
        .join(Specialty,Specialty.id==ClinicalEncounter.specialty_id).where(ClinicalEncounter.history_id==history.id,
        ClinicalEncounter.id==encounter_id)).first()
    if not row:
        raise HTTPException(404,'Consulta no disponible en esta historia autorizada')
    encounter=row[0]
    db.add(AuditEvent(actor_id=actor.id,action='CLINICAL_ENCOUNTER_VIEWED',entity_id=encounter.id))
    db.flush()
    return dict(**encounter_summary(*row),patient_id=patient_id,demo_marker=history.demo_marker,
                observations=encounter.observations,recommendations=encounter.recommendations,vitals=encounter.vitals)


def seed_histories(db, include_extra_patients=False):
    if not DEMO_MODE:
        return dict(histories_created=0,patients_created=0)
    schema=db.scalar(text('SELECT current_schema()'))
    if not inspect(db.connection()).has_table('clinical_histories',schema=schema):
        return dict(histories_created=0,patients_created=0)
    db.execute(text('SELECT pg_advisory_xact_lock(861994)'))
    admin=db.scalar(select(User).where(User.role=='ADMIN',User.status=='ACTIVE').order_by(User.id))
    if not admin:
        raise ValueError('Se requiere un actor administrativo activo para el seed ficticio')
    builtin=db.scalar(select(User).join(Patient,Patient.id==User.id).where(User.email=='paciente@vitalsync.demo',
        User.name=='Valentina Torres',User.role=='PATIENT',User.privacy_accepted_at.is_(None),Patient.document_number.is_(None)))
    if builtin and not db.get(DemoPatient,builtin.id):
        db.add(DemoPatient(patient_id=builtin.id,source='BUILTIN_SEED',confirmed_by=admin.id));db.flush()
        db.add(AuditEvent(actor_id=admin.id,action='DEMO_PATIENT_IDENTIFIED',entity_id=builtin.id))
    patients_created=0
    if include_extra_patients:
        for name,email in [('Lucía Demostración Académica','demo.lucia@vitalsync.demo'),('Santiago Demostración Académica','demo.santiago@vitalsync.demo')]:
            existing=db.scalar(select(User).where(User.email==email))
            if existing:
                # An email collision never authorizes relabeling a real patient as fictional.
                if not db.get(DemoPatient,existing.id):
                    raise ValueError('El correo de demostración ya existe sin procedencia ficticia; requiere revisión')
                continue
            u=User(name=name,email=email,role='PATIENT',password_hash=passwords.hash(secrets.token_urlsafe(48)))
            db.add(u);db.flush();db.add(Patient(id=u.id,phone=''));db.flush()
            db.add(DemoPatient(patient_id=u.id,source='OPERATOR_CONFIRMED',confirmed_by=admin.id));db.flush()
            db.add(AuditEvent(actor_id=admin.id,action='DEMO_PATIENT_CREATED',entity_id=u.id));patients_created+=1
    professionals=db.scalars(select(Doctor).order_by(Doctor.id).limit(3)).all()
    if not professionals:
        return dict(histories_created=0,patients_created=patients_created)
    templates=[
        dict(personal='Rinitis estacional ficticia, sin episodios agudos simulados.',family='Antecedente familiar ficticio de hipertensión.',surgery='No se registran procedimientos en este ejemplo académico.',disease='Rinitis alérgica ficticia.',allergy='Polen de demostración',reaction='Estornudos simulados.',medication='Antihistamínico académico A',observation='Ejemplo académico de control preventivo y seguimiento de síntomas estacionales.'),
        dict(personal='Migraña episódica ficticia y seguimiento académico de bienestar.',family='Historia familiar simulada de migraña.',surgery='Procedimiento menor ficticio sin complicaciones en el escenario académico.',disease='Cefalea episódica ficticia.',allergy='Sustancia de prueba B',reaction='Reacción cutánea ficticia leve.',medication='Medicación académica B',observation='Ejemplo ficticio de control de cefalea episódica sin signos de alarma simulados.'),
        dict(personal='Dermatitis de contacto ficticia con evolución simulada favorable.',family='No se describen antecedentes familiares en este escenario ficticio.',surgery='Sin antecedentes quirúrgicos simulados.',disease='Dermatitis de contacto ficticia.',allergy='Material de prueba C',reaction='Irritación local simulada.',medication='Preparación académica C',observation='Ejemplo académico de revisión de piel y registro de evolución ficticia.')]
    created=0
    for demo in db.scalars(select(DemoPatient).order_by(DemoPatient.patient_id)):
        if db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.patient_id==demo.patient_id)):
            continue  # Existing histories are never modified, completed or reset by a seed.
        sample=templates[demo.patient_id%len(templates)]
        h=ClinicalHistory(patient_id=demo.patient_id,demographic_note='Identidad académica expresamente identificada como ficticia. Fecha de nacimiento no registrada.')
        db.add(h);db.flush()
        for category,key in [('PERSONAL','personal'),('FAMILY','family'),('SURGICAL','surgery'),('PREVIOUS_DISEASE','disease')]:
            db.add(ClinicalBackground(history_id=h.id,category=category,description=sample[key]))
        db.add(ClinicalAllergy(history_id=h.id,substance=sample['allergy'],reaction=sample['reaction']))
        db.add(ClinicalMedication(history_id=h.id,name=sample['medication'],status='CURRENT',note='Etiqueta ficticia de demostración; sin dosis, prescripción ni indicación para uso real.'))
        db.add(ClinicalMedication(history_id=h.id,name='Registro académico previo',status='PREVIOUS',note='Tratamiento anterior completamente ficticio; no administrar.'))
        for index,days in enumerate([90,45,14]):
            professional=professionals[index%len(professionals)]
            db.add(ClinicalEncounter(history_id=h.id,doctor_id=professional.id,specialty_id=professional.specialty_id,
                seed_key=f'academic-visit-{index+1}',occurred_at=now()-timedelta(days=days),
                reason=['Control preventivo ficticio','Seguimiento académico simulado','Revisión de evolución ficticia'][index],
                observations=sample['observation'],diagnosis=sample['disease'] if index else 'Evaluación preventiva ficticia',
                recommendations='Registro académico de orientación y seguimiento simulado. No constituye una recomendación médica real.',
                vitals={'systolic':118+index*2,'diastolic':76,'heart_rate':70+index,'temperature_c':36.6,'spo2':98}))
        db.add(AuditEvent(actor_id=admin.id,action='DEMO_CLINICAL_HISTORY_CREATED',entity_id=h.id));created+=1
    db.flush()
    return dict(histories_created=created,patients_created=patients_created)
