import type { MouseEvent, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { isMaxWebApp } from "../lib/maxApp";
import { buildSourceViewPath } from "../lib/sourceView";

type Props = {
  href: string;
  className?: string;
  title?: string;
  children: ReactNode;
  id?: string;
};

/** External link: in-app viewer in MAX / mobile, new tab on desktop web. */
export function SourceLink({ href, className, title, children, id }: Props) {
  const navigate = useNavigate();
  const isDesktop = useDesktopLayout();
  const openInNewTab = isDesktop && !isMaxWebApp();

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (openInNewTab) return;
    event.preventDefault();
    navigate(buildSourceViewPath(href));
  };

  return (
    <a
      id={id}
      href={href}
      className={className}
      title={title ?? href}
      target={openInNewTab ? "_blank" : undefined}
      rel={openInNewTab ? "noopener noreferrer" : undefined}
      onClick={handleClick}
    >
      {children}
    </a>
  );
}
