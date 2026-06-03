import type { MessageAttachment } from "../api/client";
import { useAttachmentImageSrc } from "../hooks/useAttachmentImageSrc";

type Props = {
  attachment: MessageAttachment;
  onOpen: () => void;
  openLabel: string;
};

export function ThreadQueryAttachmentImage({ attachment, onOpen, openLabel }: Props) {
  const src = useAttachmentImageSrc(attachment.id, attachment.url, attachment.previewUrl);

  return (
    <div className="thread-query-attachment thread-query-attachment--image">
      <button
        type="button"
        className="thread-query-attachment-open"
        onClick={onOpen}
        disabled={!src}
        aria-label={openLabel}
      >
        {src ? (
          <img src={src} alt="" className="thread-query-attachment-thumb" referrerPolicy="no-referrer" />
        ) : (
          <span className="thread-query-attachment-thumb thread-query-attachment-thumb--placeholder" aria-hidden />
        )}
      </button>
      <span className="thread-query-attachment-name" title={attachment.filename}>
        {attachment.filename}
      </span>
    </div>
  );
}
