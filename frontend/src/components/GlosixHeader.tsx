import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchMe } from "../api/client";
import { useAuthStore } from "../store/authStore";

interface Props {
  showLimits?: boolean;
}

export function GlosixHeader({ showLimits = true }: Props) {
  const token = useAuthStore((s) => s.token);
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => fetchMe(token!),
    enabled: !!token && showLimits,
  });

  return (
    <header className="glosix-header">
      <Link to="/" className="glosix-brand" aria-label="Glosix">
        <img src="/glosix-logo.svg" alt="Glosix" className="glosix-logo" />
      </Link>
      {showLimits && me && (
        <Link to="/profile" className="limits-badge">
          {me.searches_today}/{me.searches_limit}
        </Link>
      )}
    </header>
  );
}
