import { useState } from "react";
import { voteBlogHelpful } from "../api/blog";

type Props = { slug: string; helpfulYes: number; helpfulNo: number };

export function BlogHelpfulWidget({ slug, helpfulYes, helpfulNo }: Props) {
  const [voted, setVoted] = useState<"yes" | "no" | null>(null);
  const [yes, setYes] = useState(helpfulYes);
  const [no, setNo] = useState(helpfulNo);

  const vote = async (v: "yes" | "no") => {
    if (voted) return;
    setVoted(v);
    if (v === "yes") setYes((n) => n + 1);
    else setNo((n) => n + 1);
    await voteBlogHelpful(slug, v).catch(() => {});
  };

  const total = yes + no;

  return (
    <div className="blog-helpful" aria-label="Была ли статья полезна?">
      <p className="blog-helpful__question">Была ли статья полезна?</p>
      {voted ? (
        <div className="blog-helpful__thanks">
          Спасибо за обратную связь! {total > 0 && (
            <span className="blog-helpful__stats">
              {Math.round((yes / total) * 100)}% читателей считают её полезной
            </span>
          )}
        </div>
      ) : (
        <div className="blog-helpful__buttons">
          <button
            type="button"
            className="blog-helpful__btn blog-helpful__btn--yes"
            onClick={() => vote("yes")}
            aria-label="Да, статья полезна"
          >
            👍 Да
          </button>
          <button
            type="button"
            className="blog-helpful__btn blog-helpful__btn--no"
            onClick={() => vote("no")}
            aria-label="Нет, статья не полезна"
          >
            👎 Нет
          </button>
        </div>
      )}
    </div>
  );
}
