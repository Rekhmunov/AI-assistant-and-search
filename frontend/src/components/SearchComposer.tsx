import { FormEvent, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { uploadFile, type UploadedFile, fetchMe } from "../api/client";
import { ACCEPT_FILE_INPUT, MAX_FILE_BYTES_FREE, MAX_FILE_BYTES_PRO, validateFile } from "../constants/files";
import { useTypingPlaceholder } from "../hooks/useTypingPlaceholder";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { t } from "../i18n";
import { isMaxWebApp } from "../lib/maxApp";
import { useAuthStore } from "../store/authStore";

export interface ComposerAttachment {
  id: string;
  filename: string;
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (payload: { query: string; attachmentIds: string[] }) => void;
  disabled?: boolean;
  placeholder?: string;
  attachments: ComposerAttachment[];
  onAttachmentsChange: (a: ComposerAttachment[]) => void;
  /** false — в потоке страницы (главная без ввода); true — закреплено над нижним меню */
  docked?: boolean;
  /** Циклический «печатающийся» placeholder на главной */
  animatedPlaceholder?: boolean;
  placeholderPhrases?: string[];
}

export function SearchComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder,
  attachments,
  onAttachmentsChange,
  docked = true,
  animatedPlaceholder = false,
  placeholderPhrases = [],
}: Props) {
  const token = useAuthStore((s) => s.token);
  const inMax = isMaxWebApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => fetchMe(token!),
    enabled: !!token,
  });
  const maxBytes = me?.plan === "pro" ? MAX_FILE_BYTES_PRO : MAX_FILE_BYTES_FREE;

  const voice = useVoiceInput((text) => onChange(value ? `${value} ${text}` : text));

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = value.trim();
    if (!q && attachments.length === 0) return;
    if (disabled || uploading) return;
    onSubmit({
      query: q || t("analyzeFile"),
      attachmentIds: attachments.map((a) => a.id),
    });
    onAttachmentsChange([]);
  };

  const onAttachClick = () => {
    if (!token) {
      setUploadError(t("loginForFiles"));
      return;
    }
    fileRef.current?.click();
  };

  const onFilePick = async (files: FileList | null) => {
    if (!files?.length || !token) return;
    const file = files[0];
    const err = validateFile(file, maxBytes);
    if (err) {
      setUploadError(err);
      return;
    }
    setUploadError(null);
    setUploading(true);
    try {
      const uploaded: UploadedFile = await uploadFile(token, file);
      onAttachmentsChange([...attachments, { id: uploaded.id, filename: uploaded.filename }]);
    } catch {
      setUploadError("Не удалось загрузить файл");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const canSend = (value.trim().length > 0 || attachments.length > 0) && !disabled && !uploading;
  const hasAttachment = attachments.length > 0;
  const showAnimatedPlaceholder = animatedPlaceholder && !value.trim() && !disabled;
  const typingPlaceholder = useTypingPlaceholder(showAnimatedPlaceholder, placeholderPhrases);
  const staticPlaceholder = placeholder ?? t("searchPlaceholder");

  return (
    <div className={`composer-wrap${docked ? " composer-wrap--docked" : " composer-wrap--inline"}`}>
      {(uploadError || voice.error) && <p className="composer-error">{uploadError || voice.error}</p>}
      {!token && !inMax && (
        <p className="composer-hint">
          {t("guestSearchHint")}{" "}
          <Link to="/login">{t("signIn")}</Link> — {t("guestSearchHintMore")}
        </p>
      )}
      <form
        className={`search-composer${hasAttachment ? " search-composer--with-attachment" : ""}`}
        onSubmit={handleSubmit}
      >
        {hasAttachment && (
          <div className="composer-attachments">
            {attachments.map((a) => (
              <div key={a.id} className="composer-attachment">
                <FileDocIcon />
                <span className="composer-attachment-name" title={a.filename}>
                  {a.filename}
                </span>
                <button
                  type="button"
                  className="composer-attachment-remove"
                  aria-label="Удалить файл"
                  onClick={() => onAttachmentsChange(attachments.filter((x) => x.id !== a.id))}
                >
                  <CloseIcon />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="composer-row">
          <button
            type="button"
            className="composer-icon"
            aria-label={t("attachFile")}
            disabled={disabled || uploading || attachments.length >= 1}
            onClick={onAttachClick}
          >
            <PlusIcon />
          </button>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT_FILE_INPUT}
            hidden
            onChange={(e) => onFilePick(e.target.files)}
          />
          <div className="composer-input-wrap">
            {showAnimatedPlaceholder && typingPlaceholder && (
              <span className="composer-placeholder-typing" aria-hidden>
                {typingPlaceholder}
                <span className="composer-placeholder-caret" />
              </span>
            )}
            <textarea
              className="composer-input"
              rows={hasAttachment ? 2 : 1}
              value={value}
              placeholder={showAnimatedPlaceholder ? " " : staticPlaceholder}
              disabled={disabled}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (canSend) handleSubmit(e as unknown as FormEvent);
                }
              }}
            />
          </div>
          <button
            type="button"
            className={`composer-icon ${voice.state === "recording" ? "recording" : ""}`}
            aria-label={t("voiceInput")}
            disabled={disabled}
            onClick={voice.toggle}
          >
            <MicIcon />
          </button>
          <button type="submit" className="composer-send" disabled={!canSend} aria-label={t("send")}>
            <SendIcon />
          </button>
        </div>
      </form>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 5v14M5 12h14"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 14a3 3 0 003-3V6a3 3 0 00-6 0v5a3 3 0 003 3z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M19 11v1a7 7 0 01-14 0v-1M12 18v3M8 21h8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 19V5M5 12l7-7 7 7"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function FileDocIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden className="composer-attachment-icon">
      <path
        d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M14 2v6h6M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M18 6L6 18M6 6l12 12"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
