import { useCallback, useRef, useState } from "react";
import { transcribeVoice } from "../api/client";
import { t } from "../i18n";
import { getMaxPlatform, isIosLikeDevice, isMaxWebApp } from "../lib/maxApp";

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

function preferMp4Recording(): boolean {
  return getMaxPlatform() === "ios" || isIosLikeDevice();
}

/** В MAX WebView финальный chunk часто приходит после onstop — нужна пауза перед сборкой blob. */
function blobFinalizeDelayMs(): number {
  if (isMaxWebApp()) return 750;
  if (preferMp4Recording()) return 450;
  return 0;
}

/** В MAX — периодические chunk'и; иначе iOS без timeslice, Android 250 ms. */
function useRecorderTimesliceMs(): number | undefined {
  if (isMaxWebApp()) return 400;
  return preferMp4Recording() ? undefined : 250;
}

const MAX_STOP_FLUSH_MS = 120;

function recorderMimeCandidates(): string[] {
  return preferMp4Recording()
    ? [
        "audio/mp4",
        "audio/aac",
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
      ]
    : [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
        "audio/aac",
        "audio/ogg;codecs=opus",
      ];
}

function guessRecordingMime(blob: Blob, recorderMime: string): string {
  const fromBlob = (blob.type || "").split(";")[0].trim().toLowerCase();
  if (fromBlob && fromBlob !== "application/octet-stream") {
    return fromBlob;
  }
  const fromRec = (recorderMime || "").split(";")[0].trim().toLowerCase();
  if (fromRec) return fromRec;
  if (preferMp4Recording()) return "audio/mp4";
  return "audio/webm";
}

function createMediaRecorder(stream: MediaStream): { recorder: MediaRecorder; mimeType: string } {
  if (typeof MediaRecorder === "undefined") {
    throw new Error("recorder_unsupported");
  }
  const tried = new Set<string>();
  for (const candidate of recorderMimeCandidates()) {
    if (!MediaRecorder.isTypeSupported(candidate)) continue;
    tried.add(candidate);
    try {
      const recorder = new MediaRecorder(stream, { mimeType: candidate });
      return { recorder, mimeType: recorder.mimeType || candidate };
    } catch {
      /* next candidate */
    }
  }
  try {
    const recorder = new MediaRecorder(stream);
    return { recorder, mimeType: recorder.mimeType || "audio/webm" };
  } catch {
    throw new Error("recorder_unsupported");
  }
}

function mapVoiceStartError(err: unknown): string {
  if (!(err instanceof Error)) {
    return t("voiceStartFailed");
  }
  if (err.message === "recorder_unsupported") {
    return t("voiceUnavailableMax");
  }
  const name = err.name;
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return isMaxWebApp() ? t("voiceMicDeniedMax") : t("voiceMicDenied");
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return t("voiceMicNotFound");
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return t("voiceMicBusy");
  }
  if (import.meta.env.DEV) {
    console.warn("voice start failed:", name, err.message);
  }
  return t("voiceStartFailed");
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
export function useVoiceInput(onText: (text: string) => void, token: string | null = null) {
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
    async (blob: Blob, mimeHint?: string) => {
    setState("transcribing");
      try {
        const res = await transcribeVoice(token, blob, mimeHint);
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
      const failStop = () => {
        recordingRef.current = false;
        releaseMic();
        setState("idle");
      };
      const doStop = () => {
        try {
          rec.stop();
        } catch {
          failStop();
        }
      };
      try {
        if (rec.state === "recording" && typeof rec.requestData === "function") {
          rec.requestData();
        }
        if (isMaxWebApp()) {
          window.setTimeout(() => {
            try {
              if (rec.state === "recording" && typeof rec.requestData === "function") {
                rec.requestData();
              }
            } catch {
              /* ignore */
            }
            window.setTimeout(doStop, MAX_STOP_FLUSH_MS);
          }, MAX_STOP_FLUSH_MS);
        } else {
          doStop();
        }
      } catch {
        failStop();
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

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError(t("voiceUnavailableMax"));
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      releaseMic();
      streamRef.current = stream;

      const { recorder: rec, mimeType } = createMediaRecorder(stream);
      recorderRef.current = rec;
      recorderMimeRef.current = mimeType;

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
        const mime = recorderMimeRef.current;
        const stream = streamRef.current;
        const finalize = () => {
          const chunks = chunksRef.current;
          chunksRef.current = [];
          stream?.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
          recorderRef.current = null;

          if (!userStopRef.current) {
            recordingRef.current = false;
            setState("idle");
            return;
          }

          const resolvedMime = guessRecordingMime(new Blob(chunks, { type: mime }), mime);
          const blob = new Blob(chunks, { type: resolvedMime });
          const elapsed = Date.now() - startedAtRef.current;
          if (blob.size === 0 || elapsed < 200) {
            recordingRef.current = false;
            if (import.meta.env.DEV) {
              console.warn("voice: empty recording", {
                bytes: blob.size,
                elapsed,
                mime: resolvedMime,
                chunks: chunks.length,
              });
            }
            setError(t("voiceNoSpeech"));
            setState("idle");
            return;
          }
          void uploadRecording(blob, resolvedMime);
        };

        const delay = blobFinalizeDelayMs();
        if (delay > 0) {
          window.setTimeout(finalize, delay);
        } else {
          finalize();
        }
      };

      recordingRef.current = true;
      startedAtRef.current = Date.now();
      setState("recording");
      const timeslice = useRecorderTimesliceMs();
      if (timeslice != null) {
        rec.start(timeslice);
      } else {
        rec.start();
      }
      autoStopTimerRef.current = window.setTimeout(() => {
        if (recordingRef.current) stopServerRecording();
      }, MAX_RECORD_MS);
    } catch (err) {
      releaseMic();
      recordingRef.current = false;
      setState("idle");
      setError(mapVoiceStartError(err));
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
