import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { logoutSession } from "../api/client";
import { isMaxWebApp } from "../lib/maxApp";
import { useAuthStore } from "../store/authStore";

/** End the server session and reset client auth/cache state. */
export function useSignOut() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const clear = useAuthStore((s) => s.clear);

  return useCallback(async () => {
    try {
      await logoutSession();
    } catch {
      /* still clear local state */
    }
    clear();
    queryClient.clear();
    navigate(isMaxWebApp() ? "/" : "/login");
  }, [clear, navigate, queryClient]);
}
