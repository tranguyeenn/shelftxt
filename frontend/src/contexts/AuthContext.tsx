import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";
import type { Session, User } from "@supabase/supabase-js";

import { supabase } from "@/lib/supabase";

type RegisterInput = {
  email: string;
  password: string;
  username: string;
};

type AuthContextValue = {
  session: Session | null;
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<{ needsEmailConfirmation: boolean }>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

async function ensureProfile(user: User, username?: string): Promise<void> {
  const { data: existingProfile, error: lookupError } = await supabase
    .from("profiles")
    .select("id")
    .eq("id", user.id)
    .maybeSingle();

  if (lookupError) {
    throw lookupError;
  }

  if (existingProfile) {
    return;
  }

  const profileUsername =
    username ?? (typeof user.user_metadata?.username === "string" ? user.user_metadata.username : "");

  if (!profileUsername) {
    return;
  }

  const now = new Date().toISOString();
  const { error: profileError } = await supabase.from("profiles").insert({
    id: user.id,
    email: user.email ?? "",
    username: profileUsername,
    created_at: now,
    updated_at: now
  });

  if (profileError) {
    throw profileError;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function loadSession() {
      const {
        data: { session: currentSession }
      } = await supabase.auth.getSession();

      if (mounted) {
        setSession(currentSession);
        setLoading(false);
        if (currentSession?.user) {
          void ensureProfile(currentSession.user).catch(() => {
            /* Profile creation errors are surfaced during signup; avoid disrupting session restore. */
          });
        }
      }
    }

    void loadSession();

    const {
      data: { subscription }
    } = supabase.auth.onAuthStateChange((_event, currentSession) => {
      setSession(currentSession);
      setLoading(false);
      if (currentSession?.user) {
        void ensureProfile(currentSession.user).catch(() => {
          /* Profile creation errors are surfaced during signup; avoid disrupting session restore. */
        });
      }
    });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password
    });

    if (error) {
      throw error;
    }
  }, []);

  const register = useCallback(async ({ email, password, username }: RegisterInput) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          username
        }
      }
    });

    if (error) {
      throw error;
    }

    if (data.user && data.session) {
      await ensureProfile(data.user, username);
    }

    return { needsEmailConfirmation: Boolean(data.user && !data.session) };
  }, []);

  const logout = useCallback(async () => {
    const { error } = await supabase.auth.signOut();

    if (error) {
      throw error;
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      loading,
      login,
      register,
      logout
    }),
    [loading, login, logout, register, session]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }

  return context;
}
