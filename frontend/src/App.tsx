import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, getToken, ApiError } from "./api";
import type { User } from "./types";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Discovery from "./pages/Discovery";
import Tracks from "./pages/Tracks";
import Studio from "./pages/Studio";
import Youtube from "./pages/Youtube";
import Automations from "./pages/Automations";
import Jobs from "./pages/Jobs";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"loading" | "ok" | "anon">("loading");
  const location = useLocation();

  useEffect(() => {
    if (!getToken()) {
      setState("anon");
      return;
    }
    api
      .get<User>("/auth/me")
      .then(() => setState("ok"))
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 401) setState("anon");
        else setState("ok"); // API down? let the UI degrade, don't hard lock
      });
  }, []);

  if (state === "loading")
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  if (state === "anon") return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/discovery" element={<Discovery />} />
        <Route path="/tracks" element={<Tracks />} />
        <Route path="/studio" element={<Studio />} />
        <Route path="/youtube" element={<Youtube />} />
        <Route path="/automations" element={<Automations />} />
        <Route path="/jobs" element={<Jobs />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}