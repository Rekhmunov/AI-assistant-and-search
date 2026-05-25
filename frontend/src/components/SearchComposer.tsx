import { FormEvent, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { uploadFile, type UploadedFile, fetchMe } from "../api/client";
import { ACCEPT_FILE_INPUT, MAX_FILE_BYTES_FREE, MAX_FILE_BYTES_PRO, validateFile } from "../constants/files";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { t } from "../i18n";
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
}

export function SearchComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder,
  attachments,
  onAttachmentsChange,
}: Props) {
  const token = useAuthStore((s) => s.token)!;
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => fetchMe(token),
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

  const onFilePick = async (files: FileList | null) => {
    if (!files?.length) return;
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

  return (
    <div className="composer-wrap">
      {attachments.length > 0 && (
        <div className="attachment-chips">
          {attachments.map((a) => (
            <span key={a.id} className="attachment-chip">
              📎 {a.filename}
              <button
                type="button"
                aria-label="Удалить"
                onClick={() => onAttachmentsChange(attachments.filter((x) => x.id !== a.id))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {(uploadError || voice.error) && <p className="composer-error">{uploadError || voice.error}</p>}
      <form className="search-composer" onSubmit={handleSubmit}>
        <button
          type="button"
          className="composer-icon"
          aria-label={t("attachFile")}
          disabled={disabled || uploading || attachments.length >= 1}
          onClick={() => fileRef.current?.click()}
        >
          📎
        </button>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT_FILE_INPUT}
          hidden
          onChange={(e) => onFilePick(e.target.files)}
        />
        <textarea
          className="composer-input"
          rows={1}
          value={value}
          placeholder={placeholder ?? t("searchPlaceholder")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend) handleSubmit(e as unknown as FormEvent);
            }
          }}
        />
        <button
          type="button"
          className={`composer-icon ${voice.state === "recording" ? "recording" : ""}`}
          aria-label={t("voiceInput")}
          disabled={disabled}
          onClick={voice.toggle}
        >
          🎤
        </button>
        <button type="submit" className="composer-send" disabled={!canSend} aria-label={t("send")}>
          →
        </button>
      </form>
    </div>
  );
}
