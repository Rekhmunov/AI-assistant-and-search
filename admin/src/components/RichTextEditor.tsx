import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

type EditorMode = "visual" | "html";

type Props = {
  value: string;
  onChange: (html: string) => void;
  disabled?: boolean;
  /** Режим редактирования исходного HTML (для юридических документов). */
  allowHtmlSource?: boolean;
};

const FONT_SIZES = [
  { label: "Мелкий", value: "2" },
  { label: "Обычный", value: "3" },
  { label: "Крупный", value: "4" },
  { label: "Заголовок", value: "5" },
];

const EMOJIS = [
  "😀", "😊", "👋", "🎉", "✅", "❤️", "🔥", "⭐", "💡", "📱",
  "🚀", "✨", "👍", "🙏", "💬", "📎", "🔗", "😉", "🤝", "📣",
];

export function RichTextEditor({
  value,
  onChange,
  disabled = false,
  allowHtmlSource = false,
}: Props) {
  const editorRef = useRef<HTMLDivElement>(null);
  const emojiWrapRef = useRef<HTMLDivElement>(null);
  const lastValue = useRef(value);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [mode, setMode] = useState<EditorMode>("visual");

  /** Визуальный редактор всегда в DOM; синхронизируем с value, кроме активного набора в visual. */
  useLayoutEffect(() => {
    const el = editorRef.current;
    if (!el) return;
    const html = value || "<p></p>";
    const inSync =
      mode === "visual" && value === lastValue.current && el.innerHTML === html;
    if (inSync) return;
    if (el.innerHTML !== html) {
      el.innerHTML = html;
    }
    lastValue.current = html;
  }, [value, mode]);

  const emitChange = useCallback(() => {
    const el = editorRef.current;
    if (!el) return;
    const html = el.innerHTML.trim() || "<p></p>";
    lastValue.current = html;
    onChange(html);
  }, [onChange]);

  const switchMode = (next: EditorMode) => {
    if (disabled || next === mode) return;
    if (next === "html") {
      const el = editorRef.current;
      const html = (el?.innerHTML.trim() || value || "<p></p>").trim() || "<p></p>";
      lastValue.current = html;
      onChange(html);
      setMode("html");
      return;
    }
    const el = editorRef.current;
    if (el) {
      el.innerHTML = value || "<p></p>";
      lastValue.current = value || "<p></p>";
    }
    setMode("visual");
  };

  const onHtmlSourceChange = (raw: string) => {
    const html = raw.trim() || "<p></p>";
    lastValue.current = html;
    onChange(html);
  };

  const exec = (command: string, arg?: string) => {
    if (disabled) return;
    editorRef.current?.focus();
    document.execCommand(command, false, arg);
    emitChange();
  };

  const insertLink = () => {
    if (disabled) return;
    const url = window.prompt("URL ссылки", "https://");
    if (!url) return;
    exec("createLink", url.trim());
  };

  const setFontSize = (size: string) => {
    if (disabled) return;
    editorRef.current?.focus();
    document.execCommand("fontSize", false, size);
    emitChange();
  };

  const insertEmoji = (emoji: string) => {
    if (disabled) return;
    editorRef.current?.focus();
    document.execCommand("insertText", false, emoji);
    emitChange();
    setEmojiOpen(false);
  };

  useEffect(() => {
    if (!emojiOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (emojiWrapRef.current?.contains(e.target as Node)) return;
      setEmojiOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [emojiOpen]);

  return (
    <div className={`rte${disabled ? " rte--disabled" : ""}${mode === "html" ? " rte--html" : ""}`}>
      {allowHtmlSource && (
        <div className="rte-mode-tabs" role="tablist" aria-label="Режим редактора">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "visual"}
            className={`rte-mode-tab${mode === "visual" ? " rte-mode-tab--active" : ""}`}
            disabled={disabled}
            onClick={() => switchMode("visual")}
          >
            Визуально
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "html"}
            className={`rte-mode-tab${mode === "html" ? " rte-mode-tab--active" : ""}`}
            disabled={disabled}
            onClick={() => switchMode("html")}
          >
            HTML
          </button>
        </div>
      )}
      <div
        className={`rte-visual-pane${mode !== "visual" ? " rte-visual-pane--hidden" : ""}`}
      >
      <div className="rte-toolbar" role="toolbar" aria-label="Форматирование">
        <button type="button" className="rte-btn" onClick={() => exec("bold")} title="Жирный">
          <b>B</b>
        </button>
        <button type="button" className="rte-btn" onClick={() => exec("italic")} title="Курсив">
          <i>I</i>
        </button>
        <button type="button" className="rte-btn" onClick={() => exec("underline")} title="Подчёркивание">
          <u>U</u>
        </button>
        <button type="button" className="rte-btn" onClick={insertLink} title="Ссылка">
          🔗
        </button>
        <div className="rte-emoji-wrap" ref={emojiWrapRef}>
          <button
            type="button"
            className="rte-btn"
            title="Смайл"
            disabled={disabled}
            onClick={() => setEmojiOpen((open) => !open)}
          >
            😀
          </button>
          {emojiOpen && (
            <div className="rte-emoji-panel" role="listbox" aria-label="Смайлы">
              {EMOJIS.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  className="rte-emoji-btn"
                  onClick={() => insertEmoji(emoji)}
                >
                  {emoji}
                </button>
              ))}
            </div>
          )}
        </div>
        <span className="rte-sep" aria-hidden />
        <button type="button" className="rte-btn" onClick={() => exec("formatBlock", "h2")} title="Заголовок">
          H
        </button>
        <button type="button" className="rte-btn" onClick={() => exec("insertUnorderedList")} title="Список">
          •
        </button>
        <button type="button" className="rte-btn" onClick={() => exec("insertOrderedList")} title="Нумерация">
          1.
        </button>
        <span className="rte-sep" aria-hidden />
        <label className="rte-size-label">
          Размер
          <select
            className="rte-size-select"
            defaultValue="3"
            disabled={disabled}
            onChange={(e) => setFontSize(e.target.value)}
          >
            {FONT_SIZES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <span className="rte-sep" aria-hidden />
        <button type="button" className="rte-btn" onClick={() => exec("removeFormat")} title="Сбросить формат">
          ⌫
        </button>
      </div>
        <div
          ref={editorRef}
          className="rte-editor"
          contentEditable={!disabled && mode === "visual"}
          suppressContentEditableWarning
          role="textbox"
          aria-multiline="true"
          aria-hidden={mode !== "visual"}
          onInput={emitChange}
          onBlur={emitChange}
        />
      </div>
      {allowHtmlSource && (
        <textarea
          className={`rte-html-source${mode !== "html" ? " rte-html-source--hidden" : ""}`}
          hidden={mode !== "html"}
          value={value === "<p></p>" ? "" : value}
          placeholder="<h2>Заголовок</h2>&#10;<p>Текст…</p>"
          disabled={disabled}
          spellCheck={false}
          aria-hidden={mode !== "html"}
          tabIndex={mode === "html" ? 0 : -1}
          aria-label="HTML-код документа"
          onChange={(e) => onHtmlSourceChange(e.target.value)}
          onPaste={(e) => {
            e.stopPropagation();
          }}
        />
      )}
    </div>
  );
}
