import { useCallback, useRef, useState } from "react";
import { t } from "../i18n";
import { isMaxWebApp } from "../lib/maxApp";

type VoiceState = "idle" | "recording" | "transcribing";

function getSpeechRecognitionCtor():
  | (new () => SpeechRecognition)
  | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function getRecognitionError(ev: Event): string {
  const err = (ev as SpeechRecognitionErrorEvent).error;
  return typeof err === "string" ? err : "";
}

function collectFinalTranscript(ev: SpeechRecognitionEvent): string {
  let text = "";
  for (let i = 0; i < ev.results.length; i++) {
    const chunk = ev.results[i];
    if (chunk.isFinal) {
      text += chunk[0]?.transcript ?? "";
    }
  }
  return text.trim();
}

/** Browser speech recognition; press mic to start, press again to stop. */
export function useVoiceInput(onText: (text: string) => void) {
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const transcriptRef = useRef("");
  const recordingRef = useRef(false);
  const startedAtRef = useRef(0);
  const userStopRef = useRef(false);

  const releaseMic = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const finishSession = useCallback(
    (opts?: { showNoSpeech?: boolean }) => {
      recordingRef.current = false;
      releaseMic();
      recognitionRef.current = null;

      const text = transcriptRef.current.trim();
      transcriptRef.current = "";

      if (text) {
        onText(text);
        setError(null);
        setState("idle");
        return;
      }

      const elapsed = Date.now() - startedAtRef.current;
      if (opts?.showNoSpeech && elapsed >= 600) {
        setError(t("voiceNoSpeech"));
      }
      setState("idle");
    },
    [onText, releaseMic],
  );

  const stop = useCallback(() => {
    if (!recordingRef.current) return;
    userStopRef.current = true;
    setState("transcribing");
    try {
      recognitionRef.current?.stop();
    } catch {
      finishSession({ showNoSpeech: true });
    }
  }, [finishSession]);

  const start = useCallback(async () => {
    setError(null);
    userStopRef.current = false;
    transcriptRef.current = "";

    if (navigator.mediaDevices?.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        releaseMic();
        streamRef.current = stream;
      } catch {
        setError(isMaxWebApp() ? t("voiceMicDeniedMax") : t("voiceMicDenied"));
        return;
      }
    }

    const SR = getSpeechRecognitionCtor();
    if (!SR) {
      releaseMic();
      setError(t("voiceUnavailable"));
      return;
    }

    const rec = new SR();
    rec.lang = "ru-RU";
    rec.continuous = true;
    rec.interimResults = false;
    rec.maxAlternatives = 1;

    recognitionRef.current = rec;
    recordingRef.current = true;
    startedAtRef.current = Date.now();
    setState("recording");

    rec.onresult = (ev: SpeechRecognitionEvent) => {
      const chunk = collectFinalTranscript(ev);
      if (chunk) {
        transcriptRef.current = transcriptRef.current
          ? `${transcriptRef.current} ${chunk}`
          : chunk;
      }
    };

    rec.onerror = (ev: Event) => {
      const code = getRecognitionError(ev);
      const elapsed = Date.now() - startedAtRef.current;

      if (code === "aborted") return;

      recordingRef.current = false;
      releaseMic();
      recognitionRef.current = null;
      setState("idle");

      if (code === "not-allowed" || code === "audio-capture") {
        setError(isMaxWebApp() ? t("voiceMicDeniedMax") : t("voiceMicDenied"));
        return;
      }

      if (code === "service-not-allowed" || code === "network") {
        setError(isMaxWebApp() ? t("voiceUnavailableMax") : t("voiceUnavailable"));
        return;
      }

      if (code === "no-speech") {
        if (userStopRef.current && elapsed >= 600) {
          setError(t("voiceNoSpeech"));
        }
        return;
      }

      if (elapsed < 400) {
        setError(isMaxWebApp() ? t("voiceUnavailableMax") : t("voiceStartFailed"));
        return;
      }

      setError(t("voiceRecognizeFailed"));
    };

    rec.onend = () => {
      if (!userStopRef.current && recordingRef.current) {
        try {
          rec.start();
        } catch {
          finishSession();
        }
        return;
      }
      finishSession({ showNoSpeech: userStopRef.current });
    };

    try {
      rec.start();
    } catch {
      recordingRef.current = false;
      releaseMic();
      recognitionRef.current = null;
      setState("idle");
      setError(t("voiceStartFailed"));
    }
  }, [finishSession, releaseMic]);

  const toggle = useCallback(() => {
    if (state === "recording") {
      stop();
    } else if (state === "idle") {
      void start();
    }
  }, [state, start, stop]);

  return { state, error, toggle, stop };
}
