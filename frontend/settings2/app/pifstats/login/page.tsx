"use client";

import { FormEvent, useState } from "react";
import { Lock, Loader2 } from "lucide-react";

import { ApiError, PifStatsAuthApi } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function PifStatsLoginPage() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      await PifStatsAuthApi.login(username, password);
      window.location.href = "/pifstats";
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to log in");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-6 py-10">
      <section className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-900 text-white">
            <Lock className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-lg font-semibold text-slate-950">PIFStats Login</h1>
            <p className="text-sm text-slate-500">Restricted admin access</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Username</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-slate-900"
              autoComplete="username"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-slate-900"
              autoComplete="current-password"
            />
          </label>

          {error && (
            <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </div>
          )}

          <Button type="submit" disabled={isSubmitting} className="w-full gap-2">
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Log in
          </Button>
        </form>
      </section>
    </main>
  );
}
