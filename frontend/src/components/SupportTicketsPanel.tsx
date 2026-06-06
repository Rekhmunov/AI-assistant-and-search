import { useEffect, useMemo, useState } from "react";
import {
  markSupportTicketRead,
  replyToSupportTicket,
  type SupportTicketUser,
} from "../api/client";
import { sortSupportTickets } from "../lib/supportTicketsSort";
import { t } from "../i18n";

const PAGE_SIZE = 5;

const SOURCE_LABELS: Record<string, string> = {
  pro_payment: "Оплата Pro",
  general: "Общее",
};

const STATUS_LABELS: Record<string, string> = {
  open: "Ожидает ответа",
  in_progress: "В работе",
  closed: "Закрыт",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU");
}

function ticketPreview(ticket: SupportTicketUser): string {
  const last = ticket.replies[ticket.replies.length - 1];
  const text = last?.message ?? ticket.message;
  return text.length > 120 ? `${text.slice(0, 120)}…` : text;
}

type Props = {
  token: string;
  tickets: SupportTicketUser[];
  onTicketsChange: () => void;
};

export function SupportTicketsPanel({ token, tickets, onTicketsChange }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);

  const sortedTickets = useMemo(() => sortSupportTickets(tickets), [tickets]);
  const totalPages = Math.max(1, Math.ceil(sortedTickets.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageTickets = sortedTickets.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  useEffect(() => {
    if (page > totalPages - 1) setPage(Math.max(0, totalPages - 1));
  }, [page, totalPages]);

  const openTicket = async (ticketId: string) => {
    if (expandedId === ticketId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(ticketId);
    const ticket = tickets.find((item) => item.id === ticketId);
    if (!ticket?.has_unread_reply) return;
    try {
      await markSupportTicketRead(token, ticketId);
      onTicketsChange();
    } catch {
      /* badge clears on next refetch */
    }
  };

  const sendReply = async (ticketId: string) => {
    const text = (replyDrafts[ticketId] ?? "").trim();
    if (!text) return;
    setBusyId(ticketId);
    setError("");
    try {
      await replyToSupportTicket(token, ticketId, text);
      setReplyDrafts((prev) => ({ ...prev, [ticketId]: "" }));
      onTicketsChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("supportReplyError"));
    } finally {
      setBusyId(null);
    }
  };

  if (!tickets.length) {
    return <p className="profile-support-empty">{t("profileSupportEmpty")}</p>;
  }

  return (
    <div className="profile-support-tickets">
      {error && <p className="profile-support-error">{error}</p>}
      <ul className="profile-support-ticket-list">
        {pageTickets.map((ticket) => {
          const expanded = expandedId === ticket.id;
          return (
            <li
              key={ticket.id}
              className={`profile-support-ticket${ticket.has_unread_reply ? " profile-support-ticket--unread" : ""}${
                expanded ? " profile-support-ticket--expanded" : ""
              }`}
            >
              <button
                type="button"
                className="profile-support-ticket-toggle"
                onClick={() => void openTicket(ticket.id)}
                aria-expanded={expanded}
              >
                <span className="profile-support-ticket-title-row">
                  {ticket.has_unread_reply && (
                    <span className="profile-support-unread-dot" aria-hidden />
                  )}
                  <span className="profile-support-ticket-title">
                    {SOURCE_LABELS[ticket.source] ?? ticket.source}
                  </span>
                  <span className={`profile-support-ticket-status profile-support-ticket-status--${ticket.status}`}>
                    {STATUS_LABELS[ticket.status] ?? ticket.status}
                  </span>
                </span>
                <span className="profile-support-ticket-preview">{ticketPreview(ticket)}</span>
                <span className="profile-support-ticket-date">{formatDate(ticket.created_at)}</span>
              </button>

              {expanded && (
                <div className="profile-support-thread">
                  <div className="profile-support-thread-message profile-support-thread-message--user">
                    <p className="profile-support-thread-meta">
                      {t("profileSupportYou")} · {formatDate(ticket.created_at)}
                    </p>
                    <p className="profile-support-thread-text">{ticket.message}</p>
                  </div>
                  {ticket.replies.map((reply) => (
                    <div
                      key={reply.id}
                      className={`profile-support-thread-message${
                        reply.author_type === "admin"
                          ? " profile-support-thread-message--admin"
                          : " profile-support-thread-message--user"
                      }`}
                    >
                      <p className="profile-support-thread-meta">
                        {reply.author_type === "admin"
                          ? t("profileSupportTeam")
                          : t("profileSupportYou")}
                        {reply.author_type === "admin" && reply.admin_email
                          ? ` · ${reply.admin_email}`
                          : ""}
                        {" · "}
                        {formatDate(reply.created_at)}
                      </p>
                      <p className="profile-support-thread-text">{reply.message}</p>
                    </div>
                  ))}

                  {ticket.can_reply && (
                    <div className="profile-support-reply-form">
                      <textarea
                        className="profile-support-reply-input"
                        rows={3}
                        placeholder={t("profileSupportReplyPlaceholder")}
                        value={replyDrafts[ticket.id] ?? ""}
                        onChange={(e) =>
                          setReplyDrafts((prev) => ({ ...prev, [ticket.id]: e.target.value }))
                        }
                        disabled={busyId === ticket.id}
                      />
                      <button
                        type="button"
                        className="btn-primary profile-support-reply-btn"
                        disabled={busyId === ticket.id}
                        onClick={() => void sendReply(ticket.id)}
                      >
                        {busyId === ticket.id ? "…" : t("profileSupportSendReply")}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {sortedTickets.length > PAGE_SIZE && (
        <nav className="profile-support-pager" aria-label={t("profileSupportPagerLabel")}>
          <button
            type="button"
            className="profile-support-pager-btn"
            disabled={safePage <= 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            {t("profileSupportPagerPrev")}
          </button>
          <span className="profile-support-pager-info">
            {t("profileSupportPagerPage", { current: safePage + 1, total: totalPages })}
          </span>
          <button
            type="button"
            className="profile-support-pager-btn"
            disabled={safePage >= totalPages - 1}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          >
            {t("profileSupportPagerNext")}
          </button>
        </nav>
      )}
    </div>
  );
}
