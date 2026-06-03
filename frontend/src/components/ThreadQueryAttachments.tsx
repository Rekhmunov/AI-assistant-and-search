import { useState } from "react";
import type { MessageAttachment } from "../api/client";
import { useAttachmentImageSrc } from "../hooks/useAttachmentImageSrc";
import { ImageLightboxOverlay } from "./ImageLightboxOverlay";
import { ThreadQueryAttachmentImage } from "./ThreadQueryAttachmentImage";
import { t } from "../i18n";

type Props = {
  attachments: MessageAttachment[];
};

function AttachmentLightboxImage({
  attachment,
  onClose,
}: {
  attachment: MessageAttachment;
  onClose: () => void;
}) {
  const src = useAttachmentImageSrc(attachment.id, attachment.url, attachment.previewUrl);
  if (!src) return null;
  return (
    <ImageLightboxOverlay url={src} title={attachment.filename} onClose={onClose} />
  );
}

export function ThreadQueryAttachments({ attachments }: Props) {
  const [lightboxAttachment, setLightboxAttachment] = useState<MessageAttachment | null>(null);

  if (!attachments.length) return null;

  return (
    <>
      <div className="thread-query-attachments" aria-label="Вложения">
        {attachments.map((a) => {
          if (a.kind === "image") {
            return (
              <ThreadQueryAttachmentImage
                key={a.id}
                attachment={a}
                onOpen={() => setLightboxAttachment(a)}
                openLabel={`${t("openAttachmentImage")}: ${a.filename}`}
              />
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

      {lightboxAttachment && (
        <AttachmentLightboxImage
          attachment={lightboxAttachment}
          onClose={() => setLightboxAttachment(null)}
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
