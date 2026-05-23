import { FormEvent } from "react";
import { t } from "../i18n";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  placeholder?: string;
}

export function SearchBar({ value, onChange, onSubmit, placeholder }: Props) {
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) onSubmit();
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        className="search-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? t("searchPlaceholder")}
      />
    </form>
  );
}
