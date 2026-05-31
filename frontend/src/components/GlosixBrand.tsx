import { Link } from "react-router-dom";

type Props = {
  className?: string;
  asLink?: boolean;
  tier?: "pro" | "free";
};

/** Текстовый логотип без иконки */
export function GlosixBrand({ className = "", asLink = true, tier }: Props) {
  const text = (
    <span className={`glosix-wordmark${className ? ` ${className}` : ""}`}>
      Glosix
      {tier && (
        <span className={`glosix-wordmark-tier glosix-wordmark-tier--${tier}`}>
          {" "}
          {tier === "pro" ? "PRO" : "FREE"}
        </span>
      )}
    </span>
  );
  if (asLink) {
    return (
      <Link to="/" className="glosix-brand" aria-label="Glosix">
        {text}
      </Link>
    );
  }
  return text;
}
