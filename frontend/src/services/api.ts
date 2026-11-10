export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "include",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const data = await response
    .json()
    .catch(() => ({ detail: "El servicio no devolvió una respuesta válida" }));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : "Revisa los datos del formulario",
      response.status,
    );
  }
  return data as T;
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const money = (n: number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(n);
export const dateText = (s: string) =>
  new Intl.DateTimeFormat("es-CO", {
    dateStyle: "long",
    timeZone: "America/Bogota",
  }).format(new Date(s));
export const timeText = (s: string) =>
  new Intl.DateTimeFormat("es-CO", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Bogota",
  }).format(new Date(s));
export const dayKey = (s: string) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(s));
export const statuses: Record<string, string> = {
  ACTIVE: "Activo",
  INACTIVE: "Sin activar",
  EXPIRED: "Vencido",
  CONFIRMED: "Confirmada",
  ERROR_TECNICO: "Error técnico",
  TECHNICAL_ERROR: "Incidencia técnica",
  IN_PROGRESS: "En atención",
  DEMO_COMPLETED: "Finalizada (simulación)",
  PATIENT_ABSENT: "Paciente ausente",
  DOCTOR_ABSENT: "Médico ausente",
  CANCELLED: "Cancelada",
  ATTENDED: "Finalizada",
  APPROVED: "Aprobado",
  REJECTED: "Rechazado",
  PENDING: "Pendiente",
  IN_RECONCILIATION: "En conciliación",
  PROGRAMADA: "Programada",
  SALA_DISPONIBLE: "Sala disponible",
  PACIENTE_EN_ESPERA: "Paciente en espera",
  MEDICO_EN_ESPERA: "Médico en espera",
  AMBOS_PRESENTES: "Paciente y médico presentes",
  EN_ESPERA: "En espera",
  EN_ATENCION: "En atención simulada",
  FINALIZADA: "Finalizada",
  PACIENTE_AUSENTE: "Paciente ausente",
  MEDICO_AUSENTE: "Médico ausente",
  VIRTUAL_PROGRAMADA: "Teleconsulta programada",
  VIRTUAL_SALA_DISPONIBLE: "Sala virtual disponible",
  VIRTUAL_EN_ESPERA: "Participantes en espera",
  VIRTUAL_EN_ATENCION: "Teleconsulta en atención",
  VIRTUAL_FINALIZADA: "Teleconsulta finalizada",
  VIRTUAL_PACIENTE_AUSENTE: "Teleconsulta: paciente ausente",
  VIRTUAL_MEDICO_AUSENTE: "Teleconsulta: médico ausente",
  VIRTUAL_ERROR_TECNICO: "Teleconsulta: incidencia técnica",
  VIRTUAL_CANCELADA: "Teleconsulta cancelada",
};
