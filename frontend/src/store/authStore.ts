import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserProfile } from "../api/client";
import { clearGuestSession } from "../lib/guestSession";

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  setAuth: (token: string, user: UserProfile) => void;
  setUser: (user: UserProfile) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => {
        clearGuestSession();
        set({ token, user });
      },
      setUser: (user) => set({ user }),
      clear: () => {
        clearGuestSession();
        set({ token: null, user: null });
      },
    }),
    { name: "glosix-auth" }
  )
);
