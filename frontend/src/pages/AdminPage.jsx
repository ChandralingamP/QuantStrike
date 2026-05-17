import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { getAuthUsername, getUserIsStaff } from "../utils/authCookies.js";
import { API_BASE_URL } from "../utils/constants.js";

// ── Scheduled Jobs Panel ────────────────────────────────────

function ScheduledJobsPanel({ adminUsername }) {
  const [jobs, setJobs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [triggeringJob, setTriggeringJob] = useState("");
  const [triggerResult, setTriggerResult] = useState(null);

  const loadJobs = useCallback(() => {
    if (!adminUsername) return;
    setIsLoading(true);
    setError("");
    axios
      .get(`${API_BASE_URL}/scheduler/jobs/`, {
        params: { admin_username: adminUsername },
        withCredentials: false,
      })
      .then((res) => setJobs(Array.isArray(res.data) ? res.data : []))
      .catch(() => setError("Unable to load scheduled jobs."))
      .finally(() => setIsLoading(false));
  }, [adminUsername]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Auto-refresh while a job is running
  useEffect(() => {
    const hasRunning = jobs.some(
      (j) => j.last_run && j.last_run.status === "running"
    );
    if (!hasRunning) return undefined;
    const id = setInterval(loadJobs, 3000);
    return () => clearInterval(id);
  }, [jobs, loadJobs]);

  const triggerJob = useCallback(
    (jobKey) => {
      if (!adminUsername) return;
      setTriggeringJob(jobKey);
      setTriggerResult(null);
      axios
        .post(
          `${API_BASE_URL}/scheduler/trigger/`,
          { admin_username: adminUsername, job_key: jobKey },
          { withCredentials: false }
        )
        .then((res) => {
          setTriggerResult({
            type: "success",
            message: res.data?.detail || "Job triggered.",
          });
          // Refresh after short delay so status shows "running"
          setTimeout(loadJobs, 500);
        })
        .catch((err) => {
          setTriggerResult({
            type: "error",
            message:
              err.response?.data?.detail || "Failed to trigger job.",
          });
        })
        .finally(() => setTriggeringJob(""));
    },
    [adminUsername, loadJobs]
  );

  const formatTime = (iso) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        day: "2-digit",
        month: "short",
      });
    } catch {
      return iso;
    }
  };

  const statusBadge = (run) => {
    if (!run) return null;
    const classes = {
      running: "bg-amber-500/20 text-amber-300",
      completed: "bg-emerald-500/20 text-emerald-300",
      failed: "bg-rose-500/20 text-rose-300",
    };
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
          classes[run.status] || "bg-slate-700 text-slate-300"
        }`}
      >
        {run.status === "running" && (
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
        )}
        {run.status}
      </span>
    );
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Scheduled Jobs</h2>
          <p className="text-sm text-slate-400">
            Trigger any scheduled job on-demand or view its status.
          </p>
        </div>
        <button
          type="button"
          onClick={loadJobs}
          disabled={isLoading}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-800 disabled:opacity-50"
        >
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {triggerResult && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            triggerResult.type === "success"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
              : "border-rose-500/40 bg-rose-500/10 text-rose-200"
          }`}
        >
          {triggerResult.message}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      {isLoading && jobs.length === 0 ? (
        <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-6 text-sm text-slate-300">
          Loading jobs...
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {jobs.map((job) => {
            const isRunning =
              job.last_run?.status === "running" ||
              triggeringJob === job.key;
            return (
              <div
                key={job.key}
                className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-950/70 p-4"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-white">
                      {job.label}
                    </h3>
                    {job.last_run && statusBadge(job.last_run)}
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {job.description}
                  </p>
                  <div className="mt-3 space-y-1 text-xs text-slate-500">
                    <p>
                      <span className="text-slate-400">Schedule:</span>{" "}
                      {job.schedule}
                    </p>
                    {job.next_run && (
                      <p>
                        <span className="text-slate-400">Next run:</span>{" "}
                        {formatTime(job.next_run)}
                      </p>
                    )}
                    {job.last_run?.started_at && (
                      <p>
                        <span className="text-slate-400">Last triggered:</span>{" "}
                        {formatTime(job.last_run.started_at)}
                      </p>
                    )}
                    {job.last_run?.error && (
                      <p className="text-rose-400">
                        Error: {job.last_run.error}
                      </p>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  disabled={isRunning}
                  onClick={() => triggerJob(job.key)}
                  className="mt-4 w-full rounded-lg bg-brand-500 px-3 py-2 text-xs font-semibold text-white shadow-lg shadow-brand-500/30 transition hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-slate-700"
                >
                  {isRunning ? (
                    <span className="flex items-center justify-center gap-1.5">
                      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-white" />
                      Running...
                    </span>
                  ) : (
                    "Run Now"
                  )}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ── Admin Page ──────────────────────────────────────────────

export default function AdminPage() {
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingUser, setSavingUser] = useState("");
  const [deletingUser, setDeletingUser] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);
  const [adminUsername, setAdminUsername] = useState(() => getAuthUsername());
  const navigate = useNavigate();

  const loadUsers = useCallback(() => {
    const adminUsername = getAuthUsername();
    if (!adminUsername) {
      navigate("/login", { replace: true });
      return;
    }

    setAdminUsername(adminUsername);

    setIsLoading(true);
    setError("");

    axios
      .get(`${API_BASE_URL}/auth/admin/users/`, {
        params: { admin_username: adminUsername },
        withCredentials: false,
      })
      .then((response) => {
        setUsers(Array.isArray(response.data) ? response.data : []);
      })
      .catch(() => {
        setError("Unable to fetch users. Please try again.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [navigate]);

  useEffect(() => {
    const isStaff = getUserIsStaff();
    if (!isStaff) {
      navigate("/", { replace: true });
      return;
    }
    loadUsers();
  }, [loadUsers, navigate]);

  const toggleSuperuser = useCallback(
    (username, nextValue) => {
      const adminUsername = getAuthUsername();
      if (!adminUsername) {
        navigate("/login", { replace: true });
        return;
      }

      setSavingUser(username);
      setError("");
      setAdminUsername(adminUsername);

      axios
        .patch(
          `${API_BASE_URL}/auth/admin/users/`,
          {
            admin_username: adminUsername,
            username,
            is_superuser: nextValue,
          },
          { withCredentials: false }
        )
        .then((response) => {
          const updated = response.data?.user;
          if (!updated) {
            throw new Error("Missing user in response");
          }
          setUsers((previous) =>
            previous.map((user) =>
              user.username.toLowerCase() === updated.username.toLowerCase()
                ? updated
                : user
            )
          );
        })
        .catch(() => {
          setError("Unable to update user status. Please try again.");
          loadUsers();
        })
        .finally(() => {
          setSavingUser("");
        });
    },
    [loadUsers, navigate]
  );

  const requestDeleteUser = useCallback((username) => {
    setPendingDelete({ username });
  }, []);

  const resetPendingDelete = useCallback(() => {
    setPendingDelete(null);
  }, []);

  const confirmPendingDelete = useCallback(() => {
    if (!pendingDelete) {
      return;
    }

    const adminUsername = getAuthUsername();
    if (!adminUsername) {
      navigate("/login", { replace: true });
      return;
    }

    const username = pendingDelete.username;
    setDeletingUser(username);
    setError("");
    setAdminUsername(adminUsername);

    axios
      .delete(`${API_BASE_URL}/auth/admin/users/`, {
        data: {
          admin_username: adminUsername,
          username,
        },
        withCredentials: false,
      })
      .then(() => {
        setUsers((previous) =>
          previous.filter(
            (user) => user.username.toLowerCase() !== username.toLowerCase()
          )
        );
        resetPendingDelete();
      })
      .catch(() => {
        setError("Unable to delete user. Please try again.");
        loadUsers();
      })
      .finally(() => {
        setDeletingUser("");
      });
  }, [loadUsers, navigate, pendingDelete, resetPendingDelete]);

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-white">Admin Console</h1>
          <p className="text-sm text-slate-400">
            Manage user access to QuantStrike superuser features.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => navigate("/admin/backtest")}
            className="inline-flex items-center rounded-lg bg-brand-500 px-3 py-2 text-xs font-semibold text-white shadow-brand-500/30 transition hover:bg-brand-400"
          >
            Open Strategy Backtesting
          </button>
        </div>
      </header>

      {error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <ScheduledJobsPanel adminUsername={adminUsername} />

      <div>
        <h2 className="mb-3 text-lg font-semibold text-white">User Management</h2>
        {isLoading ? (
        <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-6 text-sm text-slate-300">
          Loading users...
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70 shadow-lg shadow-black/30">
          <table className="min-w-full divide-y divide-slate-800 text-left text-sm text-slate-200">
            <thead className="bg-slate-900/80 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th scope="col" className="px-4 py-3">
                  Username
                </th>
                <th scope="col" className="px-4 py-3">
                  Email
                </th>
                <th scope="col" className="px-4 py-3 text-center">
                  Staff
                </th>
                <th scope="col" className="px-4 py-3 text-center">
                  Superuser
                </th>
                <th scope="col" className="px-4 py-3 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {users.length === 0 ? (
                <tr>
                  <td
                    className="px-4 py-6 text-center text-slate-400"
                    colSpan={5}
                  >
                    No users found.
                  </td>
                </tr>
              ) : (
                users.map((user) => {
                  const isUpdating = savingUser === user.username;
                  const isDeleting = deletingUser === user.username;
                  const nextValue = !user.is_superuser;
                  const isSelf =
                    (adminUsername || "").toLowerCase() ===
                    user.username.toLowerCase();
                  return (
                    <tr key={user.id ?? user.username}>
                      <td className="px-4 py-3 font-medium text-white">
                        {user.username}
                      </td>
                      <td className="px-4 py-3 text-slate-300">
                        {user.email || "—"}
                      </td>
                      <td className="px-4 py-3 text-center text-slate-300">
                        {user.is_staff ? "Yes" : "No"}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${
                            user.is_superuser
                              ? "bg-emerald-500/10 text-emerald-300"
                              : "bg-slate-800 text-slate-300"
                          }`}
                        >
                          {user.is_superuser ? "Enabled" : "Disabled"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            disabled={isUpdating || isDeleting || isSelf}
                            onClick={() =>
                              toggleSuperuser(user.username, nextValue)
                            }
                            className="rounded-lg bg-brand-500 px-3 py-2 text-xs font-semibold text-white shadow-brand-500/30 transition hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-slate-700"
                          >
                            {isUpdating
                              ? "Updating..."
                              : user.is_superuser
                              ? "Revoke access"
                              : "Grant access"}
                          </button>
                          <button
                            type="button"
                            disabled={isDeleting || isSelf}
                            onClick={() => requestDeleteUser(user.username)}
                            className="rounded-lg bg-rose-500/80 px-3 py-2 text-xs font-semibold text-white shadow-rose-500/20 transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:bg-slate-700"
                          >
                            {isDeleting ? "Deleting..." : "Delete user"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
      </div>

      {pendingDelete ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900/95 px-6 py-7 shadow-2xl shadow-black/50">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/10 text-lg font-bold text-rose-300">
                !
              </div>
              <div className="space-y-2">
                <h2 className="text-lg font-semibold text-white">
                  QuantStrike Admin
                </h2>
                <p className="text-sm leading-relaxed text-slate-300">
                  Permanently delete{" "}
                  <span className="font-semibold text-white">
                    {pendingDelete.username}
                  </span>
                  ? This action removes the account and all linked QuantStrike
                  data. You cannot undo this.
                </p>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                disabled={deletingUser === pendingDelete.username}
                onClick={resetPendingDelete}
                className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-200 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmPendingDelete}
                disabled={deletingUser === pendingDelete.username}
                className="rounded-lg bg-rose-500 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-white shadow-rose-500/30 transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                {deletingUser === pendingDelete.username
                  ? "Deleting..."
                  : "Delete user"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
