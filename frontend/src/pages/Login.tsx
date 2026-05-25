import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginEmail, registerEmail } from "../api/client";
import { GlosixHeader } from "../components/GlosixHeader";
import { useAuthStore } from "../store/authStore";

export function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data =
        mode === "login"
          ? await loginEmail(email, password)
          : await registerEmail(email, password, firstName || undefined);
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
        <h1>{mode === "login" ? "Вход" : "Регистрация"}</h1>
        <p className="hint">Один аккаунт для сайта app.glosix.ru и миниаппа в MAX</p>
        <button type="button" className="btn-link" style={{ marginBottom: 16 }} onClick={() => navigate("/")}>
          Продолжить без входа
        </button>
        <form onSubmit={onSubmit}>
          {mode === "register" && (
            <label>
              Имя
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)} autoComplete="given-name" />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
            />
          </label>
          <label>
            Пароль {mode === "register" && <span className="hint">(мин. 8 символов)</span>}
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === "register" ? 8 : 1}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {error && <p className="composer-error">{error}</p>}
          <button type="submit" className="btn-primary btn-block" disabled={busy}>
            {busy ? "…" : mode === "login" ? "Войти" : "Создать аккаунт"}
          </button>
        </form>
        <button
          type="button"
          className="btn-link"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError("");
          }}
        >
          {mode === "login" ? "Нет аккаунта? Зарегистрироваться" : "Уже есть аккаунт? Войти"}
        </button>
      </div>
    </div>
  );
}
