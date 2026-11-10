"""Appointment side of virtual consultation lifecycle transitions."""


def start(appointment):
    appointment.status = 'IN_PROGRESS'
    appointment.version += 1


def finalize(appointment, timestamp):
    appointment.status = 'ATTENDED'
    appointment.attended_at = timestamp
    appointment.completion_source = 'DEMO'
    appointment.simulated_completed_at = timestamp
    appointment.clinically_attended = False
    appointment.version += 1


def mark_absent(appointment, status, timestamp, reason):
    appointment.status = status
    appointment.incidence_at = timestamp
    appointment.incidence_reason = reason
    appointment.version += 1


def mark_technical_issue(appointment, timestamp, reason):
    appointment.status = 'TECHNICAL_ERROR'
    appointment.incidence_at = timestamp
    appointment.incidence_reason = reason
    appointment.version += 1
