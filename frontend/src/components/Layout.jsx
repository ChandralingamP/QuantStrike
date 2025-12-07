import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  clearAuthUsername,
  getAuthUsername,
  getUserRole,
  getUserIsStaff,
  hasSessionExpired,
  markSessionActive,
  SESSION_TIMEOUT_MS,
} from "../utils/authCookies.js";

const baseNavItems = [
  { label: "Home", to: "/" },
  { label: "Instruments", to: "/instruments" },
  { label: "Profit & Loss", to: "/pnl" },
  { label: "Algo Configuration", to: "/algo" },
];

export default function Layout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState(() => getAuthUsername());
  const [isSuperuser, setIsSuperuser] = useState(() => getUserRole());
  const [isStaff, setIsStaff] = useState(() => getUserIsStaff());

  const navItems = useMemo(() => {
    const items = [...baseNavItems];
    if (isStaff) {
      items.push({ label: "Admin", to: "/admin" });
    }
    return items;
  }, [isStaff]);

  const handleLogout = useCallback(
    (reason = "manual", sourcePath = null) => {
      if (reason === "timeout" && typeof window !== "undefined") {
        try {
          window.sessionStorage.setItem(
            "quantstrike_logout_reason",
            "Session expired after 15 minutes of inactivity."
          );
        } catch (error) {
          // ignore storage failures
        }
      }
      clearAuthUsername();
      setUsername(null);
      setIsSuperuser(null);
      setIsStaff(null);
      const navigationOptions = sourcePath
        ? { replace: true, state: { from: sourcePath } }
        : { replace: true };
      navigate("/login", navigationOptions);
    },
    [navigate]
  );

  useEffect(() => {
    const current = getAuthUsername();
    if (!current) {
      const reason = hasSessionExpired() ? "timeout" : "manual";
      handleLogout(reason, location.pathname);
      return;
    }
    setUsername(current);
    setIsSuperuser(getUserRole());
    setIsStaff(getUserIsStaff());
  }, [handleLogout, location.pathname]);

  useEffect(() => {
    if (!username) {
      return;
    }
    if (hasSessionExpired()) {
      handleLogout("timeout", location.pathname);
      return;
    }

    markSessionActive();

    const activityHandler = () => {
      if (hasSessionExpired()) {
        handleLogout("timeout", location.pathname);
        return;
      }
      markSessionActive();
    };

    const events = ["mousemove", "keydown", "click", "touchstart", "scroll"];
    events.forEach((eventName) =>
      window.addEventListener(eventName, activityHandler)
    );

    const checkInterval = Math.max(Math.floor(SESSION_TIMEOUT_MS / 3), 10000);
    const intervalId = window.setInterval(() => {
      if (hasSessionExpired()) {
        handleLogout("timeout", location.pathname);
      }
    }, checkInterval);

    return () => {
      events.forEach((eventName) =>
        window.removeEventListener(eventName, activityHandler)
      );
      window.clearInterval(intervalId);
    };
  }, [handleLogout, location.pathname, username]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return () => {};
    }
    const syncStoredFlags = () => {
      setIsSuperuser(getUserRole());
      setIsStaff(getUserIsStaff());
    };
    window.addEventListener("storage", syncStoredFlags);
    return () => {
      window.removeEventListener("storage", syncStoredFlags);
    };
  }, []);

  useEffect(() => {
    if (!isStaff && location.pathname.startsWith("/admin")) {
      navigate("/", { replace: true });
    }
  }, [isStaff, location.pathname, navigate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-950 to-slate-900">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col">
        <nav className="flex flex-wrap items-center justify-between gap-6 px-6 py-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-500 text-lg font-bold text-white">
              QS
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm uppercase tracking-[0.4em] text-brand-300">
                  QuantStrike
                </p>
                {isSuperuser === false ? (
                  <span className="rounded-full border border-amber-400/50 bg-amber-500/10 px-2 py-[2px] text-[10px] font-semibold uppercase tracking-wide text-amber-200">
                    Demo
                  </span>
                ) : null}
              </div>
              <p className="text-xs text-slate-400">
                Algorithmic Trading Control Center
              </p>
            </div>
          </div>
          <div className="flex flex-1 items-center justify-center">
            <div className="flex items-center gap-4 rounded-full border border-slate-800 bg-slate-900/60 px-6 py-2 text-xs font-semibold text-slate-400">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `transition hover:text-brand-200 ${
                      isActive ? "text-brand-300" : "text-slate-400"
                    }`
                  }
                  end={item.to === "/"}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="rounded-full border border-slate-800 bg-slate-900/60 px-4 py-2 text-xs text-slate-300">
              Logged in as{" "}
              <span className="font-semibold text-white">
                {username || "Guest"}
              </span>
            </div>
            <button
              type="button"
              onClick={() => handleLogout("manual", location.pathname)}
              className="rounded-full bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-700"
            >
              Logout
            </button>
          </div>
        </nav>
        <main className="flex-1 px-6 pb-12">
          {typeof children !== "undefined" ? children : <Outlet />}
        </main>
        <footer className="border-t border-slate-800 px-6 py-6 text-xs text-slate-500">
          Built for rapid quant experimentation. © {new Date().getFullYear()}{" "}
          QuantStrike.
        </footer>
      </div>
    </div>
  );
}
