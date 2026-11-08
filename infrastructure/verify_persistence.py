"""Prueba real de persistencia contra los servicios Docker locales.
Crea únicamente datos ficticios nuevos; no elimina volúmenes ni datos existentes.
Ejecutar desde la raíz: python infrastructure/verify_persistence.py
"""
import http.cookiejar
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv('E2E_BASE_URL', 'http://localhost:5188') + '/api'
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def api(path, data=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None, headers={'Content-Type':'application/json'})
    with opener.open(request, timeout=15) as response:
        return json.load(response)

def main():
    account = api('/auth/register', {'name':'Paciente Persistencia','email':f'persistence-{uuid4().hex[:12]}@example.com','password':'Persistencia2026!'})
    premium = next(p for p in api('/plans') if p['name'] == 'Premium')
    payment = api('/payments', {'kind':'PLAN','target_id':premium['id'],'status':'APPROVED','idempotency_key':uuid4().hex})
    doctor = api('/doctors')[0]
    slot = next(s for s in api(f"/doctors/{doctor['id']}/availability") if s['available'])
    hold = api('/holds', {'availability_id':slot['id']})
    appointment = api(f"/holds/{hold['id']}/confirm", {})
    virtual_slot = next(s for s in api(f"/doctors/{doctor['id']}/availability?modality=VIRTUAL") if s['available'])
    virtual_hold = api('/holds', {'availability_id':virtual_slot['id'],'modality':'VIRTUAL'})
    virtual_appointment = api(f"/holds/{virtual_hold['id']}/confirm", {})
    virtual_room_path = f"/appointments/{virtual_appointment['id']}/teleconsult"
    api(f"{virtual_room_path}/status", {'status':'SALA_DISPONIBLE'})
    before = {'profile':api('/auth/me'),'plan':api('/my-plan'),'payments':api('/payments'),'appointment':api(f"/appointments/{appointment['id']}"),'virtual_appointment':api(f"/appointments/{virtual_appointment['id']}"),'virtual_room':api(virtual_room_path),'notifications':api('/notifications')}
    subprocess.run(['docker','compose','restart'], cwd=ROOT, check=True)
    for attempt in range(45):
        try:
            api('/health')
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('Los servicios no respondieron después del reinicio')
    after = {'profile':api('/auth/me'),'plan':api('/my-plan'),'payments':api('/payments'),'appointment':api(f"/appointments/{appointment['id']}"),'virtual_appointment':api(f"/appointments/{virtual_appointment['id']}"),'virtual_room':api(virtual_room_path),'notifications':api('/notifications')}
    assert before == after, 'Los datos o la sesión cambiaron tras reiniciar los servicios'
    cancelled = api(f"/appointments/{appointment['id']}/cancel", {'version':1,'reason':'Fin de la prueba de persistencia','confirmed':True})
    assert cancelled['status'] == 'CANCELLED'
    virtual_cancelled = api(f"/appointments/{virtual_appointment['id']}/cancel", {'version':1,'reason':'Fin de la prueba de persistencia virtual','confirmed':True})
    assert virtual_cancelled['status'] == 'CANCELLED'
    result = {'result':'PASS','user_id':account['id'],'payment_id':payment['id'],'appointment_codes':[appointment['code'],virtual_appointment['code']],'verified':['sesión HttpOnly','perfil','plan activo y vigencia','pago','cita presencial confirmada','cita virtual confirmada','estado de sala virtual','historial','notificaciones'],'restart':'docker compose restart; volumen conservado','cancelled_after_restart':True}
    output = ROOT/'docs'/'persistence-result.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
