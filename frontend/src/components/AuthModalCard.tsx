import type { ReactNode } from "react";
import { GlosixBrand } from "./GlosixBrand";

type Props = {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  showBrand?: boolean;
  icon?: ReactNode;
  footer?: ReactNode;
};

/** Центрированная карточка авторизации в стиле модальных окон приложения. */
export function AuthModalCard({
  children,
  title,
  subtitle,
  showBrand = true,
  icon,
  footer,
}: Props) {
  return (
    <div className="auth-modal">
      {showBrand && (
        <div className="auth-modal-brand">
          <GlosixBrand asLink={false} />
        </div>
      )}
      {icon && <div className="auth-modal-icon">{icon}</div>}
      {title && <h1 className="auth-modal-title">{title}</h1>}
      {subtitle && <p className="auth-modal-hint">{subtitle}</p>}
      <div className="auth-modal-body">{children}</div>
      {footer && <div className="auth-modal-footer">{footer}</div>}
    </div>
  );
}

/** Обёртка страницы: центрирует модальный блок на экране (миниапп и ПК). */
export function AuthShell({ children }: { children: ReactNode }) {
  return <div className="auth-shell">{children}</div>;
}
