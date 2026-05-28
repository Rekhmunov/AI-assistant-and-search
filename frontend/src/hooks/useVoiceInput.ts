import { useCallback, useRef, useState } from "react";
import { transcribeVoice } from "../api/client";
import { t } from "../i18n";
import { isMaxWebApp } from "../lib/maxApp";

type VoiceState = "idle" | "recording" | "transcribing";

const MAX_RECORD_MS = 90_000;

function getSpeechRecognitionCtor(): (new () => SpeechRecognition) | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function preferServerStt(): boolean {
  if (isMaxWebApp()) return true;
  if (typeof MediaRecorder === "undefined") return false;
  return !getSpeechRecognitionCtor();
}

function pickRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/aac",
    "audio/ogg;codecs=opus",
  ];
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return undefined;
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

/** Голосовой ввод: Web Speech API в браузере; в MAX — запись + сервер (Yandex STT). */
export function useVoiceInput(onText: (text: string) => void, token: string | null) {
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const recorderMimeRef = useRef<string>("audio/webm");
  const transcriptRef = useRef("");
  const recordingRef = useRef(false);
  const startedAtRef = useRef(0);
  const userStopRef = useRef(false);
  const autoStopTimerRef = useRef<number | null>(null);

  const clearAutoStop = useCallback(() => {
    if (autoStopTimerRef.current !== null) {
      window.clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
  }, []);

  const releaseMic = useCallback(() => {
    clearAutoStop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
  }, [clearAutoStop]);

  const finishBrowserSession = useCallback(
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

  const uploadRecording = useCallback(
    async (blob: Blob) => {
      if (!token) {
        setError(t("loginForFiles"));
        setState("idle");
        return;
      }
      setState("transcribing");
      try {
        const res = await transcribeVoice(token, blob);
        const text = res.text.trim();
        if (!text) {
          setError(t("voiceNoSpeech"));
        } else {
          onText(text);
          setError(null);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : t("voiceRecognizeFailed"));
      } finally {
        releaseMic();
        recordingRef.current = false;
        setState("idle");
      }
    },
    [onText, releaseMic, token],
  );

  const stopServerRecording = useCallback(() => {
    if (!recordingRef.current) return;
    userStopRef.current = true;
    clearAutoStop();
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") {
      try {
        rec.stop();
      } catch {
        recordingRef.current = false;
        releaseMic();
        setState("idle");
      }
      return;
    }
    recordingRef.current = false;
    releaseMic();
    setState("idle");
  }, [clearAutoStop, releaseMic]);

  const startServerRecording = useCallback(async () => {
    setError(null);
    userStopRef.current = false;
    chunksRef.current = [];

    if (!token) {
      setError(t("loginForFiles"));
      return;
    }

    const mimeType = pickRecorderMimeType();
    if (!mimeType || !navigator.mediaDevices?.getUserMedia) {
      setError(t("voiceUnavailableMax"));
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      releaseMic();
      streamRef.current = stream;
      recorderMimeRef.current = mimeType;

      const rec = new MediaRecorder(stream, { mimeType });
      recorderRef.current = rec;

      rec.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };

      rec.onerror = () => {
        recordingRef.current = false;
        releaseMic();
        setState("idle");
        setError(t("voiceStartFailed"));
      };

      rec.onstop = () => {
        const chunks = chunksRef.current;
        chunksRef.current = [];
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;

        if (!userStopRef.current) {
          recordingRef.current = false;
          setState("idle");
          return;
        }

        const blob = new Blob(chunks, { type: mimeType });
        const elapsed = Date.now() - startedAtRef.current;
        if (blob.size < 256 || elapsed < 400) {
          recordingRef.current = false;
          setError(t("voiceNoSpeech"));
          setState("idle");
          return;
        }
        void uploadRecording(blob);
      };

      recordingRef.current = true;
      startedAtRef.current = Date.now();
      setState("recording");
      rec.start(250);
      autoStopTimerRef.current = window.setTimeout(() => {
        if (recordingRef.current) stopServerRecording();
      }, MAX_RECORD_MS);
    } catch {
      releaseMic();
      setError(isMaxWebApp() ? t("voiceMicDeniedMax") : t("voiceMicDenied"));
    }
  }, [releaseMic, stopServerRecording, token, uploadRecording]);

  const stopBrowserRecording = useCallback(() => {
    if (!recordingRef.current) return;
    userStopRef.current = true;
    setState("transcribing");
    try {
      recognitionRef.current?.stop();
    } catch {
      finishBrowserSession({ showNoSpeech: true });
    }
  }, [finishBrowserSession]);

  const startBrowserRecording = useCallback(async () => {
    setError(null);
    userStopRef.current = false;
    transcriptRef.current = "";

    if (navigator.mediaDevices?.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        releaseMic();
        streamRef.current = stream;
      } catch {
        setError(t("voiceMicDenied"));
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
        setError(t("voiceMicDenied"));
        return;
      }

      if (code === "service-not-allowed" || code === "network") {
        setError(t("voiceUnavailable"));
        return;
      }

      if (code === "no-speech") {
        if (userStopRef.current && elapsed >= 600) {
          setError(t("voiceNoSpeech"));
        }
        return;
      }

      if (elapsed < 400) {
        setError(t("voiceStartFailed"));
        return;
      }

      setError(t("voiceRecognizeFailed"));
    };

    rec.onend = () => {
      if (!userStopRef.current && recordingRef.current) {
        try {
          rec.start();
        } catch {
          finishBrowserSession();
        }
        return;
      }
      finishBrowserSession({ showNoSpeech: userStopRef.current });
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
  }, [finishBrowserSession, releaseMic]);

  const start = useCallback(async () => {
    if (preferServerStt()) {
      await startServerRecording();
    } else {
      await startBrowserRecording();
    }
  }, [startBrowserRecording, startServerRecording]);

  const stop = useCallback(() => {
    if (preferServerStt()) {
      stopServerRecording();
    } else {
      stopBrowserRecording();
    }
  }, [stopBrowserRecording, stopServerRecording]);

  const toggle = useCallback(() => {
    if (state === "recording") {
      stop();
    } else if (state === "idle") {
      void start();
    }
  }, [state, start, stop]);

  return { state, error, toggle, stop };
}
