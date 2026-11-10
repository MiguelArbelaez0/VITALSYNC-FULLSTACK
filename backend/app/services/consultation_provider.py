"""Provider boundary for future audiovisual rooms; the current provider is demo only."""
from typing import Protocol


class ConsultationProvider(Protocol):
    name: str
    is_demo: bool
    message: str


class DemoTeleconsultationProvider:
    name = 'demo'
    is_demo = True
    message = 'Teleconsulta simulada — sin conexión de audio o video'
