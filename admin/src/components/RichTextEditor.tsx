import { useCallback, useEffect, useRef, useState } from "react";

type Props = {
  value: string;
  onChange: (html: string) => void;
  disabled?: boolean;
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

export function RichTextEditor({ value, onChange, disabled = false }: Props) {
  const editorRef = useRef<HTMLDivElement>(null);
  const emojiWrapRef = useRef<HTMLDivElement>(null);
  const lastValue = useRef(value);
  const [emojiOpen, setEmojiOpen] = useState(false);

  useEffect(() => {
    const el = editorRef.current;
    if (!el) return;
    if (value !== lastValue.current && el.innerHTML !== value) {
      el.innerHTML = value || "<p></p>";
      lastValue.current = value;
    }
  }, [value]);

  const emitChange = useCallback(() => {
    const el = editorRef.current;
    if (!el) return;
    const html = el.innerHTML.trim() || "<p></p>";
    lastValue.current = html;
    onChange(html);
  }, [onChange]);

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
    <div className={`rte${disabled ? " rte--disabled" : ""}`}>
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
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        onInput={emitChange}
        onBlur={emitChange}
      />
    </div>
  );
}
