/// <reference types="vite/client" />

interface MaxWebAppUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string | null;
  language_code?: string;
}

interface MaxWebApp {
  initData: string;
  initDataUnsafe: { user?: MaxWebAppUser };
  ready: () => void;
  close: () => void;
}

interface Window {
  WebApp?: MaxWebApp;
}
