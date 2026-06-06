import type { SupportTicketUser } from "../api/client";

function isActiveTicket(ticket: SupportTicketUser): boolean {
  return ticket.status !== "closed";
}

/** Открытые сверху (новые первыми), затем закрытые (новые первыми). */
export function sortSupportTickets(tickets: SupportTicketUser[]): SupportTicketUser[] {
  const byDateDesc = (a: SupportTicketUser, b: SupportTicketUser) =>
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime();

  const active = tickets.filter(isActiveTicket).sort(byDateDesc);
  const closed = tickets.filter((t) => !isActiveTicket(t)).sort(byDateDesc);
  return [...active, ...closed];
}
