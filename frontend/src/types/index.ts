export interface User {
  id: number;
  name: string;
  email: string;
  phone: string;
  role: string;
}
export interface Plan {
  id: number;
  name: string;
  description: string;
  price: number;
  copay: number;
  duration_days: number;
  specialty_ids: number[];
}
export interface Membership {
  status: string;
  plan: Plan | null;
  expires_at: string | null;
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
}
export interface Slot {
  id: number;
  starts_at: string;
  ends_at: string;
  available: boolean;
}
export interface Hold {
  id: number;
  doctor_id: number;
  starts_at: string;
  ends_at: string;
  expires_at: string;
  copay: number;
  status: string;
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
  cancelled_at: string | null;
  cancellation_reason: string | null;
  economic_review: boolean;
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
