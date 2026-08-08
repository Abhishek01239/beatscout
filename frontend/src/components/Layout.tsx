import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { getEmail, setToken } from "../api";
import { cn } from "./ui";
import { LogoIcon } from "./Logo";

const NAV = [
  { to: "/", label: "Dashboard", icon: "▦" },
  { to: "/discovery", label: "Discover", icon: "◎" },
  { to: "/tracks", label: "Library", icon: "♫" },
  { to: "/studio", label: "Studio", icon: "▶" },
  { to: "/youtube", label: "YouTube", icon: "▲" },
  { to: "/automations", label: "Automations", icon: "⟳" },
  { to: "/jobs", label: "Jobs", icon: "⚙" },
];

export default function Layout() {
  const navigate = useNavigate();
  const email = getEmail();

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-20 flex w-56 flex-col border-r border-surface-800 bg-surface-900/80 backdrop-blur">
        <div className="flex items-center gap-2 px-5 py-5">
          <LogoIcon />
          <div>
            <p className="text-sm font-extrabold tracking-tight text-white">
              Beat<span className="text-accent-soft">Scout</span>
            </p>
            <p className="text-[10px] text-slate-500">discover · clear · render · publish</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent/15 text-accent-soft"
                    : "text-slate-400 hover:bg-surface-800 hover:text-slate-200"
                )
              }
            >
              <span className="w-5 text-center text-xs">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-surface-800 p-4">
          <p className="truncate text-xs text-slate-400">{email ?? "guest"}</p>
          <button
            className="mt-2 text-xs text-slate-500 hover:text-danger"
            onClick={() => {
              setToken(null);
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="ml-56 flex-1 px-8 py-6">
        <Outlet />
      </main>
    </div>
  );
}