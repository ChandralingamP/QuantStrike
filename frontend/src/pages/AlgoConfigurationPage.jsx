import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { fetchAlgoConfig, updateAlgoConfig } from "../features/algo/algoSlice";
import {
  getAuthUsername,
  getUserIsStaff,
  getUserRole,
} from "../utils/authCookies.js";

const toggleClasses = (active) =>
  `inline-flex h-6 w-11 items-center rounded-full border border-transparent px-1 transition ${
    active ? "justify-end bg-emerald-500/30" : "justify-start bg-slate-700/80"
  }`;

export default function AlgoConfigurationPage() {
  const dispatch = useDispatch();
  const { config, status, error, updating, updateError } = useSelector(
    (state) => state.algo
  );
  const [formState, setFormState] = useState({
    algo_active: false,
    market_active: false,
    strategy_alpha_active: false,
    strategy_alpha_instrument_ids: [],
    strategy_alpha_mode: "demo",
  });
  const [instrumentOptions, setInstrumentOptions] = useState([]);
  const [strategyMeta, setStrategyMeta] = useState({ mode: "demo" });
  const allowLiveMode = useMemo(() => {
    const isSuperuser = getUserRole();
    const isStaff = getUserIsStaff();
    return Boolean(isSuperuser || isStaff);
  }, []);

  useEffect(() => {
    const username = getAuthUsername();
    if (username) {
      dispatch(fetchAlgoConfig());
    }
  }, [dispatch]);

  useEffect(() => {
    if (config) {
      setFormState((prev) => ({
        ...prev,
        algo_active: Boolean(config.algo_active),
        market_active: Boolean(config.market_active),
        strategy_alpha_active: Boolean(config.strategy_alpha?.active),
        strategy_alpha_instrument_ids:
          config.strategy_alpha?.selected_instrument_ids || [],
        strategy_alpha_mode: config.strategy_alpha?.mode || "demo",
      }));
      if (config.strategy_alpha?.instrument_options) {
        setInstrumentOptions(config.strategy_alpha.instrument_options);
      }
      if (config.strategy_alpha) {
        setStrategyMeta({
          mode: config.strategy_alpha.mode,
          activated_at: config.strategy_alpha.activated_at,
        });
      }
    }
  }, [config]);

  const handleToggle = (key) => {
    setFormState((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleInstrumentToggle = (instrumentId) => {
    setFormState((prev) => {
      const current = new Set(prev.strategy_alpha_instrument_ids);
      if (current.has(instrumentId)) {
        current.delete(instrumentId);
      } else {
        current.add(instrumentId);
      }
      return {
        ...prev,
        strategy_alpha_instrument_ids: Array.from(current),
      };
    });
  };

  const toggleAllInstruments = () => {
    setFormState((prev) => {
      if (
        prev.strategy_alpha_instrument_ids.length === instrumentOptions.length
      ) {
        return { ...prev, strategy_alpha_instrument_ids: [] };
      }
      return {
        ...prev,
        strategy_alpha_instrument_ids: instrumentOptions.map(
          (option) => option.id
        ),
      };
    });
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    dispatch(updateAlgoConfig(formState));
  };

  const strategyActivatedAtLabel = useMemo(() => {
    if (!strategyMeta.activated_at) {
      return "—";
    }
    try {
      return new Date(strategyMeta.activated_at).toLocaleString();
    } catch (error) {
      return strategyMeta.activated_at;
    }
  }, [strategyMeta.activated_at]);

  const selectedInstrumentLabels = useMemo(() => {
    const selectedSet = new Set(formState.strategy_alpha_instrument_ids);
    return instrumentOptions
      .filter((option) => selectedSet.has(option.id))
      .map((option) => {
        const expiry = option.expiry ? ` · Exp ${option.expiry}` : "";
        return `${option.label}${expiry}`;
      });
  }, [formState.strategy_alpha_instrument_ids, instrumentOptions]);

  const infoItems = config
    ? [
        {
          label: "Algo Active",
          value: config.algo_active ? "Enabled" : "Disabled",
        },
        {
          label: "Market Active",
          value: config.market_active ? "Enabled" : "Disabled",
        },
        {
          label: "Strategy Alpha",
          value: config.strategy_alpha?.active ? "Enabled" : "Disabled",
        },
        {
          label: "Strategy Mode",
          value:
            (config.strategy_alpha?.mode || "demo") === "live"
              ? "Live"
              : "Demo",
        },
        {
          label: "Market Updated",
          value: config.market_active_updated_at
            ? new Date(config.market_active_updated_at).toLocaleString()
            : "—",
        },
        {
          label: "Last Updated",
          value: config.updated_at
            ? new Date(config.updated_at).toLocaleString()
            : "—",
        },
        {
          label: "Strategy Activated",
          value: strategyActivatedAtLabel,
        },
      ]
    : [];

  const excludedExtraFields = new Set([
    "algo_active",
    "market_active",
    "market_active_updated_at",
    "updated_at",
    "created_at",
    "id",
    "strategy_alpha",
    "strategy_alpha_active",
    "strategy_alpha_mode",
    "strategy_alpha_instrument_ids",
  ]);

  const extraItems = config
    ? Object.entries(config).filter(([key, value]) => {
        const isPrimitive =
          value === null ||
          ["string", "number", "boolean"].includes(typeof value);
        return !excludedExtraFields.has(key) && isPrimitive;
      })
    : [];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold text-white">
          Algo Configuration
        </h1>
        <p className="text-sm text-slate-400">
          Toggle algo and market availability, then review runtime metadata to
          ensure trading conditions match expectations.
        </p>
      </header>

      {error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1fr,1fr]">
        <section className="rounded-3xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl shadow-black/40">
          <header className="mb-6 flex flex-col gap-2">
            <h2 className="text-xl font-semibold text-white">Controls</h2>
            <p className="text-sm text-slate-400">
              Update live algo switches and sync with backend safeguards.
            </p>
          </header>
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="flex items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3">
              <div>
                <p className="text-sm font-medium text-white">Algo Active</p>
                <p className="text-xs text-slate-400">
                  Enables or pauses the core strategy execution engine.
                </p>
              </div>
              <button
                type="button"
                className={toggleClasses(formState.algo_active)}
                onClick={() => handleToggle("algo_active")}
              >
                <span className="h-4 w-4 rounded-full bg-white/90" />
              </button>
            </div>

            <div className="flex items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3">
              <div>
                <p className="text-sm font-medium text-white">Market Active</p>
                <p className="text-xs text-slate-400">
                  Controls whether orders can be transmitted to the market.
                </p>
              </div>
              <button
                type="button"
                className={toggleClasses(formState.market_active)}
                onClick={() => handleToggle("market_active")}
              >
                <span className="h-4 w-4 rounded-full bg-white/90" />
              </button>
            </div>

            <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-white">
                    Strategy Alpha
                  </p>
                  <p className="text-xs text-slate-400">
                    Enable the breakout strategy and choose which instruments it
                    manages.
                  </p>
                </div>
                <button
                  type="button"
                  className={toggleClasses(formState.strategy_alpha_active)}
                  onClick={() => handleToggle("strategy_alpha_active")}
                >
                  <span className="h-4 w-4 rounded-full bg-white/90" />
                </button>
              </div>

              {formState.strategy_alpha_active ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-2">
                    <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
                      Execution Mode
                    </div>
                    <div className="flex items-center gap-2">
                      {[
                        { value: "demo", label: "Demo" },
                        { value: "live", label: "Live" },
                      ].map((option) => {
                        const isActive =
                          formState.strategy_alpha_mode === option.value;
                        const isDisabled =
                          option.value === "live" && !allowLiveMode;
                        return (
                          <button
                            key={option.value}
                            type="button"
                            disabled={isDisabled}
                            onClick={() =>
                              setFormState((prev) => ({
                                ...prev,
                                strategy_alpha_mode: option.value,
                              }))
                            }
                            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                              isActive
                                ? "bg-brand-500 text-white shadow-md shadow-brand-500/40"
                                : "text-slate-300 hover:text-white"
                            } ${
                              isDisabled ? "cursor-not-allowed opacity-50" : ""
                            }`}
                          >
                            {option.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  {!allowLiveMode ? (
                    <p className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs text-slate-400">
                      Live mode is limited to staff or admin accounts. Contact
                      an administrator to enable real executions.
                    </p>
                  ) : null}

                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>
                      Selected {formState.strategy_alpha_instrument_ids.length}{" "}
                      of {instrumentOptions.length}
                    </span>
                    <button
                      type="button"
                      onClick={toggleAllInstruments}
                      className="text-brand-300 transition hover:text-brand-200"
                    >
                      {formState.strategy_alpha_instrument_ids.length ===
                      instrumentOptions.length
                        ? "Clear"
                        : "Select All"}
                    </button>
                  </div>

                  {instrumentOptions.length === 0 ? (
                    <p className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-xs text-slate-400">
                      No instruments found. Configure instruments first to
                      enable this strategy.
                    </p>
                  ) : null}

                  <div className="grid gap-2">
                    {instrumentOptions.map((option) => {
                      const checked =
                        formState.strategy_alpha_instrument_ids.includes(
                          option.id
                        );
                      return (
                        <label
                          key={option.id}
                          className={`flex cursor-pointer items-center justify-between rounded-xl border px-3 py-2 text-sm transition ${
                            checked
                              ? "border-brand-400 bg-brand-500/10 text-white"
                              : "border-slate-700/60 bg-slate-900/50 text-slate-200"
                          }`}
                        >
                          <span className="flex flex-col">
                            <span className="font-medium">{option.label}</span>
                            <span className="text-xs text-slate-400">
                              {option.expiry
                                ? `Expiry ${option.expiry}`
                                : "Expiry not set"}{" "}
                              · {option.transaction} · Lots {option.lots}
                            </span>
                          </span>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => handleInstrumentToggle(option.id)}
                            className="h-4 w-4 accent-brand-400"
                          />
                        </label>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>

            <button
              type="submit"
              disabled={updating || status === "loading"}
              className="w-full rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-brand-500/30 transition hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-slate-600"
            >
              {updating ? "Saving..." : "Save Changes"}
            </button>
            {updateError ? (
              <p className="text-xs text-rose-300">{updateError}</p>
            ) : null}
          </form>
        </section>

        <section className="rounded-3xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl shadow-black/40">
          <header className="mb-6 flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">Algo Status</h2>
              <p className="text-xs text-slate-400">
                Snapshot of current configuration and system timestamps.
              </p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                config?.algo_active
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "bg-slate-700/60 text-slate-300"
              }`}
            >
              {config?.algo_active ? "Running" : "Paused"}
            </span>
          </header>

          <dl className="space-y-3 text-sm text-slate-200">
            {infoItems.map((item) => (
              <div key={item.label} className="flex justify-between">
                <dt className="text-slate-400">{item.label}</dt>
                <dd className="font-medium">{item.value}</dd>
              </div>
            ))}
            {selectedInstrumentLabels.length ? (
              <div className="flex flex-col rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-3 text-xs text-slate-300">
                <span className="mb-1 font-semibold text-slate-200">
                  Strategy Instruments
                </span>
                <ul className="list-disc space-y-1 pl-4">
                  {selectedInstrumentLabels.map((label) => (
                    <li key={label}>{label}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {extraItems.map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <dt className="text-slate-400">{key.replace(/_/g, " ")}</dt>
                <dd className="font-medium">{String(value)}</dd>
              </div>
            ))}
            {status === "loading" ? (
              <p className="text-xs text-slate-400">Loading configuration...</p>
            ) : null}
          </dl>
        </section>
      </div>
    </div>
  );
}
