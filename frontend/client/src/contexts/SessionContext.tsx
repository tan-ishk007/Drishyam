/**
 * DRISHYAM local integration: a durable browser session with safe expiry recovery.
 * Refresh restores server-validated access; a server 401 clears only this browser session.
 */
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { currentUser, requestEmailOtp, resendSignUpVerification, signIn, signInWithGoogleCredential, signOut, signUp, type CurrentUser, verifyEmailOtp, verifySignUp } from "@/api/auth";
import { clearExpiredAccessSession, SESSION_EXPIRED_EVENT, SESSION_TOKEN_KEY, setInMemoryAccessToken } from "@/api/client";

type SessionContextValue = {
  user: CurrentUser | null;
  isRestoring: boolean;
  signInWithPassword: (payload: { email: string; password: string }) => Promise<CurrentUser>;
  register: (payload: { name: string; email: string; password: string }) => Promise<void>;
  verifyRegistration: (payload: { email: string; otp: string }) => Promise<CurrentUser>;
  resendRegistrationVerification: (payload: { email: string }) => Promise<void>;
  requestPasswordlessOtp: (payload: { email: string }) => Promise<void>;
  signInWithEmailOtp: (payload: { email: string; otp: string }) => Promise<CurrentUser>;
  signInWithGoogle: (credential: string) => Promise<CurrentUser>;
  signOutSession: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

async function establish(token: string, setUser: (user: CurrentUser) => void) {
  setInMemoryAccessToken(token);
  try {
    const user = await currentUser();
    window.localStorage.setItem(SESSION_TOKEN_KEY, token);
    window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
    setUser(user);
    return user;
  } catch (error) {
    clearExpiredAccessSession();
    throw error;
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);

  useEffect(() => {
    let active = true;
    const handleExpiredSession = () => {
      if (active) setUser(null);
    };
    const restore = async () => {
      // AUTH_REFRESH_PERSISTENCE_20260828: migrate the previous tab token once, then restore durably.
      const durableToken = window.localStorage.getItem(SESSION_TOKEN_KEY);
      const legacyToken = window.sessionStorage.getItem(SESSION_TOKEN_KEY);
      const token = durableToken || legacyToken;
      if (token && !durableToken) {
        window.localStorage.setItem(SESSION_TOKEN_KEY, token);
        window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
      }
      if (!token) {
        if (active) setIsRestoring(false);
        return;
      }
      setInMemoryAccessToken(token);
      try {
        const restoredUser = await currentUser();
        if (active) setUser(restoredUser);
      } catch {
        clearExpiredAccessSession();
      } finally {
        if (active) setIsRestoring(false);
      }
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpiredSession);
    void restore();
    return () => {
      active = false;
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpiredSession);
    };
  }, []);

  const value = useMemo<SessionContextValue>(() => ({
    user,
    isRestoring,
    async signInWithPassword(payload) {
      const token = await signIn(payload);
      return establish(token.access_token, setUser);
    },
    async register(payload) {
      await signUp(payload);
    },
    async verifyRegistration(payload) {
      const token = await verifySignUp(payload);
      return establish(token.access_token, setUser);
    },
    async resendRegistrationVerification(payload) {
      await resendSignUpVerification(payload);
    },
    async requestPasswordlessOtp(payload) {
      await requestEmailOtp(payload);
    },
    async signInWithEmailOtp(payload) {
      const token = await verifyEmailOtp(payload);
      return establish(token.access_token, setUser);
    },
    async signInWithGoogle(credential) {
      const token = await signInWithGoogleCredential(credential);
      return establish(token.access_token, setUser);
    },
    async signOutSession() {
      try {
        await signOut();
      } finally {
        clearExpiredAccessSession();
      }
    },
  }), [isRestoring, user]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
