import { useState } from "react";

type Props = { title: string; url: string };

export function BlogShareButtons({ title, url }: Props) {
  const [copied, setCopied] = useState(false);

  const shareUrl = encodeURIComponent(url);
  const shareTitle = encodeURIComponent(title);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const ta = document.createElement("textarea");
      ta.value = url;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="blog-share">
      <span className="blog-share__label">Поделиться</span>
      <div className="blog-share__buttons">
        <a
          href={`https://t.me/share/url?url=${shareUrl}&text=${shareTitle}`}
          target="_blank"
          rel="noopener noreferrer"
          className="blog-share__btn blog-share__btn--telegram"
          aria-label="Поделиться в Telegram"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.869 4.326-2.96-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.829.941z"/>
          </svg>
          Telegram
        </a>

        <a
          href={`https://vk.com/share.php?url=${shareUrl}&title=${shareTitle}`}
          target="_blank"
          rel="noopener noreferrer"
          className="blog-share__btn blog-share__btn--vk"
          aria-label="Поделиться ВКонтакте"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <path d="M12.785 16.241s.288-.032.436-.194c.136-.148.132-.427.132-.427s-.02-1.304.586-1.496c.598-.19 1.365 1.26 2.178 1.817.615.422 1.082.33 1.082.33l2.175-.03s1.138-.07.598-1.03c-.044-.073-.314-.66-1.613-1.866-1.36-1.26-1.177-1.057.46-3.239.998-1.329 1.397-2.142 1.272-2.49-.12-.333-.854-.245-.854-.245l-2.448.015s-.181-.025-.315.056c-.132.08-.216.267-.216.267s-.387 1.03-.903 1.906c-1.088 1.85-1.524 1.948-1.702 1.833-.413-.267-.31-1.075-.31-1.648 0-1.793.272-2.54-.528-2.733-.266-.064-.46-.107-1.137-.114-.869-.009-1.603.002-2.019.206-.277.135-.49.437-.36.454.16.021.523.098.716.36.248.34.24 1.1.24 1.1s.142 2.11-.333 2.372c-.326.179-.773-.187-1.733-1.86-.491-.849-.863-1.788-.863-1.788s-.071-.173-.2-.267c-.154-.113-.37-.148-.37-.148l-2.325.015s-.35.01-.478.162c-.115.136-.009.417-.009.417s1.82 4.26 3.876 6.406c1.888 1.974 4.03 1.845 4.03 1.845h.972z"/>
          </svg>
          ВКонтакте
        </a>

        <button
          type="button"
          className={`blog-share__btn blog-share__btn--copy${copied ? " blog-share__btn--copied" : ""}`}
          onClick={handleCopy}
          aria-label="Скопировать ссылку"
        >
          {copied ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
            </svg>
          )}
          {copied ? "Скопировано!" : "Ссылка"}
        </button>
      </div>
    </div>
  );
}
