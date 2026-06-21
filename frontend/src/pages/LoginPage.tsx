import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Wordmark } from "@/components/ui/Wordmark";
import { useAuth } from "@/contexts/AuthContext";

type LocationState = {
  from?: {
    pathname?: string;
  };
};

export function LoginPage() {
  const { loading, login, user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as LocationState | null)?.from?.pathname ?? "/app";

  if (!loading && user) {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to log in.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg px-4 py-10">
      <Card padding="lg" className="w-full max-w-md">
        <div className="mb-6">
          <Wordmark className="text-sm" />
          <h1 className="mt-2 text-2xl font-semibold text-text">Log in</h1>
          <p className="mt-2 text-sm text-text-muted">Use your account to open your library workspace.</p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block text-sm text-text-muted">
            Email
            <input
              className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2 text-text outline-none transition-colors focus:border-accent"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>

          <label className="block text-sm text-text-muted">
            Password
            <input
              className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2 text-text outline-none transition-colors focus:border-accent"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {error ? (
            <p className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger">
              {error}
            </p>
          ) : null}

          <Button className="w-full" variant="primary" type="submit" disabled={submitting}>
            {submitting ? "Logging in..." : "Log in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-text-muted">
          Need an account?{" "}
          <Link className="text-accent hover:text-accent-dim" to="/register">
            Register
          </Link>
        </p>
      </Card>
    </main>
  );
}
