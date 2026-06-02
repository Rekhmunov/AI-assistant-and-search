import type { MessageAttachment } from "../api/client";

type Props = {
  attachments: MessageAttachment[];
};

export function ThreadQueryAttachments({ attachments }: Props) {
  if (!attachments.length) return null;

  return (
    <div className="thread-query-attachments" aria-label="Вложения">
      {attachments.map((a) => (
        <div key={a.id} className="thread-query-attachment">
          {a.kind === "image" && (a.previewUrl || a.url) ? (
            <img
              src={a.previewUrl || a.url}
              alt=""
              className="thread-query-attachment-thumb"
              referrerPolicy="no-referrer"
            />
          ) : (
            <FileIcon />
          )}
          <span className="thread-query-attachment-name" title={a.filename}>
            {a.filename}
          </span>
        </div>
      ))}
    </div>
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
