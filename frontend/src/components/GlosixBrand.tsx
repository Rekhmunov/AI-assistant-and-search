import { Link } from "react-router-dom";

type Props = {
  className?: string;
  asLink?: boolean;
};

/** Текстовый логотип без иконки */
export function GlosixBrand({ className = "", asLink = true }: Props) {
  const text = <span className={`glosix-wordmark${className ? ` ${className}` : ""}`}>Glosix</span>;
  if (asLink) {
    return (
      <Link to="/" className="glosix-brand" aria-label="Glosix">
        {text}
      </Link>
    );
  }
  return text;
}
