import { forwardRef, useCallback, useImperativeHandle, useRef } from "react";
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
      // Всегда формируем абсолютный URL, чтобы bleach на бэкенде не удалил src
      // из-за отсутствия схемы у относительного пути /api/blog/media/...
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

  // mousedown fires BEFORE the editor loses focus, so the selection is still valid.
  // We insert the caret marker here so insertHtmlAtCaret knows where to place the image.
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
