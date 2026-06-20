import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SEARCH_QUERY_MAX_LENGTH } from "../lib/searchQueryLimits";

export function BlogTrySearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    const params = new URLSearchParams({ q });
    navigate(`/thread?${params.toString()}`);
  };

  return (
    <section className="blog-try-search" aria-labelledby="blog-try-search-title">
      <h2 id="blog-try-search-title" className="blog-try-search-title">
        Попробуйте Glosix прямо сейчас
      </h2>
      <p className="blog-try-search-lead">
        Умный поиск с источниками и готовым ответом. Без регистрации.
      </p>
      <form className="blog-try-search-form" onSubmit={submit}>
        <label className="blog-try-search-field">
          <span className="visually-hidden">Ваш вопрос</span>
          <input
            type="search"
            name="q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Например: как настроить VPN на роутере"
            maxLength={SEARCH_QUERY_MAX_LENGTH}
            autoComplete="off"
            enterKeyHint="search"
          />
        </label>
        <button type="submit" className="blog-try-search-submit" disabled={!query.trim()}>
          Искать
        </button>
      </form>
    </section>
  );
}
