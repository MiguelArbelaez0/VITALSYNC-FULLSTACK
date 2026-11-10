export interface User {
  id: number;
  name: string;
  email: string;
  phone: string;
  role: string;
  document_type?: string | null;
  document_masked?: string | null;
  has_document?: boolean;
  account_status?: string;
  registered_at?: string;
  privacy_notice_version?: string | null;
  privacy_accepted_at?: string | null;
}
export interface Plan {
  id: number;
  name: string;
  description: string;
  price: number;
  copay: number;
  duration_days: number;
  specialty_ids: number[];
  modalities: Modality[];
}
export type Modality = 'PRESENCIAL' | 'VIRTUAL';
export interface Membership {
  status: string;
  plan: Plan | null;
  expires_at: string | null;
  cancelled_at?: string | null;
  cancelled_by?: number | null;
  cancellation_history?: PlanCancellationHistory[];
}
export interface PlanCancellationHistory {
  id: number;
  plan_id: number;
  plan_name: string;
  previous_status: string;
  new_status: string;
  policy: "IMMEDIATE";
  cancelled_at: string;
  effective_at: string;
  changed_by: number;
  reason: string;
}
export interface Specialty {
  id: number;
  name: string;
}
export interface Doctor {
  id: number;
  name: string;
  specialty_id: number;
  specialty: string;
  bio: string;
  enabled: boolean;
  modalities: Modality[];
}
export interface Slot {
  id: number;
  starts_at: string;
  ends_at: string;
  available: boolean;
  modalities: Modality[];
}
export interface Hold {
  id: number;
  doctor_id: number;
  starts_at: string;
  ends_at: string;
  expires_at: string;
  copay: number;
  status: string;
  modality: Modality;
}
export interface Payment {
  id: number;
  kind: string;
  plan_id: number | null;
  hold_id: number | null;
  amount: number;
  status: string;
  created_at: string;
}
export interface Appointment {
  completion_source?: "DEMO" | null;
  simulated_completed_at?: string | null;
  clinically_attended?: boolean;
  demo_mode?: boolean;
  patient_present_at?: string | null;
  doctor_present_at?: string | null;
  id: number;
  code: string;
  doctor: string;
  specialty: string;
  patient?: string;
  plan: string;
  starts_at: string;
  ends_at: string;
  status: string;
  version: number;
  copay: number;
  modality: Modality;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  economic_review: boolean;
  location: string|null;
  virtual_status: string|null;
  history?: {
    id: number;
    status: string;
    reason: string;
    created_at: string;
  }[];
}
export interface DashboardData {
  name: string;
  plan: Membership;
  upcoming_count: number;
  next_appointment: Appointment | null;
  unread_notifications: number;
}
export interface Notice {
  id: number;
  message: string;
  read: boolean;
  created_at: string;
}
export interface Config {
  demo_mode: boolean;
  hold_minutes: number;
  cancellation_hours: number;
  timezone: string;
}
