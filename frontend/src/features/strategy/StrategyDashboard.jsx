import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import classNames from "classnames";
import { createStrategy, fetchStrategies } from "./strategySlice";

const defaultFormState = {
  name: "",
  symbol: "",
  timeframe: "",
  notes: "",
};

export default function StrategyDashboard() {
  const dispatch = useDispatch();
  const { items, status, error, lastCreated } = useSelector(
    (state) => state.strategy
  );
  const [formState, setFormState] = useState(defaultFormState);

  useEffect(() => {
    dispatch(fetchStrategies());
  }, [dispatch]);

  useEffect(() => {
    if (status === "succeeded" && lastCreated) {
      setFormState(defaultFormState);
    }
  }, [status, lastCreated]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormState((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!formState.name.trim()) {
      return;
    }
    dispatch(createStrategy(formState));
  };

  const content = useMemo(() => {
    if (status === "loading") {
      return <p className="text-sm text-slate-400">Loading strategies...</p>;
    }
    if (status === "failed") {
      return <p className="text-sm text-rose-400">{error}</p>;
    }
    if (!items.length) {
      return (
        <p className="text-sm text-slate-400">
          No strategies yet. Create your first one below.
        </p>
      );
    }
    return (
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((strategy) => (
          <li
            key={strategy.id}
            className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 shadow-lg shadow-black/40 backdrop-blur"
          >
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">
                {strategy.name}
              </h3>
              <span className="rounded-full bg-brand-500/20 px-2 py-1 text-xs font-medium text-brand-300">
                {strategy.timeframe || "N/A"}
              </span>
            </div>
            <dl className="space-y-1 text-sm text-slate-300">
              <div className="flex justify-between">
                <dt className="text-slate-400">Symbol</dt>
                <dd className="font-medium">{strategy.symbol || "-"}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">Status</dt>
                <dd className="font-medium capitalize">
                  {strategy.status || "draft"}
                </dd>
              </div>
            </dl>
            {strategy.notes ? (
              <p className="mt-3 rounded bg-slate-800/80 p-3 text-sm text-slate-200">
                {strategy.notes}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    );
  }, [error, items, status]);

  return (
    <section className="mx-auto flex w-full max-w-6xl flex-col gap-12 px-4 py-8">
      <header className="space-y-3">
        <p className="text-sm uppercase tracking-[0.3em] text-brand-400">
          QuantStrike
        </p>
        <h1 className="text-3xl font-bold text-white sm:text-4xl">
          Trading Strategy Command Center
        </h1>
        <p className="max-w-2xl text-base text-slate-300">
          Monitor live strategies, manage deployments, and iterate on your quant
          research faster with a cohesive dashboard and streamlined workflow.
        </p>
      </header>

      <div className="grid gap-10 lg:grid-cols-[2fr,1fr]">
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-white">
              Active Strategies
            </h2>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span
                className={classNames(
                  "h-2 w-2 rounded-full",
                  status === "loading"
                    ? "bg-amber-400 animate-pulse"
                    : "bg-emerald-400"
                )}
              ></span>
              {status === "loading" ? "Syncing" : "Up to date"}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl shadow-black/40 backdrop-blur">
            {content}
          </div>
        </div>

        <aside className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl shadow-black/40 backdrop-blur">
          <h2 className="text-lg font-semibold text-white">Add Strategy</h2>
          <p className="mb-4 text-sm text-slate-400">
            Capture baseline parameters for a new idea.
          </p>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label
                className="text-sm font-medium text-slate-300"
                htmlFor="name"
              >
                Strategy Name
              </label>
              <input
                className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white focus:border-brand-400 focus:outline-none focus:ring focus:ring-brand-500/20"
                id="name"
                name="name"
                value={formState.name}
                onChange={handleChange}
                placeholder="Momentum Breakout"
                required
              />
            </div>
            <div className="space-y-2">
              <label
                className="text-sm font-medium text-slate-300"
                htmlFor="symbol"
              >
                Symbol
              </label>
              <input
                className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white focus:border-brand-400 focus:outline-none focus:ring focus:ring-brand-500/20"
                id="symbol"
                name="symbol"
                value={formState.symbol}
                onChange={handleChange}
                placeholder="AAPL"
              />
            </div>
            <div className="space-y-2">
              <label
                className="text-sm font-medium text-slate-300"
                htmlFor="timeframe"
              >
                Timeframe
              </label>
              <input
                className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white focus:border-brand-400 focus:outline-none focus:ring focus:ring-brand-500/20"
                id="timeframe"
                name="timeframe"
                value={formState.timeframe}
                onChange={handleChange}
                placeholder="15m"
              />
            </div>
            <div className="space-y-2">
              <label
                className="text-sm font-medium text-slate-300"
                htmlFor="notes"
              >
                Notes
              </label>
              <textarea
                className="h-24 w-full resize-none rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white focus:border-brand-400 focus:outline-none focus:ring focus:ring-brand-500/20"
                id="notes"
                name="notes"
                value={formState.notes}
                onChange={handleChange}
                placeholder="Key signals, risk parameters, and deployment plan"
              />
            </div>
            <button
              className="w-full rounded-lg bg-brand-500 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-brand-500/30 transition hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-slate-600"
              type="submit"
              disabled={status === "loading"}
            >
              {status === "loading" ? "Saving..." : "Create Strategy"}
            </button>
            {status === "failed" ? (
              <p className="text-xs text-rose-400">{error}</p>
            ) : null}
          </form>
        </aside>
      </div>
    </section>
  );
}
