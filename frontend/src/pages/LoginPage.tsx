import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Button, ErrorNote, Input } from "../components/ui";
import { useAuth } from "../state";

export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form
        className="w-full max-w-sm space-y-4 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100"
        onSubmit={async (event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          setPending(true);
          setError("");
          try {
            const token = await api<{ access_token: string }>("/api/v1/auth/login", {
              method: "POST",
              body: JSON.stringify({ email: data.get("email"), password: data.get("password") }),
            });
            signIn(token.access_token);
            navigate("/");
          } catch (err) {
            setError(err instanceof Error ? err.message : "Login failed");
          } finally {
            setPending(false);
          }
        }}
      >
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-cyan-400">ObservePro</p>
          <h1 className="mt-1 text-xl font-semibold">Sign in</h1>
        </div>
        <Input name="email" type="email" required aria-label="Email" placeholder="admin@localhost" className="border-zinc-700 bg-black text-zinc-100" />
        <Input name="password" type="password" required aria-label="Password" placeholder="Password" className="border-zinc-700 bg-black text-zinc-100" />
        {error && <ErrorNote message={error} />}
        <Button type="submit" disabled={pending} className="w-full">{pending ? "Signing in…" : "Sign in"}</Button>
      </form>
    </div>
  );
}
