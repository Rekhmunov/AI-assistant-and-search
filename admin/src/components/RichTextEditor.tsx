import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

type EditorMode = "visual" | "html";

export type RichTextEditorHandle = {
  markCaret: () => boolean;
  insertHtmlAtCaret: (html: string) => boolean;
};

type Props = {
  value: string;
  onChange: (html: string) => void;
  disabled?: boolean;
  allowHtmlSource?: boolean;
};

const CARET_ATTR = "data-glosix-caret";

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

type ImgProps = { alt: string; title: string; align: "left" | "center" | "right" | "none" };

function applyImgStyle(img: HTMLImageElement, align: ImgProps["align"]) {
  img.style.maxWidth = "100%";
  img.style.height = "auto";
  img.style.borderRadius = "8px";
  if (align === "left") {
    img.style.float = "left";
    img.style.display = "";
    img.style.marginRight = "16px";
    img.style.marginLeft = "0";
    img.style.marginTop = "4px";
    img.style.marginBottom = "8px";
  } else if (align === "right") {
    img.style.float = "right";
    img.style.display = "";
    img.style.marginLeft = "16px";
    img.style.marginRight = "0";
    img.style.marginTop = "4px";
    img.style.marginBottom = "8px";
  } else {
    img.style.float = "none";
    img.style.display = "block";
    img.style.marginLeft = "auto";
    img.style.marginRight = "auto";
    img.style.marginTop = "8px";
    img.style.marginBottom = "8px";
  }
}

function detectImgAlign(img: HTMLImageElement): ImgProps["align"] {
  const f = img.style.float;
  if (f === "left") return "left";
  if (f === "right") return "right";
  if (img.style.marginLeft === "auto" && img.style.marginRight === "auto") return "center";
  return "none";
}

export const RichTextEditor = forwardRef<RichTextEditorHandle, Props>(function RichTextEditor(
  { value, onChange, disabled = false, allowHtmlSource = false },
  ref,
) {
  const editorRef = useRef<HTMLDivElement>(null);
  const htmlSourceRef = useRef<HTMLTextAreaElement>(null);
  const emojiWrapRef = useRef<HTMLDivElement>(null);
  const lastValue = useRef(value);
  const htmlCaretRef = useRef<number | null>(null);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [mode, setMode] = useState<EditorMode>("visual");

  // Image toolbar state
  const [selectedImg, setSelectedImg] = useState<HTMLImageElement | null>(null);
  const [imgProps, setImgProps] = useState<ImgProps>({ alt: "", title: "", align: "none" });
  const [imgPanelTop, setImgPanelTop] = useState(0);
  const imgPanelRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = editorRef.current;
    if (!el) return;
    const html = value || "<p></p>";
    const inSync = mode === "visual" && value === lastValue.current && el.innerHTML === html;
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

  const clearCaretMarkers = useCallback(() => {
    editorRef.current?.querySelectorAll(`[${CARET_ATTR}]`).forEach((node) => node.remove());
  }, []);

  const markCaret = useCallback((): boolean => {
    if (disabled) return false;
    if (mode === "html") {
      const ta = htmlSourceRef.current;
      if (!ta) return false;
      htmlCaretRef.current = ta.selectionStart ?? ta.value.length;
      return true;
    }
    const root = editorRef.current;
    const sel = window.getSelection();
    if (!root || !sel || sel.rangeCount === 0) return false;
    const range = sel.getRangeAt(0);
    if (!root.contains(range.commonAncestorContainer)) return false;
    clearCaretMarkers();
    const marker = document.createElement("span");
    marker.setAttribute(CARET_ATTR, "1");
    marker.style.display = "none";
    range.collapse(true);
    range.insertNode(marker);
    emitChange();
    return true;
  }, [clearCaretMarkers, disabled, emitChange, mode]);

  const insertHtmlAtCaret = useCallback(
    (html: string): boolean => {
      if (disabled) return false;
      if (mode === "html") {
        const ta = htmlSourceRef.current;
        if (!ta) return false;
        const pos = htmlCaretRef.current ?? ta.value.length;
        const next = `${ta.value.slice(0, pos)}${html}${ta.value.slice(pos)}`;
        htmlCaretRef.current = pos + html.length;
        onChange(next.trim() || "<p></p>");
        return true;
      }
      const root = editorRef.current;
      if (!root) return false;
      const marker = root.querySelector(`[${CARET_ATTR}]`);
      if (!marker || !marker.parentNode) {
        onChange((value || "<p></p>") + html);
        return false;
      }
      const wrapper = document.createElement("div");
      wrapper.innerHTML = html;
      const parent = marker.parentNode;
      while (wrapper.firstChild) {
        parent.insertBefore(wrapper.firstChild, marker);
      }
      marker.remove();
      emitChange();
      return true;
    },
    [disabled, emitChange, mode, onChange, value],
  );

  useImperativeHandle(ref, () => ({ markCaret, insertHtmlAtCaret }), [insertHtmlAtCaret, markCaret]);

  // ── Image click handling ────────────────────────────────────────────────
  const openImgPanel = useCallback((img: HTMLImageElement) => {
    setSelectedImg(img);
    setImgProps({
      alt: img.alt || "",
      title: img.title || "",
      align: detectImgAlign(img),
    });
    const editorRect = editorRef.current?.getBoundingClientRect();
    const imgRect = img.getBoundingClientRect();
    if (editorRect) {
      setImgPanelTop(imgRect.bottom - editorRect.top + 6);
    }
  }, []);

  const closeImgPanel = useCallback(() => {
    setSelectedImg(null);
  }, []);

  const applyImgProps = useCallback(() => {
    if (!selectedImg) return;
    selectedImg.alt = imgProps.alt;
    selectedImg.title = imgProps.title;
    applyImgStyle(selectedImg, imgProps.align);
    emitChange();
  }, [selectedImg, imgProps, emitChange]);

  const copyImg = useCallback(() => {
    if (!selectedImg) return;
    const clone = selectedImg.cloneNode(true) as HTMLImageElement;
    const p = document.createElement("p");
    p.appendChild(clone);
    const block = selectedImg.closest("p, div, figure, h1, h2, h3") as HTMLElement;
    if (block && block.parentNode) {
      block.parentNode.insertBefore(p, block.nextSibling);
    } else if (selectedImg.parentNode) {
      selectedImg.parentNode.appendChild(p);
    }
    emitChange();
  }, [selectedImg, emitChange]);

  const moveImg = useCallback((dir: "up" | "down") => {
    if (!selectedImg) return;
    const block = selectedImg.closest("p, div, figure, h1, h2, h3") as HTMLElement;
    if (!block || !block.parentNode) return;
    if (dir === "up" && block.previousElementSibling) {
      block.parentNode.insertBefore(block, block.previousElementSibling);
    } else if (dir === "down" && block.nextElementSibling) {
      block.parentNode.insertBefore(block.nextElementSibling, block);
    }
    emitChange();
  }, [selectedImg, emitChange]);

  const deleteImg = useCallback(() => {
    if (!selectedImg) return;
    const block = selectedImg.closest("p, div, figure") as HTMLElement;
    if (block && block.children.length === 1) {
      block.remove();
    } else {
      selectedImg.remove();
    }
    closeImgPanel();
    emitChange();
  }, [selectedImg, closeImgPanel, emitChange]);

  const onEditorClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.tagName === "IMG") {
      openImgPanel(target as HTMLImageElement);
    } else if (!imgPanelRef.current?.contains(target)) {
      closeImgPanel();
    }
  }, [openImgPanel, closeImgPanel]);

  // Close image panel when clicking outside editor
  useEffect(() => {
    if (!selectedImg) return;
    const onDoc = (e: MouseEvent) => {
      if (
        editorRef.current?.contains(e.target as Node) ||
        imgPanelRef.current?.contains(e.target as Node)
      ) return;
      closeImgPanel();
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [selectedImg, closeImgPanel]);

  // ── Toolbar commands ───────────────────────────────────────────────────
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
          <button type="button" role="tab" aria-selected={mode === "visual"}
            className={`rte-mode-tab${mode === "visual" ? " rte-mode-tab--active" : ""}`}
            disabled={disabled} onClick={() => switchMode("visual")}>
            Визуально
          </button>
          <button type="button" role="tab" aria-selected={mode === "html"}
            className={`rte-mode-tab${mode === "html" ? " rte-mode-tab--active" : ""}`}
            disabled={disabled} onClick={() => switchMode("html")}>
            HTML
          </button>
        </div>
      )}

      <div className={`rte-visual-pane${mode !== "visual" ? " rte-visual-pane--hidden" : ""}`}>
        <div className="rte-toolbar" role="toolbar" aria-label="Форматирование">
          {/* Форматирование текста */}
          <button type="button" className="rte-btn" onClick={() => exec("bold")} title="Жирный"><b>B</b></button>
          <button type="button" className="rte-btn" onClick={() => exec("italic")} title="Курсив"><i>I</i></button>
          <button type="button" className="rte-btn" onClick={() => exec("underline")} title="Подчёркивание"><u>U</u></button>
          <button type="button" className="rte-btn" onClick={insertLink} title="Ссылка">🔗</button>

          <span className="rte-sep" aria-hidden />

          {/* Выравнивание текста */}
          <button type="button" className="rte-btn" onClick={() => exec("justifyLeft")} title="По левому краю">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="0" y="1" width="14" height="2"/><rect x="0" y="5" width="10" height="2"/><rect x="0" y="9" width="14" height="2"/><rect x="0" y="13" width="8" height="2"/></svg>
          </button>
          <button type="button" className="rte-btn" onClick={() => exec("justifyCenter")} title="По центру">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="0" y="1" width="14" height="2"/><rect x="2" y="5" width="10" height="2"/><rect x="0" y="9" width="14" height="2"/><rect x="3" y="13" width="8" height="2"/></svg>
          </button>
          <button type="button" className="rte-btn" onClick={() => exec("justifyRight")} title="По правому краю">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="0" y="1" width="14" height="2"/><rect x="4" y="5" width="10" height="2"/><rect x="0" y="9" width="14" height="2"/><rect x="6" y="13" width="8" height="2"/></svg>
          </button>
          <button type="button" className="rte-btn" onClick={() => exec("justifyFull")} title="По ширине">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="0" y="1" width="14" height="2"/><rect x="0" y="5" width="14" height="2"/><rect x="0" y="9" width="14" height="2"/><rect x="0" y="13" width="14" height="2"/></svg>
          </button>

          <span className="rte-sep" aria-hidden />

          {/* Заголовки и списки */}
          <button type="button" className="rte-btn" onClick={() => exec("formatBlock", "h2")} title="Заголовок H2">H2</button>
          <button type="button" className="rte-btn" onClick={() => exec("formatBlock", "h3")} title="Заголовок H3">H3</button>
          <button type="button" className="rte-btn" onClick={() => exec("insertUnorderedList")} title="Список">•</button>
          <button type="button" className="rte-btn" onClick={() => exec("insertOrderedList")} title="Нумерация">1.</button>

          <span className="rte-sep" aria-hidden />

          {/* Размер и смайлы */}
          <label className="rte-size-label">
            Размер
            <select className="rte-size-select" defaultValue="3" disabled={disabled}
              onChange={(e) => setFontSize(e.target.value)}>
              {FONT_SIZES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </label>

          <div className="rte-emoji-wrap" ref={emojiWrapRef}>
            <button type="button" className="rte-btn" title="Смайл" disabled={disabled}
              onClick={() => setEmojiOpen((open) => !open)}>
              😀
            </button>
            {emojiOpen && (
              <div className="rte-emoji-panel" role="listbox" aria-label="Смайлы">
                {EMOJIS.map((emoji) => (
                  <button key={emoji} type="button" className="rte-emoji-btn"
                    onClick={() => insertEmoji(emoji)}>
                    {emoji}
                  </button>
                ))}
              </div>
            )}
          </div>

          <span className="rte-sep" aria-hidden />
          <button type="button" className="rte-btn" onClick={() => exec("removeFormat")} title="Сбросить формат">⌫</button>
        </div>

        {/* Область редактирования */}
        <div style={{ position: "relative" }}>
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
            onClick={onEditorClick}
          />

          {/* Панель свойств картинки */}
          {selectedImg && (
            <div
              ref={imgPanelRef}
              className="rte-img-panel"
              style={{ top: imgPanelTop }}
              onMouseDown={(e) => e.stopPropagation()}
            >
              <div className="rte-img-panel-header">
                <span className="rte-img-panel-title">Свойства изображения</span>
                <button type="button" className="rte-img-panel-close" onClick={closeImgPanel} title="Закрыть">✕</button>
              </div>

              <div className="rte-img-panel-fields">
                <label className="rte-img-field">
                  <span>Alt-текст</span>
                  <input
                    value={imgProps.alt}
                    onChange={(e) => setImgProps((p) => ({ ...p, alt: e.target.value }))}
                    placeholder="Описание изображения для SEO"
                  />
                </label>
                <label className="rte-img-field">
                  <span>Подпись (title)</span>
                  <input
                    value={imgProps.title}
                    onChange={(e) => setImgProps((p) => ({ ...p, title: e.target.value }))}
                    placeholder="Текст при наведении"
                  />
                </label>
              </div>

              <div className="rte-img-panel-row">
                <span className="rte-img-panel-label">Выравнивание:</span>
                <div className="rte-img-align-btns">
                  {(["left", "center", "right", "none"] as const).map((a) => (
                    <button
                      key={a}
                      type="button"
                      className={`rte-btn rte-img-align-btn${imgProps.align === a ? " rte-img-align-btn--active" : ""}`}
                      onClick={() => setImgProps((p) => ({ ...p, align: a }))}
                      title={{ left: "Слева", center: "По центру", right: "Справа", none: "Без обтекания" }[a]}
                    >
                      {{ left: "◧", center: "▣", right: "◨", none: "▢" }[a]}
                    </button>
                  ))}
                </div>
              </div>

              <div className="rte-img-panel-actions">
                <button type="button" className="rte-btn rte-img-action-btn" onClick={() => moveImg("up")} title="Переместить выше">↑ Вверх</button>
                <button type="button" className="rte-btn rte-img-action-btn" onClick={() => moveImg("down")} title="Переместить ниже">↓ Вниз</button>
                <button type="button" className="rte-btn rte-img-action-btn" onClick={copyImg} title="Скопировать">⎘ Копия</button>
                <button type="button" className="btn-primary rte-img-apply-btn" onClick={applyImgProps}>Применить</button>
                <button type="button" className="btn-secondary btn-danger-outline rte-img-action-btn" onClick={deleteImg}>Удалить</button>
              </div>
            </div>
          )}
        </div>
      </div>

      {allowHtmlSource && (
        <textarea
          ref={htmlSourceRef}
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
          onPaste={(e) => { e.stopPropagation(); }}
        />
      )}
    </div>
  );
});
