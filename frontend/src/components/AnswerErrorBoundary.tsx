import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode; fallbackText?: string };
type State = { error: Error | null };

/** Не даём всему треду упасть в белый экран (старый WebView в MAX). */
export class AnswerErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Answer render failed", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <p className="composer-error" role="alert">
          {this.props.fallbackText ??
            "Не удалось показать ответ. Обновите миниапп или откройте тред на сайте."}
        </p>
      );
    }
    return this.props.children;
  }
}
