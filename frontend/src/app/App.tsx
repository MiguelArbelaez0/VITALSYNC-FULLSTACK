import { lazy, Suspense } from "react";
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
import { Teleconsultation } from "../features/appointments/Appointments";
import { Notifications } from "../features/notifications/Notifications";
import {
  DoctorDashboard,
  DoctorAgenda,
  DoctorDetail,
  DoctorPatients,
  DoctorProfilePage,
  DoctorAvailability,
  DoctorRoom,
} from "../features/doctor/DoctorPortal";
import { DoctorClinicalHistory } from "../features/doctor/ClinicalHistory";
import { DoctorPasswordSetup } from "../features/doctor/DoctorPassword";
const AdminPortal = lazy(() => import("../features/admin/AdminPortal"));
const Recover = lazy(() => import("../features/admin/Recover"));
export function Protected({
  role = "PATIENT",
}: {
  role?: "PATIENT" | "DOCTOR" | "ADMIN";
}) {
  const { user, loading, error } = useAuth();
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role)
    return (
      <Empty
        title={
          role === "ADMIN"
            ? "Acceso exclusivo para administradores"
            : role === "PATIENT"
              ? "Acceso exclusivo para pacientes"
              : "Acceso exclusivo para médicos"
        }
      >
        <Go
          to={
            user.role === "ADMIN"
              ? "/admin"
              : user.role === "DOCTOR"
                ? "/doctor"
                : user.role === "PATIENT"
                  ? "/portal"
                  : "/"
          }
        >
          Volver a mi espacio
        </Go>
      </Empty>
    );
  if (role === "DOCTOR" && !user.doctor_id)
    return (
      <ErrorBox
        error={
          new Error(
            "Tu cuenta no tiene un perfil profesional válido. Contacta a VITALSYNC.",
          )
        }
      />
    );
  if (role === "DOCTOR" && user.must_change_password)
    return <DoctorPasswordSetup />;
  return <Outlet />;
}
export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Auth />} />
      <Route path="/register" element={<Auth register />} />
      <Route
        path="/recover"
        element={
          <Suspense fallback={<Loading />}>
            <Recover />
          </Suspense>
        }
      />
      <Route element={<Protected role="ADMIN" />}>
        <Route path="/admin" element={<Layout admin />}>
          <Route
            index
            element={
              <Suspense fallback={<Loading />}>
                <AdminPortal />
              </Suspense>
            }
          />
          <Route
            path=":section"
            element={
              <Suspense fallback={<Loading />}>
                <AdminPortal />
              </Suspense>
            }
          />
        </Route>
      </Route>
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
          <Route
            path="appointments/:id/teleconsult"
            element={<Teleconsultation />}
          />
          <Route path="notifications" element={<Notifications />} />
        </Route>
      </Route>
      <Route element={<Protected role="DOCTOR" />}>
        <Route path="/doctor" element={<Layout doctor />}>
          <Route index element={<DoctorDashboard />} />
          <Route path="appointments" element={<DoctorAgenda />} />
          <Route path="appointments/:id" element={<DoctorDetail />} />
          <Route path="appointments/:id/teleconsult" element={<DoctorRoom />} />
          <Route path="patients" element={<DoctorPatients />} />
          <Route
            path="patients/:id/clinical-history"
            element={<DoctorClinicalHistory />}
          />
          <Route path="profile" element={<DoctorProfilePage />} />
          <Route path="availability" element={<DoctorAvailability />} />
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
