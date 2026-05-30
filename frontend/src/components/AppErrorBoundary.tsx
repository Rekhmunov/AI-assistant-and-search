import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/** Ловит падение всего приложения — вместо белого экрана показываем текст ошибки. */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("App crashed", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app-boot-error" role="alert">
          <p>Не удалось загрузить Glosix.</p>
          <p style={{ fontSize: "0.85rem", marginTop: 8 }}>{this.state.error.message}</p>
          <button type="button" className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => location.reload()}>
            Обновить страницу
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
