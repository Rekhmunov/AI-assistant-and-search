import { useState } from "react";
import {
  markSupportTicketRead,
  replyToSupportTicket,
  type SupportTicketUser,
} from "../api/client";
import { t } from "../i18n";

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

  const unreadCount = tickets.filter((ticket) => ticket.has_unread_reply).length;

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

  if (!tickets.length) return null;

  return (
    <div className="profile-support-tickets">
      <div className="profile-support-tickets-head">
        <h3 className="profile-support-replies-title">{t("profileSupportMyTickets")}</h3>
        {unreadCount > 0 && (
          <span className="profile-support-unread-badge" aria-label={t("profileSupportUnreadCount", { n: unreadCount })}>
            {unreadCount}
          </span>
        )}
      </div>
      {error && <p className="profile-support-error">{error}</p>}
      <ul className="profile-support-ticket-list">
        {tickets.map((ticket) => {
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
                    <p className="profile-support-thread-meta">{t("profileSupportYou")} · {formatDate(ticket.created_at)}</p>
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
    </div>
  );
}
