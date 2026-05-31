import type { MouseEvent, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { buildSourceViewPath } from "../lib/sourceView";

type Props = {
  href: string;
  className?: string;
  title?: string;
  children: ReactNode;
  id?: string;
};

/** External source link: in-app viewer on mobile, new tab on desktop. */
export function SourceLink({ href, className, title, children, id }: Props) {
  const navigate = useNavigate();
  const isDesktop = useDesktopLayout();

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (isDesktop) return;
    event.preventDefault();
    navigate(buildSourceViewPath(href));
  };

  return (
    <a
      id={id}
      href={href}
      className={className}
      title={title}
      target={isDesktop ? "_blank" : undefined}
      rel={isDesktop ? "noopener noreferrer" : undefined}
      onClick={handleClick}
    >
      {children}
    </a>
  );
}
