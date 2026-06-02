import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserProfile } from "../api/client";
import { clearGuestSession } from "../lib/guestSession";

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  setAuth: (token: string, user: UserProfile) => void;
  setUser: (user: UserProfile) => void;
  setToken: (token: string) => void;
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
      setToken: (token) => set({ token }),
      clear: () => {
        clearGuestSession();
        set({ token: null, user: null });
      },
    }),
    {
      name: "glosix-auth",
      partialize: (state) => ({ user: state.user }),
    }
  )
);
