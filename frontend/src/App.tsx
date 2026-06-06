import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { AppNavigation } from "./components/AppNavigation";
import { useAuthBootstrap } from "./hooks/useAuth";
import { t } from "./i18n";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { LoginPage } from "./pages/Login";
import { Profile } from "./pages/Profile";
import { SourceViewPage } from "./pages/SourceViewPage";
import { LegalCompliance } from "./components/LegalCompliance";
import { LegalPathCatch } from "./components/LegalPathCatch";
import { Thread } from "./pages/Thread";

const queryClient = new QueryClient();

function AppRoutes() {
  const { ready, error } = useAuthBootstrap();

  return (
    <div className="app-shell">
      <AppNavigation />
      <main className="app-main">
        {error ? (
          <div className="app-boot-error">{error}</div>
        ) : ready ? (
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<Home />} />
            <Route path="/thread" element={<Thread />} />
            <Route path="/thread/:id" element={<Thread />} />
            <Route path="/history" element={<History />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/source-view" element={<SourceViewPage />} />
            <Route path="*" element={<LegalPathCatch />} />
          </Routes>
        ) : (
          <div className="app-boot-placeholder" aria-busy="true" aria-label={t("pageLoading")}>
            {t("pageLoading")}
          </div>
        )}
      </main>
      {ready && <LegalCompliance />}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppErrorBoundary>
          <AppRoutes />
        </AppErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
