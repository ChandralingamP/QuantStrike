import { useCallback, useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../utils/constants.js";
import { getAuthUsername, getUserIsStaff } from "../utils/authCookies.js";
import { fetchInstruments } from "../features/instruments/instrumentsSlice.js";

export default function StrategyBacktestPage() {
  const [username, setUsername] = useState("");
  const [selectedStrategy, setSelectedStrategy] = useState("strategy_alpha");
  const [mode, setMode] = useState("demo");
  const [marketDate, setMarketDate] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState([]);

  const dispatch = useDispatch();
  const instrumentsState = useSelector((state) => state.instruments);
  const [selectedInstrumentIds, setSelectedInstrumentIds] = useState([]);

  const navigate = useNavigate();

  useEffect(() => {
    const isStaff = getUserIsStaff();
    if (!isStaff) {
      navigate("/", { replace: true });
      return;
    }
    const currentUser = getAuthUsername();
    if (!currentUser) {
      navigate("/login", { replace: true });
      return;
    }
  }, [navigate]);

  useEffect(() => {
    if (!username.trim()) {
      return;
    }
    dispatch(fetchInstruments(username.trim()));
    setSelectedInstrumentIds([]);
  }, [dispatch, username]);

  const handleSubmit = useCallback(
    (event) => {
      event.preventDefault();
      setError("");

      if (!username.trim()) {
        setError("Target username is required.");
        return;
      }

      if (marketDate && (startDate || endDate)) {
        setError(
          "Use either a single market date or a start/end range, not both.",
        );
        return;
      }

      if ((startDate && !endDate) || (!startDate && endDate)) {
        setError("Both start and end dates are required for a range.");
        return;
      }

      setIsRunning(true);
      setRuns([]);

      const payload = {
        username: username.trim(),
        api_username: getAuthUsername(),
        mode,
        strategy_code: selectedStrategy,
      };

      if (marketDate) {
        payload.market_date = marketDate;
      } else if (startDate && endDate) {
        payload.start_date = startDate;
        payload.end_date = endDate;
      }

      if (selectedInstrumentIds.length > 0) {
        payload.instrument_ids = selectedInstrumentIds;
      }

      axios
        .post(`${API_BASE_URL}/strategy/one/backtest/`, payload, {
          withCredentials: true,
        })
        .then((response) => {
          const data = response.data || {};
          setRuns(Array.isArray(data.runs) ? data.runs : []);
        })
        .catch((error) => {
          const detail =
            error?.response?.data?.detail ||
            error?.response?.data?.non_field_errors?.[0] ||
            "Unable to run backtest. Please try again.";
          setError(detail);
        })
        .finally(() => {
          setIsRunning(false);
        });
    },
    [
      username,
      mode,
      marketDate,
      startDate,
      endDate,
      selectedStrategy,
      selectedInstrumentIds,
    ],
  );

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-white">
          Strategy Backtesting
        </h1>
        <p className="text-sm text-slate-400">
          Admin-only backtesting for Strategy Alpha using historical SmartAPI
          data.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/70 p-4 shadow-lg shadow-black/30"
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-200">
              Target username
            </label>
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none ring-brand-500/60 placeholder:text-slate-500 focus:border-brand-500 focus:ring-2"
              placeholder="User to backtest for"
            />
            <p className="text-xs text-slate-400">
              Strategy will use this user&apos;s instruments and expiries.
            </p>
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-200">
              Mode
            </label>
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none ring-brand-500/60 focus:border-brand-500 focus:ring-2"
            >
              <option value="demo">Demo (recommended for backtesting)</option>
              <option value="live">Live</option>
            </select>
          </div>
        </div>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-slate-200">
            Strategy
          </label>
          <select
            value={selectedStrategy}
            onChange={(event) => setSelectedStrategy(event.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none ring-brand-500/60 focus:border-brand-500 focus:ring-2"
          >
            <option value="strategy_alpha">Strategy Alpha</option>
            {/* In future you can add other strategies here */}
          </select>
          <p className="text-xs text-slate-400">
            Choose which strategy engine to run for this backtest.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-200">
              Single market date
            </label>
            <input
              type="date"
              value={marketDate}
              onChange={(event) => setMarketDate(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none ring-brand-500/60 focus:border-brand-500 focus:ring-2"
            />
            <p className="text-xs text-slate-400">
              Leave blank when using a start/end range.
            </p>
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-200">
              Range start date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none ring-brand-500/60 focus:border-brand-500 focus:ring-2"
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-200">
              Range end date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none ring-brand-500/60 focus:border-brand-500 focus:ring-2"
            />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-slate-200">
              Instruments for backtesting
            </h2>
            <span className="text-xs text-slate-500">
              Loaded from the selected user&apos;s configuration
            </span>
          </div>
          {instrumentsState.status === "loading" && (
            <p className="text-xs text-slate-400">Loading instruments…</p>
          )}
          {instrumentsState.error && (
            <p className="text-xs text-rose-300">
              {String(instrumentsState.error)}
            </p>
          )}
          {instrumentsState.items.length > 0 && (
            <div className="mt-1 max-h-48 space-y-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/40 p-2 text-xs text-slate-200">
              {instrumentsState.items.map((instrument) => (
                <label
                  key={instrument.id}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 hover:bg-slate-800/60"
                >
                  <input
                    type="checkbox"
                    checked={selectedInstrumentIds.includes(instrument.id)}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setSelectedInstrumentIds((prev) => {
                        if (checked) {
                          return prev.includes(instrument.id)
                            ? prev
                            : [...prev, instrument.id];
                        }
                        return prev.filter((id) => id !== instrument.id);
                      });
                    }}
                    className="h-3 w-3 rounded border-slate-600 bg-slate-900 text-brand-500"
                  />
                  <span className="font-medium text-slate-100">
                    {instrument.instrument}
                  </span>
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">
                    {instrument.transaction} · {instrument.contract_expiry_code}
                  </span>
                </label>
              ))}
            </div>
          )}
          {instrumentsState.items.length === 0 && !instrumentsState.error && (
            <p className="text-xs text-slate-500">
              Enter a username above to load instruments for backtesting.
            </p>
          )}
        </div>

        {error ? (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={isRunning}
          className="inline-flex items-center rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white shadow-brand-500/30 transition hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-slate-700"
        >
          {isRunning ? "Running backtest..." : "Run backtest"}
        </button>
      </form>

      {runs.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-white">Backtest results</h2>
          <div className="space-y-4">
            {runs.map((run) => (
              <div
                key={String(run.date)}
                className="space-y-2 rounded-xl border border-slate-800 bg-slate-900/70 p-4"
              >
                <div className="flex items-center justify-between text-sm">
                  <div className="font-medium text-slate-100">
                    Date: {String(run.date)}
                  </div>
                  <div className="text-slate-400">
                    Mode: {run.summary?.mode || mode}
                  </div>
                </div>
                <div className="text-sm text-slate-300">
                  Status: {run.summary?.status}
                  {typeof run.summary?.opened_trades === "number" && (
                    <>
                      {" · Opened: "}
                      {run.summary.opened_trades}
                      {" · Closed: "}
                      {run.summary.closed_trades ?? 0}
                    </>
                  )}
                  {run.summary?.net_pnl && (
                    <span
                      className={`ml-2 font-semibold ${
                        parseFloat(run.summary.net_pnl) > 0
                          ? "text-emerald-400"
                          : parseFloat(run.summary.net_pnl) < 0
                            ? "text-rose-400"
                            : "text-slate-300"
                      }`}
                    >
                      Net P&L: ₹
                      {parseFloat(run.summary.net_pnl).toLocaleString("en-IN", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </span>
                  )}
                </div>
                {Array.isArray(run.summary?.instrument_summaries) && (
                  <div className="mt-2 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40">
                    <table className="min-w-full divide-y divide-slate-800 text-left text-xs text-slate-200">
                      <thead className="bg-slate-900/80 text-[11px] uppercase tracking-wide text-slate-400">
                        <tr>
                          <th className="px-3 py-2">Instrument</th>
                          <th className="px-3 py-2">Opened</th>
                          <th className="px-3 py-2">Closed</th>
                          <th className="px-3 py-2">P&L</th>
                          <th className="px-3 py-2">Message</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {run.summary.instrument_summaries.map((instrument) => (
                          <tr key={instrument.instrument}>
                            <td className="px-3 py-2 font-medium text-white">
                              {instrument.instrument}
                            </td>
                            <td className="px-3 py-2">{instrument.opened}</td>
                            <td className="px-3 py-2">{instrument.closed}</td>
                            <td
                              className={`px-3 py-2 font-medium ${
                                instrument.pnl && parseFloat(instrument.pnl) > 0
                                  ? "text-emerald-400"
                                  : instrument.pnl &&
                                      parseFloat(instrument.pnl) < 0
                                    ? "text-rose-400"
                                    : "text-slate-300"
                              }`}
                            >
                              {instrument.pnl
                                ? `₹${parseFloat(instrument.pnl).toLocaleString(
                                    "en-IN",
                                    {
                                      minimumFractionDigits: 2,
                                      maximumFractionDigits: 2,
                                    },
                                  )}`
                                : "—"}
                            </td>
                            <td className="px-3 py-2 text-slate-300">
                              {instrument.message || ""}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {Array.isArray(run.summary?.trades) &&
                  run.summary.trades.length > 0 && (
                    <div className="mt-3 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40">
                      <div className="border-b border-slate-800 bg-slate-900/60 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Trade Details
                      </div>
                      <table className="min-w-full divide-y divide-slate-800 text-left text-xs text-slate-200">
                        <thead className="bg-slate-900/80 text-[11px] uppercase tracking-wide text-slate-400">
                          <tr>
                            <th className="px-3 py-2">Contract</th>
                            <th className="px-3 py-2">Type</th>
                            <th className="px-3 py-2">Entry</th>
                            <th className="px-3 py-2">Exit</th>
                            <th className="px-3 py-2">SL</th>
                            <th className="px-3 py-2">Target</th>
                            <th className="px-3 py-2">Reason</th>
                            <th className="px-3 py-2">P&L</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                          {run.summary.trades.map((trade, tradeIdx) => (
                            <tr key={trade.trade_id || tradeIdx}>
                              <td className="px-3 py-2 font-medium text-white">
                                {trade.contract || trade.instrument}
                              </td>
                              <td className="px-3 py-2">
                                <span
                                  className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                                    trade.option_type === "CE"
                                      ? "bg-emerald-500/20 text-emerald-300"
                                      : "bg-rose-500/20 text-rose-300"
                                  }`}
                                >
                                  {trade.option_type}
                                </span>
                              </td>
                              <td className="px-3 py-2">
                                ₹{trade.entry_price}
                              </td>
                              <td className="px-3 py-2">₹{trade.exit_price}</td>
                              <td className="px-3 py-2 text-slate-400">
                                {trade.stop_loss ? `₹${trade.stop_loss}` : "—"}
                              </td>
                              <td className="px-3 py-2 text-slate-400">
                                {trade.target ? `₹${trade.target}` : "—"}
                              </td>
                              <td className="px-3 py-2">
                                <span
                                  className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                                    trade.exit_reason === "target"
                                      ? "bg-emerald-500/20 text-emerald-300"
                                      : trade.exit_reason === "stop_loss"
                                        ? "bg-rose-500/20 text-rose-300"
                                        : trade.exit_reason === "trailing_stop"
                                          ? "bg-amber-500/20 text-amber-300"
                                          : "bg-slate-500/20 text-slate-300"
                                  }`}
                                >
                                  {(trade.exit_reason || "").replace("_", " ")}
                                </span>
                              </td>
                              <td
                                className={`px-3 py-2 font-medium ${
                                  parseFloat(trade.pnl) > 0
                                    ? "text-emerald-400"
                                    : parseFloat(trade.pnl) < 0
                                      ? "text-rose-400"
                                      : "text-slate-300"
                                }`}
                              >
                                ₹
                                {parseFloat(trade.pnl).toLocaleString("en-IN", {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
