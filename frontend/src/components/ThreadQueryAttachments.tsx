import { useState } from "react";
import type { MessageAttachment } from "../api/client";
import { ImageLightboxOverlay } from "./ImageLightboxOverlay";
import { t } from "../i18n";

type Props = {
  attachments: MessageAttachment[];
};

type LightboxState = {
  url: string;
  title: string;
};

export function ThreadQueryAttachments({ attachments }: Props) {
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);

  if (!attachments.length) return null;

  const openImage = (attachment: MessageAttachment) => {
    const url = attachment.url || attachment.previewUrl;
    if (!url) return;
    setLightbox({ url, title: attachment.filename });
  };

  return (
    <>
      <div className="thread-query-attachments" aria-label="Вложения">
        {attachments.map((a) => {
          const imageUrl = a.kind === "image" ? a.url || a.previewUrl : null;

          if (imageUrl) {
            return (
              <div key={a.id} className="thread-query-attachment thread-query-attachment--image">
                <button
                  type="button"
                  className="thread-query-attachment-open"
                  onClick={() => openImage(a)}
                  aria-label={`${t("openAttachmentImage")}: ${a.filename}`}
                >
                  <img
                    src={imageUrl}
                    alt=""
                    className="thread-query-attachment-thumb"
                    referrerPolicy="no-referrer"
                  />
                </button>
                <span className="thread-query-attachment-name" title={a.filename}>
                  {a.filename}
                </span>
              </div>
            );
          }

          return (
            <div key={a.id} className="thread-query-attachment">
              <FileIcon />
              <span className="thread-query-attachment-name" title={a.filename}>
                {a.filename}
              </span>
            </div>
          );
        })}
      </div>

      {lightbox && (
        <ImageLightboxOverlay
          url={lightbox.url}
          title={lightbox.title}
          onClose={() => setLightbox(null)}
        />
      )}
    </>
  );
}

function FileIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden className="thread-query-attachment-icon">
      <path
        d="M14 2H8a2 2 0 00-2 2v16a2 2 0 002 2h8a2 2 0 002-2V8l-6-6z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}
