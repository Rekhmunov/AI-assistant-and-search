import { useCallback, useRef } from "react";
import { apiUpload } from "../api";
import { RichTextEditor } from "./RichTextEditor";

const API = import.meta.env.VITE_API_URL || "";

type Props = {
  value: string;
  onChange: (html: string) => void;
  disabled?: boolean;
};

export function BlogRichTextEditor({ value, onChange, disabled }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);

  const insertImage = useCallback(
    async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const media = await apiUpload<{ url: string; alt_text: string }>(
        "/api/admin/blog/media?purpose=inline",
        form,
      );
      const src = media.url.startsWith("http") ? media.url : `${API}${media.url}`;
      const imgHtml = `<p><img src="${src}" alt="${media.alt_text || ""}" loading="lazy" style="max-width:100%;height:auto;border-radius:8px;" /></p>`;
      const next = (value || "<p></p>").replace(/<\/p>\s*$/, "") + imgHtml;
      onChange(next.endsWith("</p>") ? next : `${next}<p></p>`);
    },
    [value, onChange],
  );

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
        <RichTextEditor value={value} onChange={onChange} disabled={disabled} allowHtmlSource />
      </div>
    </div>
  );
}
