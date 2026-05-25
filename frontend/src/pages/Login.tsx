import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginEmail } from "../api/client";
import { GlosixHeader } from "../components/GlosixHeader";
import { useAuthStore } from "../store/authStore";

export function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data = await loginEmail(email, password);
      setAuth(data.access_token, data.user);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка входа");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page page-login">
      <GlosixHeader showLimits={false} />
      <div className="login-card">
        <h1>Вход</h1>
        <button type="button" className="btn-link" style={{ marginBottom: 16 }} onClick={() => navigate("/")}>
          Продолжить без входа
        </button>
        <form onSubmit={onSubmit}>
          <label>
            Логин
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          {error && <p className="composer-error">{error}</p>}
          <button type="submit" className="btn-primary btn-block" disabled={busy}>
            {busy ? "…" : "Войти"}
          </button>
        </form>
      </div>
    </div>
  );
}
