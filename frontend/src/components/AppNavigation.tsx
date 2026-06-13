import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Search, Clock, User, Bot } from "lucide-react";
import { GlosixBrand } from "./GlosixBrand";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

function NavItem({
  to,
  end,
  label,
  icon,
}: {
  to: string;
  end?: boolean;
  label: string;
  icon: ReactNode;
}) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
      <span className="app-nav-icon" aria-hidden>
        {icon}
      </span>
      <span className="app-nav-label">{label}</span>
    </NavLink>
  );
}

const NAV_ICON_SIZE = 22;

export function AppNavigation() {
  const aria = t("navMain");
  const userPlan = useAuthStore((s) => s.user?.plan);
  const brandTier = userPlan === "pro" ? "pro" : "free";

  return (
    <>
      <nav className="sidebar-nav" aria-label={aria}>
        <div className="sidebar-nav-brand">
          <GlosixBrand className="glosix-wordmark--sidebar" tier={brandTier} />
        </div>
        <div className="sidebar-nav-top">
          <NavItem to="/" end label={t("navSearch")} icon={<Search size={NAV_ICON_SIZE} strokeWidth={1.8} />} />
          <NavItem to="/agents" label={t("navAgents")} icon={<Bot size={NAV_ICON_SIZE} strokeWidth={1.8} />} />
          <NavItem to="/history" label={t("navHistory")} icon={<Clock size={NAV_ICON_SIZE} strokeWidth={1.8} />} />
        </div>
        <div className="sidebar-nav-bottom">
          <NavItem to="/profile" label={t("navProfile")} icon={<User size={NAV_ICON_SIZE} strokeWidth={1.8} />} />
        </div>
      </nav>

      <nav className="bottom-nav" aria-label={aria}>
        <NavItem to="/" end label={t("navSearch")} icon={<Search size={NAV_ICON_SIZE} strokeWidth={1.8} />} />
        <NavItem to="/agents" label={t("navAgents")} icon={<Bot size={NAV_ICON_SIZE} strokeWidth={1.8} />} />
        <NavItem to="/history" label={t("navHistory")} icon={<Clock size={NAV_ICON_SIZE} strokeWidth={1.8} />} />
        <NavItem to="/profile" label={t("navProfile")} icon={<User size={NAV_ICON_SIZE} strokeWidth={1.8} />} />
      </nav>
    </>
  );
}
