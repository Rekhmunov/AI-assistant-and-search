import { Link } from "react-router-dom";
import { isMaxWebApp } from "../lib/maxApp";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";
import { GlosixBrand } from "./GlosixBrand";

interface Props {
  /** Показать текстовый логотип Glosix слева */
  showBrand?: boolean;
}

export function GlosixHeader({ showBrand = true }: Props) {
  const token = useAuthStore((s) => s.token);
  const inMax = isMaxWebApp();

  return (
    <header className={`glosix-header${showBrand ? "" : " glosix-header--no-brand"}`}>
      {showBrand ? <GlosixBrand /> : <div className="glosix-header-spacer" aria-hidden />}
      <div className="glosix-header-actions">
        {!token && !inMax && (
          <Link to="/login" className="header-login-btn">
            {t("signIn")}
          </Link>
        )}
        {!token && inMax && (
          <Link to="/profile" className="header-login-btn">
            {t("navProfile")}
          </Link>
        )}
        {token && (
          <Link to="/profile" className="header-login-btn">
            {t("navProfile")}
          </Link>
        )}
      </div>
    </header>
  );
}
