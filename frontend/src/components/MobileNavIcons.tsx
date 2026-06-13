import { History, User, ChevronLeft, Plus, Search, MessageSquare, List } from "lucide-react";

export function HistoryIcon() {
  return <History width={20} height={20} strokeWidth={2} aria-hidden />;
}

export function ProfileIcon() {
  return <User width={20} height={20} strokeWidth={1.8} aria-hidden />;
}

export function BackIcon() {
  return <ChevronLeft width={22} height={22} strokeWidth={2} aria-hidden />;
}

export function PlusIcon({ size = 22 }: { size?: number }) {
  return <Plus width={size} height={size} strokeWidth={1.75} aria-hidden />;
}

export function SearchIcon() {
  return <Search width={20} height={20} strokeWidth={2} aria-hidden />;
}

export function SupportWriteIcon() {
  return <MessageSquare width={20} height={20} strokeWidth={1.8} aria-hidden />;
}

export function SupportListIcon() {
  return <List width={20} height={20} strokeWidth={1.8} aria-hidden />;
}
