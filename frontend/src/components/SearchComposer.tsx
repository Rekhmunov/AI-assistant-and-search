import { FormEvent, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { FileUploadError, uploadFile, fetchMe } from "../api/client";
import { ComposerAttachMenu } from "./ComposerAttachMenu";
import {
  ACCEPT_DOCUMENT_INPUT,
  ACCEPT_IMAGE_INPUT,
  MAX_ATTACHMENTS,
  MAX_FILE_BYTES_FREE,
  MAX_FILE_BYTES_PRO,
  fileKind,
  type FileKind,
  validateFile,
} from "../constants/files";
import { useTypingPlaceholder } from "../hooks/useTypingPlaceholder";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { t } from "../i18n";
import { prepareFileForUpload } from "../lib/compressImage";
import { useAuthStore } from "../store/authStore";

export type AttachmentKind = "document" | "image";

export interface ComposerAttachment {
  id: string;
  filename: string;
  kind: AttachmentKind;
  previewUrl?: string;
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (payload: { query: string; attachmentIds: string[] }) => void;
  /** Первое сообщение в треде: нельзя отправить только вложение без текста */
  requireTextWithAttachments?: boolean;
  disabled?: boolean;
  placeholder?: string;
  attachments: ComposerAttachment[];
  onAttachmentsChange: Dispatch<SetStateAction<ComposerAttachment[]>>;
  docked?: boolean;
  animatedPlaceholder?: boolean;
  placeholderPhrases?: string[];
}

type UploadingItem = {
  localKey: string;
  filename: string;
  kind: AttachmentKind;
  previewUrl?: string;
};

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
  requireTextWithAttachments = false,
}: Props) {
  const token = useAuthStore((s) => s.token);
  const documentRef = useRef<HTMLInputElement>(null);
  const photoRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuggestPro, setUploadSuggestPro] = useState(false);
  const [uploading, setUploading] = useState<UploadingItem[]>([]);
  const [inputFocused, setInputFocused] = useState(false);

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => fetchMe(token!),
    enabled: !!token,
  });
  const plan = me?.plan === "pro" ? "pro" : "free";
  const maxBytes = plan === "pro" ? MAX_FILE_BYTES_PRO : MAX_FILE_BYTES_FREE;

  const setUploadFailure = (message: string, suggestPro = false) => {
    setUploadError(message);
    setUploadSuggestPro(suggestPro);
  };

  const clearUploadFailure = () => {
    setUploadError(null);
    setUploadSuggestPro(false);
  };

  const voice = useVoiceInput((text) => onChange(value ? `${value} ${text}` : text));

  const totalCount = attachments.length + uploading.length;
  const isBusy = uploading.length > 0;
  const atLimit = totalCount >= MAX_ATTACHMENTS;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = value.trim();
    if (!q && attachments.length === 0) return;
    if (!q && attachments.length > 0 && requireTextWithAttachments) {
      setUploadFailure(t("attachmentTextRequired"));
      return;
    }
    if (disabled || isBusy) return;
    onSubmit({
      query: q || t("analyzeFile"),
      attachmentIds: attachments.map((a) => a.id),
    });
    for (const a of attachments) {
      if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
    }
    onAttachmentsChange([]);
  };

  const openPicker = (ref: React.RefObject<HTMLInputElement | null>) => {
    if (!token) {
      setUploadFailure(t("loginForFiles"));
      return;
    }
    if (atLimit) {
      setUploadFailure(t("attachLimit", { n: MAX_ATTACHMENTS }));
      return;
    }
    clearUploadFailure();
    ref.current?.click();
  };

  const removeAttachment = (id: string) => {
    const removed = attachments.find((a) => a.id === id);
    if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
    onAttachmentsChange(attachments.filter((x) => x.id !== id));
  };

  const onFilesPicked = async (files: FileList | null, expected?: FileKind) => {
    if (!files?.length || !token) return;

    let slots = MAX_ATTACHMENTS - attachments.length - uploading.length;
    if (slots <= 0) {
      setUploadFailure(t("attachLimit", { n: MAX_ATTACHMENTS }));
      return;
    }

    const batch = Array.from(files).slice(0, slots);
    if (files.length > batch.length) {
      setUploadFailure(t("attachLimit", { n: MAX_ATTACHMENTS }));
    }

    for (const raw of batch) {
      const file = await prepareFileForUpload(raw);
      const err = validateFile(file, maxBytes, plan, expected);
      if (err) {
        setUploadFailure(err.message, err.suggestPro);
        continue;
      }

      const kind = expected ?? fileKind(file) ?? "document";
      const localKey = `up-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const previewUrl = kind === "image" ? URL.createObjectURL(file) : undefined;
      const pending: UploadingItem = { localKey, filename: file.name, kind, previewUrl };
      setUploading((prev) => [...prev, pending]);

      try {
        const uploaded = await uploadFile(token, file);
        onAttachmentsChange((prev) => [
          ...prev,
          {
            id: uploaded.id,
            filename: uploaded.filename,
            kind,
            previewUrl,
          },
        ]);
      } catch (e) {
        if (e instanceof FileUploadError) {
          setUploadFailure(e.message, e.suggestPro);
        } else {
          setUploadFailure(t("attachUploadFailed"));
        }
        if (previewUrl) URL.revokeObjectURL(previewUrl);
      } finally {
        setUploading((prev) => prev.filter((u) => u.localKey !== localKey));
      }
    }
  };

  const resetInput = (ref: React.RefObject<HTMLInputElement | null>) => {
    if (ref.current) ref.current.value = "";
  };

  const canSend =
    (value.trim().length > 0 || (attachments.length > 0 && !requireTextWithAttachments)) &&
    !disabled &&
    !isBusy;
  const hasAttachment = totalCount > 0;
  const showTypingOverlay =
    animatedPlaceholder && !value.trim() && !disabled && !inputFocused;
  const typingPlaceholder = useTypingPlaceholder(showTypingOverlay, placeholderPhrases);
  const staticPlaceholder = placeholder ?? t("searchPlaceholder");
  const textareaPlaceholder = inputFocused
    ? ""
    : showTypingOverlay
      ? " "
      : staticPlaceholder;

  return (
    <div className={`composer-wrap${docked ? " composer-wrap--docked" : " composer-wrap--inline"}`}>
      {(uploadError || voice.error) && (
        <div className="composer-error-wrap">
          <p className="composer-error">{uploadError || voice.error}</p>
          {uploadSuggestPro && uploadError && (
            <Link to="/profile" className="composer-error-upgrade">
              {t("upgradePro")}
            </Link>
          )}
        </div>
      )}
      <form
        className={`search-composer${hasAttachment ? " search-composer--with-attachment" : ""}`}
        onSubmit={handleSubmit}
      >
        {hasAttachment && (
          <div className="composer-attachments">
            {attachments.map((a) => (
              <AttachmentChip
                key={a.id}
                filename={a.filename}
                kind={a.kind}
                previewUrl={a.previewUrl}
                onRemove={() => removeAttachment(a.id)}
              />
            ))}
            {uploading.map((u) => (
              <AttachmentChip
                key={u.localKey}
                filename={u.filename}
                kind={u.kind}
                previewUrl={u.previewUrl}
                processing
              />
            ))}
          </div>
        )}

        <div className="composer-row">
          <ComposerAttachMenu
            disabled={disabled || isBusy || atLimit}
            onPickDocument={() => openPicker(documentRef)}
            onPickPhoto={() => openPicker(photoRef)}
            onTakePhoto={() => openPicker(cameraRef)}
          />
          <input
            ref={documentRef}
            type="file"
            accept={ACCEPT_DOCUMENT_INPUT}
            multiple
            hidden
            onChange={(e) => {
              void onFilesPicked(e.target.files, "document");
              resetInput(documentRef);
            }}
          />
          <input
            ref={photoRef}
            type="file"
            accept={ACCEPT_IMAGE_INPUT}
            multiple
            hidden
            onChange={(e) => {
              void onFilesPicked(e.target.files, "image");
              resetInput(photoRef);
            }}
          />
          <input
            ref={cameraRef}
            type="file"
            accept={ACCEPT_IMAGE_INPUT}
            capture="environment"
            hidden
            onChange={(e) => {
              void onFilesPicked(e.target.files, "image");
              resetInput(cameraRef);
            }}
          />
          <div className="composer-input-wrap">
            {showTypingOverlay && typingPlaceholder && (
              <span className="composer-placeholder-typing" aria-hidden>
                {typingPlaceholder}
                <span className="composer-placeholder-caret" />
              </span>
            )}
            <textarea
              className="composer-input"
              rows={hasAttachment ? 2 : 1}
              value={value}
              placeholder={textareaPlaceholder}
              disabled={disabled}
              onFocus={() => setInputFocused(true)}
              onBlur={() => setInputFocused(false)}
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

function AttachmentChip({
  filename,
  kind,
  previewUrl,
  processing,
  onRemove,
}: {
  filename: string;
  kind: AttachmentKind;
  previewUrl?: string;
  processing?: boolean;
  onRemove?: () => void;
}) {
  return (
    <div
      className={`composer-attachment${processing ? " composer-attachment--processing" : ""}`}
    >
      {kind === "image" && previewUrl ? (
        <img src={previewUrl} alt="" className="composer-attachment-thumb" />
      ) : (
        <FileDocIcon />
      )}
      <span className="composer-attachment-name" title={filename}>
        {processing ? t("attachProcessing") : filename}
      </span>
      {onRemove && (
        <button
          type="button"
          className="composer-attachment-remove"
          aria-label={t("attachRemove")}
          onClick={onRemove}
        >
          <CloseIcon />
        </button>
      )}
    </div>
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
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M18 6L6 18M6 6l12 12"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
