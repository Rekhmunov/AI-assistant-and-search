import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import { Layout } from "./components/Layout";
import { AdminsPage } from "./pages/Admins";
import { AuditPage } from "./pages/Audit";
import { BroadcastsPage } from "./pages/Broadcasts";
import { DashboardPage } from "./pages/Dashboard";
import { LoginPage } from "./pages/Login";
import { PaymentsPage } from "./pages/Payments";
import { SettingsPage } from "./pages/Settings";
import { UserDetailPage } from "./pages/UserDetail";
import { UsersPage } from "./pages/Users";

function ProtectedApp() {
  const { admin, loading } = useAuth();
  if (loading) return <div className="center">Загрузка…</div>;
  if (!admin) return <Navigate to="/login" replace />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="broadcasts" element={<BroadcastsPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="users/:id" element={<UserDetailPage />} />
        <Route path="payments" element={<PaymentsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="admins" element={<AdminsPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/*" element={<ProtectedApp />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
