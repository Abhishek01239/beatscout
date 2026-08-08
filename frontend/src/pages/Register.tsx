import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, setToken, storeEmail } from "../api";
import type { AuthResponse } from "../types";
import { Button, Card, Input, Label } from "../components/ui";
import { LogoIcon } from "../components/Logo";

export default function Register() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post<AuthResponse>("/auth/register", {
        name,
        email,
        password,
      });
      setToken(res.token.access_token);
      storeEmail(res.user.email);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <LogoIcon />
          <h1 className="text-2xl font-extrabold text-white">Create account</h1>
        </div>
        <Card>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
              />
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
              />
            </div>
            {error && (
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">
                {error}
              </p>
            )}
            <Button type="submit" loading={busy} className="w-full" size="lg">
              Sign up
            </Button>
            <p className="text-center text-xs text-slate-500">
              Already registered?{" "}
              <Link to="/login" className="text-accent-soft hover:underline">
                Sign in
              </Link>
            </p>
          </form>
        </Card>
      </div>
    </div>
  );
}