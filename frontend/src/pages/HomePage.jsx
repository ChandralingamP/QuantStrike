import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  connectBrokerage,
  fetchAccountStatus,
  hydrateFromCache as hydrateHomeFromCache,
} from "../features/home/homeSlice";
import { getAuthUsername } from "../utils/authCookies.js";
import {
  CACHE_TTL_MS,
  getCacheEntry,
  isCacheEntryFresh,
} from "../utils/dataCache.js";

const HOME_CACHE_NAMESPACE = "home_status";

const defaultFormState = {
  mpin: "",
  totp: "",
};

export default function HomePage() {
  const dispatch = useDispatch();
  const authUsername = getAuthUsername();
  const { details, status, error, connection } = useSelector(
    (state) => state.home
  );
  const [formState, setFormState] = useState(defaultFormState);

  useEffect(() => {
    if (!authUsername) {
      return undefined;
    }

    const cacheEntry = getCacheEntry(HOME_CACHE_NAMESPACE, authUsername);
    if (cacheEntry?.value) {
      dispatch(hydrateHomeFromCache(cacheEntry.value));
    }

    const age = cacheEntry
      ? Date.now() - cacheEntry.timestamp
      : Number.POSITIVE_INFINITY;

    const triggerFetch = () => {
      dispatch(fetchAccountStatus(authUsername));
    };

    if (!cacheEntry || !isCacheEntryFresh(cacheEntry)) {
      triggerFetch();
      return undefined;
    }

    let timeoutId;
    if (typeof window !== "undefined") {
      const delay = Math.max(CACHE_TTL_MS - age, 0);
      timeoutId = window.setTimeout(triggerFetch, delay);
    }

    return () => {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [dispatch, authUsername]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormState((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!formState.mpin || !formState.totp) {
      return;
    }
    if (!authUsername) {
      return;
    }
    dispatch(connectBrokerage({ ...formState, username: authUsername })).then(
      (action) => {
        if (action.meta.requestStatus === "fulfilled") {
          setFormState(defaultFormState);
        }
      }
    );
  };

  const isInitialLoading = status === "loading" && !details;
  const detailsSnapshot = details || {};

  const lastUpdated =
    detailsSnapshot.last_updated || detailsSnapshot.last_connected_at;
  const connectionState = (
    detailsSnapshot.connection_state || ""
  ).toLowerCase();
  const effectiveConnectionState = connectionState
    ? connectionState
    : connection.status === "succeeded"
    ? "connected"
    : connection.status === "failed"
    ? "failed"
    : "idle";

  const badgeClass =
    effectiveConnectionState === "connected"
      ? "bg-emerald-500/20 text-emerald-300"
      : effectiveConnectionState === "failed"
      ? "bg-rose-500/20 text-rose-300"
      : "bg-slate-700/60 text-slate-300";

  const badgeLabel =
    effectiveConnectionState === "connected"
      ? "Connected"
      : effectiveConnectionState === "failed"
      ? "Disconnected"
      : "Idle";

  const lastConnected =
    detailsSnapshot.last_connected_at || connection.lastConnectedAt || null;
  const connectionMessage =
    connection.status !== "idle" && connection.message
      ? connection.message
      : null;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <section className="rounded-3xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl shadow-black/40 backdrop-blur">
        <header className="mb-6 flex flex-col gap-2">
          <p className="text-xs uppercase tracking-[0.4em] text-brand-300">
            Account
          </p>
          <h1 className="text-3xl font-semibold text-white">
            Brokerage Connection Overview
          </h1>
          <p className="text-sm text-slate-400">
            Review your client credentials and initiate a fresh brokerage
            session using MPIN and TOTP.
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-[1.2fr,1fr]">
          <article className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">
                Client Profile
              </h2>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${badgeClass}`}
              >
                {badgeLabel}
              </span>
            </div>

            <dl className="mt-6 space-y-3 text-sm text-slate-200">
              <div className="flex justify-between">
                <dt className="text-slate-400">Client ID</dt>
                <dd className="font-medium">
                  {isInitialLoading
                    ? "Loading..."
                    : detailsSnapshot.client_id || "—"}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">API Key</dt>
                <dd className="font-medium">
                  {detailsSnapshot.api_key_masked || "************"}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">Session Status</dt>
                <dd className="font-medium">{badgeLabel}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">Last Connected</dt>
                <dd className="font-medium">
                  {lastConnected
                    ? new Date(lastConnected).toLocaleString()
                    : "—"}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">Last Updated</dt>
                <dd className="font-medium">
                  {lastUpdated ? new Date(lastUpdated).toLocaleString() : "—"}
                </dd>
              </div>
            </dl>
            {connectionMessage ? (
              <p className="mt-4 text-xs text-slate-400">{connectionMessage}</p>
            ) : null}
            {error ? (
              <p className="mt-4 text-xs text-rose-400">{error}</p>
            ) : null}
          </article>

          <article className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
            <h2 className="text-lg font-semibold text-white">
              Establish Session
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Submit MPIN and TOTP to connect your brokerage session securely.
            </p>
            <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <label
                  className="text-sm font-medium text-slate-300"
                  htmlFor="mpin"
                >
                  MPIN
                </label>
                <input
                  id="mpin"
                  name="mpin"
                  type="password"
                  value={formState.mpin}
                  onChange={handleChange}
                  placeholder="••••"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white focus:border-brand-400 focus:outline-none focus:ring focus:ring-brand-500/20"
                  required
                />
              </div>
              <div className="space-y-2">
                <label
                  className="text-sm font-medium text-slate-300"
                  htmlFor="totp"
                >
                  TOTP
                </label>
                <input
                  id="totp"
                  name="totp"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={formState.totp}
                  onChange={handleChange}
                  placeholder="123456"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white focus:border-brand-400 focus:outline-none focus:ring focus:ring-brand-500/20"
                  maxLength={8}
                  required
                />
              </div>
              <button
                type="submit"
                disabled={connection.status === "loading"}
                className="w-full rounded-lg bg-brand-500 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-brand-500/30 transition hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-slate-600"
              >
                {connection.status === "loading" ? "Connecting..." : "Connect"}
              </button>
              {connection.message ? (
                <p
                  className={`text-xs ${
                    connection.status === "failed"
                      ? "text-rose-400"
                      : "text-emerald-400"
                  }`}
                >
                  {connection.message}
                </p>
              ) : null}
            </form>
          </article>
        </div>
      </section>
    </div>
  );
}
