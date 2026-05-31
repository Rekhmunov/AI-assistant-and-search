/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_MAX_BOT_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  onresult: ((ev: SpeechRecognitionEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message?: string;
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

declare var SpeechRecognition: {
  prototype: SpeechRecognition;
  new (): SpeechRecognition;
};

declare var webkitSpeechRecognition: {
  prototype: SpeechRecognition;
  new (): SpeechRecognition;
};

interface WebAppUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
}

interface WebAppInitDataUnsafe {
  user?: WebAppUser;
  start_param?: string;
}

interface WebAppBackButton {
  show: () => void;
  hide: () => void;
  isVisible: boolean;
  onClick: (callback: () => void) => void;
  offClick: (callback: () => void) => void;
}

interface WebAppBridge {
  initData: string;
  initDataUnsafe: WebAppInitDataUnsafe;
  ready: () => void;
  close: () => void;
  platform?: string;
  version?: string;
  openLink?: (url: string) => void;
  openMaxLink?: (url: string) => void;
  BackButton?: WebAppBackButton;
}

interface Window {
  WebApp?: WebAppBridge;
}
