import { modes, type Field, type Options } from "./AdminCore";
export function fields(options: Options | undefined) {
  const specialties =
    options?.specialties.map((s) => ({ value: s.id, label: s.name })) ?? [];
  const doctors =
    options?.doctors.map((d) => ({ value: d.id, label: d.name })) ?? [];
  const doctorFields: Field[] = [
    { key: "name", label: "Nombre profesional", min: 3, max: 120 },
    {
      key: "specialty_id",
      label: "Especialidad",
      type: "number",
      options: specialties,
    },
    {
      key: "bio",
      label: "Biografía profesional",
      type: "textarea",
      min: 10,
      wide: true,
    },
    {
      key: "modalities",
      label: "Modalidades ofrecidas",
      type: "multi",
      options: modes,
    },
    { key: "enabled", label: "Perfil y cuenta habilitados", type: "checkbox" },
  ];
  const planFields: Field[] = [
    { key: "name", label: "Nombre del plan", min: 2, max: 50 },
    {
      key: "price",
      label: "Precio simulado (COP)",
      type: "number",
      min: 0,
      max: 100000000,
    },
    {
      key: "description",
      label: "Descripción",
      type: "textarea",
      min: 5,
      wide: true,
    },
    {
      key: "duration_days",
      label: "Vigencia en días",
      type: "number",
      min: 1,
      max: 730,
    },
    { key: "copay", label: "Copago base (COP)", type: "number", min: 0 },
    {
      key: "virtual_copay",
      label: "Copago virtual (vacío: base)",
      type: "number",
      min: 0,
      required: false,
    },
    {
      key: "onsite_copay",
      label: "Copago presencial (vacío: base)",
      type: "number",
      min: 0,
      required: false,
    },
    {
      key: "consultation_limit",
      label: "Consultas por contratación (vacío: sin límite)",
      type: "number",
      min: 1,
      required: false,
    },
    {
      key: "modalities",
      label: "Cobertura por modalidad",
      type: "multi",
      options: modes,
    },
    {
      key: "specialty_ids",
      label: "Especialidades cubiertas",
      type: "multi",
      options: specialties,
    },
    {
      key: "benefits",
      label: "Beneficios",
      type: "textarea",
      required: false,
      wide: true,
    },
    {
      key: "restrictions",
      label: "Restricciones informativas",
      type: "textarea",
      required: false,
      wide: true,
    },
    {
      key: "enabled",
      label: "Disponible para nuevas contrataciones y renovaciones",
      type: "checkbox",
    },
  ];
  const slotFields: Field[] = [
    { key: "doctor_id", label: "Médico", type: "number", options: doctors },
    {
      key: "starts_at",
      label: "Inicio · hora de Bogotá",
      type: "datetime-local",
    },
    { key: "ends_at", label: "Fin · hora de Bogotá", type: "datetime-local" },
    {
      key: "modalities",
      label: "Modalidades del turno",
      type: "multi",
      options: modes,
    },
    {
      key: "published",
      label: "Publicado y visible para reservar",
      type: "checkbox",
    },
  ];
  return { doctorFields, planFields, slotFields };
}
