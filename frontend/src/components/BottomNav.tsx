import { NavLink } from "react-router-dom";
import { t } from "../i18n";

export function BottomNav() {
  return (
    <nav className="bottom-nav">
      <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
        <span>🔍</span>
        {t("navSearch")}
      </NavLink>
      <NavLink to="/history" className={({ isActive }) => (isActive ? "active" : "")}>
        <span>📚</span>
        {t("navHistory")}
      </NavLink>
      <NavLink to="/profile" className={({ isActive }) => (isActive ? "active" : "")}>
        <span>👤</span>
        {t("navProfile")}
      </NavLink>
    </nav>
  );
}
