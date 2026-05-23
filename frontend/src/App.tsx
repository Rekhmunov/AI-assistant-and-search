import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { BottomNav } from "./components/BottomNav";
import { useAuthBootstrap } from "./hooks/useAuth";
import { t } from "./i18n";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { Profile } from "./pages/Profile";
import { Thread } from "./pages/Thread";

const queryClient = new QueryClient();

function AppRoutes() {
  const { ready, error } = useAuthBootstrap();

  if (!ready) return <div className="loading-screen">{t("loading")}</div>;
  if (error) return <div className="loading-screen">{error}</div>;

  return (
    <div className="app-shell">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/thread" element={<Thread />} />
        <Route path="/thread/:id" element={<Thread />} />
        <Route path="/history" element={<History />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <BottomNav />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
