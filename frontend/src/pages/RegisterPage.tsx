import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuth } from "@/contexts/AuthContext";

export function RegisterPage() {
  const { loading, register, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user && !submitting && !error) {
    return <Navigate to="/app" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setSubmitting(true);

    try {
      const result = await register({
        email,
        password,
        username
      });
      if (result.needsEmailConfirmation) {
        setMessage("Check your email to confirm your account, then log in.");
        return;
      }
      navigate("/app", { replace: true });
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to create account.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg px-4 py-10">
      <Card padding="lg" className="w-full max-w-md">
        <div className="mb-6">
          <p className="font-mono text-xs uppercase tracking-widest text-text-dim">ShelfTxt</p>
          <h1 className="mt-2 text-2xl font-semibold text-text">Create account</h1>
          <p className="mt-2 text-sm text-text-muted">Start a private ShelfTxt workspace with email login.</p>
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
            Username
            <input
              className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2 text-text outline-none transition-colors focus:border-accent"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>

          <label className="block text-sm text-text-muted">
            Password
            <input
              className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2 text-text outline-none transition-colors focus:border-accent"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={6}
              required
            />
          </label>

          {error ? (
            <p className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger">
              {error}
            </p>
          ) : null}

          {message ? (
            <p className="rounded-lg border border-accent/30 bg-accent-muted px-3 py-2 text-sm text-accent">
              {message}
            </p>
          ) : null}

          <Button className="w-full" variant="primary" type="submit" disabled={submitting}>
            {submitting ? "Creating account..." : "Create account"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-text-muted">
          Already have an account?{" "}
          <Link className="text-accent hover:text-accent-dim" to="/login">
            Log in
          </Link>
        </p>
      </Card>
    </main>
  );
}
