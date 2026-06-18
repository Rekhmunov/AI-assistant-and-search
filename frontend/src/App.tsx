import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { AppNavigation } from "./components/AppNavigation";
import { useAuthBootstrap } from "./hooks/useAuth";
import { useMaxDeepLink } from "./hooks/useMaxDeepLink";
import { usePageRobots } from "./hooks/usePageRobots";
import { t } from "./i18n";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { LoginPage } from "./pages/Login";
import { Profile } from "./pages/Profile";
import { SourceViewPage } from "./pages/SourceViewPage";
import { LegalCompliance } from "./components/LegalCompliance";
import { ProPaymentReturnHandler } from "./components/ProPaymentReturnHandler";
import { LegalPathCatch } from "./components/LegalPathCatch";
import { BlogPage } from "./pages/Blog";
import { BlogCategoryPage } from "./pages/BlogCategory";
import { BlogPostPage } from "./pages/BlogPost";
import { Thread } from "./pages/Thread";
import { AgentsPage } from "./pages/Agents";

const queryClient = new QueryClient();

function AppRoutes() {
  const { ready, error } = useAuthBootstrap();
  const booting = !ready && !error;
  useMaxDeepLink();

  return (
    <div className={`app-shell${booting ? " app-shell--booting" : ""}`}>
      <AppNavigation />
      <main className="app-main">
        {error ? (
          <div className="app-boot-error">{error}</div>
        ) : (
          <>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/" element={<Home />} />
              <Route path="/thread" element={<Thread />} />
              <Route path="/thread/:id" element={<Thread />} />
              <Route path="/history" element={<History />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/source-view" element={<SourceViewPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/blog" element={<BlogPage />} />
              <Route path="/blog/category/:slug" element={<BlogCategoryPage />} />
              <Route path="/blog/:slug" element={<BlogPostPage />} />
              <Route path="*" element={<LegalPathCatch />} />
            </Routes>
            {booting && (
              <div className="app-boot-overlay" role="status" aria-live="polite" aria-busy="true">
                {t("pageLoading")}
              </div>
            )}
          </>
        )}
      </main>
      {!booting && !error && <LegalCompliance />}
      <ProPaymentReturnHandler ready={ready || !booting} />
    </div>
  );
}

function AppShell() {
  usePageRobots();
  return (
    <AppErrorBoundary>
      <AppRoutes />
    </AppErrorBoundary>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
