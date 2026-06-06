import { ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";

type Props = {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  onClose: () => void;
};

export function AdminModal({ title, children, actions, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="admin-modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="admin-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="admin-modal-title">{title}</h2>
        <div className="admin-modal-body">{children}</div>
        {actions && <div className="admin-modal-actions">{actions}</div>}
      </div>
    </div>,
    document.body,
  );
}
