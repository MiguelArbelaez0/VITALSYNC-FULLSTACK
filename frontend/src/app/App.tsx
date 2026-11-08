import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { Loading, Empty, Go, ErrorBox } from "../components/common";
import { Layout } from "./Layout";
import { Landing } from "./Landing";
import { Auth } from "../features/auth/Auth";
import { Profile } from "../features/auth/Profile";
import { Dashboard } from "../features/dashboard/Dashboard";
import { Plans } from "../features/plans/Plans";
import { Doctors, DoctorProfile } from "../features/doctors/Doctors";
import { Booking } from "../features/appointments/Booking";
import {
  Appointments,
  AppointmentDetail,
} from "../features/appointments/Appointments";
import { Notifications } from "../features/notifications/Notifications";
export function Protected() {
  const { user, loading, error } = useAuth();
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "PATIENT")
    return (
      <Empty title="Acceso exclusivo para pacientes">
        <Go to="/">Volver al inicio</Go>
      </Empty>
    );
  return <Outlet />;
}
export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Auth />} />
      <Route path="/register" element={<Auth register />} />
      <Route element={<Protected />}>
        <Route path="/portal" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="profile" element={<Profile />} />
          <Route path="plans" element={<Plans />} />
          <Route path="doctors" element={<Doctors />} />
          <Route path="doctors/:id" element={<DoctorProfile />} />
          <Route path="booking/:id" element={<Booking />} />
          <Route path="appointments" element={<Appointments />} />
          <Route path="appointments/:id" element={<AppointmentDetail />} />
          <Route path="notifications" element={<Notifications />} />
        </Route>
      </Route>
      <Route
        path="*"
        element={
          <Empty title="No encontramos esta página">
            <Go to="/">Volver al inicio</Go>
          </Empty>
        }
      />
    </Routes>
  );
}
