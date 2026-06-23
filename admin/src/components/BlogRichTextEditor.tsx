import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from "react";
import { apiUpload } from "../api";
import { RichTextEditor, type RichTextEditorHandle } from "./RichTextEditor";

const API = import.meta.env.VITE_API_URL || "";

export type BlogRichTextEditorHandle = RichTextEditorHandle & {
  insertImageHtml: (html: string) => boolean;
};

type Props = {
  value: string;
  onChange: (html: string) => void;
  disabled?: boolean;
};

export const BlogRichTextEditor = forwardRef<BlogRichTextEditorHandle, Props>(function BlogRichTextEditor(
  { value, onChange, disabled },
  ref,
) {
  const editorRef = useRef<RichTextEditorHandle>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Search block insertion state
  const [searchPopoverOpen, setSearchPopoverOpen] = useState(false);
  const [searchPlaceholder, setSearchPlaceholder] = useState("");

  const insertImageHtml = useCallback(
    (html: string) => editorRef.current?.insertHtmlAtCaret(html) ?? false,
    [],
  );

  useImperativeHandle(
    ref,
    () => ({
      markCaret: () => editorRef.current?.markCaret() ?? false,
      insertHtmlAtCaret: (html: string) => editorRef.current?.insertHtmlAtCaret(html) ?? false,
      insertImageHtml,
    }),
    [insertImageHtml],
  );

  const insertImage = useCallback(
    async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const media = await apiUpload<{ url: string; alt_text: string }>(
        "/api/admin/blog/media?purpose=inline",
        form,
      );
      const src = media.url.startsWith("http")
        ? media.url
        : `${API || window.location.origin}${media.url}`;
      const alt = (media.alt_text || "").replace(/"/g, "&quot;");
      const imgHtml = `<p><img src="${src}" alt="${alt}" loading="lazy" style="max-width:100%;height:auto;border-radius:8px;display:block;margin-left:auto;margin-right:auto;" /></p>`;
      if (!insertImageHtml(imgHtml)) {
        const next = (value || "<p></p>").replace(/<\/p>\s*$/, "") + imgHtml;
        onChange(next.endsWith("</p>") ? next : `${next}<p></p>`);
      }
    },
    [insertImageHtml, onChange, value],
  );

  const onImageButtonMouseDown = useCallback(() => {
    editorRef.current?.markCaret();
  }, []);

  const onPickImage = () => fileRef.current?.click();

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || disabled) return;
    try {
      await insertImage(file);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Не удалось загрузить изображение");
    }
  };

  // Open search popover — save caret first (mousedown fires before focus loss)
  const onSearchButtonMouseDown = useCallback(() => {
    editorRef.current?.markCaret();
  }, []);

  const onSearchButtonClick = () => {
    setSearchPlaceholder("");
    setSearchPopoverOpen(true);
  };

  const onInsertSearch = useCallback(() => {
    const ph = searchPlaceholder.trim() || "Спроси что угодно, на все найду точный ответ";
    const esc = ph.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const blockHtml = `<div class="glosix-search" data-q="${esc}"><p class="glosix-search-preview">🔍 Поиск Glosix: «${esc}»</p></div><p></p>`;
    const inserted = editorRef.current?.insertHtmlAtCaret(blockHtml) ?? false;
    if (!inserted) {
      const next = (value || "<p></p>").replace(/<\/p>\s*$/, "") + blockHtml;
      onChange(next.endsWith("</p>") ? next : `${next}<p></p>`);
    }
    setSearchPopoverOpen(false);
    setSearchPlaceholder("");
  }, [searchPlaceholder, value, onChange]);

  return (
    <div className="blog-rte-wrap">
      <div className="blog-rte-toolbar">
        <button
          type="button"
          className="rte-btn blog-rte-image-btn"
          disabled={disabled}
          onMouseDown={onImageButtonMouseDown}
          onClick={onPickImage}
          title="Вставить изображение"
        >
          Изображение
        </button>

        <div className="blog-rte-search-wrap">
          <button
            type="button"
            className="rte-btn blog-rte-search-btn"
            disabled={disabled}
            onMouseDown={onSearchButtonMouseDown}
            onClick={onSearchButtonClick}
            title="Вставить блок поиска Glosix"
          >
            🔍 Поиск Glosix
          </button>
          {searchPopoverOpen && (
            <div className="blog-search-popover">
              <label className="blog-search-popover-label">Подсказка внутри строки поиска:</label>
              <input
                className="blog-search-popover-input"
                type="text"
                autoFocus
                placeholder="Спроси что угодно, на все найду точный ответ"
                value={searchPlaceholder}
                onChange={(e) => setSearchPlaceholder(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") { e.preventDefault(); onInsertSearch(); }
                  if (e.key === "Escape") { setSearchPopoverOpen(false); }
                }}
                maxLength={200}
              />
              <div className="blog-search-popover-actions">
                <button type="button" className="btn-primary blog-search-popover-ok" onClick={onInsertSearch}>
                  Вставить
                </button>
                <button type="button" className="btn-secondary blog-search-popover-cancel" onClick={() => setSearchPopoverOpen(false)}>
                  Отмена
                </button>
              </div>
            </div>
          )}
        </div>

        <span className="hint blog-rte-hint">JPEG/PNG/WebP сжимаются в WebP при загрузке</span>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        hidden
        onChange={onFileChange}
      />
      <div className="blog-rte-editor-wrap">
        <RichTextEditor
          ref={editorRef}
          value={value}
          onChange={onChange}
          disabled={disabled}
          allowHtmlSource
        />
      </div>
    </div>
  );
});
