import { useCallback, useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  fetchInstruments,
  updateInstrument,
  hydrateFromCache as hydrateInstrumentsFromCache,
} from "../features/instruments/instrumentsSlice";
import { getAuthUsername } from "../utils/authCookies.js";
import {
  CACHE_TTL_MS,
  getCacheEntry,
  isCacheEntryFresh,
} from "../utils/dataCache.js";
import Modal from "../components/Modal.jsx";
import { flushSync } from "react-dom";

const INSTRUMENTS_CACHE_NAMESPACE = "instruments";

const numericFields = [
  "no_of_lots",
  "pl_exit_lots",
  "premium_price",
  "pl_points",
  "sl_points",
  "trailing_points",
  "lot_size",
  "strike_step",
  "ce_strike_offset",
  "pe_strike_offset",
];

const defaultInstruments = [
  {
    id: "sample-nifty-50",
    instrument: "NIFTY",
    index_scrip: "Nifty 50",
    contract_expiry: "09DEC2025",
    available_expiries: ["09DEC2025", "16DEC2025", "23DEC2025", "30DEC2025"],
    transaction: "BUY",
    strike_selection: "atm",
    trading_symbol: "",
    symbol_token: "",
    exchange: "NFO",
    lot_size: 75,
    no_of_lots: 1,
    pl_exit_lots: 1,
    premium_price: 200,
    pl_points: 45,
    sl_points: 35,
    trailing_points: 15,
    strike_step: 50,
    ce_strike_offset: 0,
    pe_strike_offset: 0,
    active: false,
    placeholder: true,
  },
  {
    id: "sample-nifty-bank",
    instrument: "BANKNIFTY",
    index_scrip: "Nifty Bank",
    contract_expiry: "30DEC2025",
    available_expiries: ["30DEC2025", "27JAN2026", "24FEB2026"],
    transaction: "BUY",
    strike_selection: "atm",
    trading_symbol: "",
    symbol_token: "",
    exchange: "NFO",
    lot_size: 35,
    no_of_lots: 1,
    pl_exit_lots: 1,
    premium_price: 500,
    pl_points: 50,
    sl_points: 50,
    trailing_points: 10,
    strike_step: 100,
    ce_strike_offset: 0,
    pe_strike_offset: 0,
    active: false,
    placeholder: true,
  },
  {
    id: "sample-sensex",
    instrument: "SENSEX",
    index_scrip: "Sensex",
    contract_expiry: "11DEC2025",
    available_expiries: ["11DEC2025", "18DEC2025", "24DEC2025", "01JAN2026"],
    transaction: "BUY",
    strike_selection: "atm",
    trading_symbol: "",
    symbol_token: "",
    exchange: "NFO",
    lot_size: 20,
    no_of_lots: 1,
    pl_exit_lots: 1,
    premium_price: 400,
    pl_points: 40,
    sl_points: 35,
    trailing_points: 12,
    strike_step: 100,
    ce_strike_offset: 0,
    pe_strike_offset: 0,
    active: false,
    placeholder: true,
  },
];

const formatNumberInputValue = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "";
  }
  return String(value);
};

const createDraftFromInstrument = (instrument) => ({
  index_scrip: instrument.index_scrip || "",
  contract_expiry: instrument.contract_expiry || "",
  transaction: instrument.transaction || "",
  strike_selection: instrument.strike_selection || "atm",
  trading_symbol: instrument.trading_symbol || "",
  symbol_token: instrument.symbol_token || "",
  exchange: instrument.exchange || "NFO",
  lot_size: formatNumberInputValue(instrument.lot_size),
  no_of_lots: formatNumberInputValue(instrument.no_of_lots),
  pl_exit_lots: formatNumberInputValue(instrument.pl_exit_lots),
  premium_price: formatNumberInputValue(instrument.premium_price),
  pl_points: formatNumberInputValue(instrument.pl_points),
  sl_points: formatNumberInputValue(instrument.sl_points),
  trailing_points: formatNumberInputValue(instrument.trailing_points),
  strike_step: formatNumberInputValue(instrument.strike_step),
  ce_strike_offset: formatNumberInputValue(instrument.ce_strike_offset),
  pe_strike_offset: formatNumberInputValue(instrument.pe_strike_offset),
  active: Boolean(instrument.active),
  placeholder: Boolean(instrument.placeholder),
});

const valuesAreEqual = (previousValue, nextValue) => {
  if (typeof previousValue === "boolean" || typeof nextValue === "boolean") {
    return Boolean(previousValue) === Boolean(nextValue);
  }

  const previousNormalized =
    previousValue === null || previousValue === undefined
      ? ""
      : String(previousValue);
  const nextNormalized =
    nextValue === null || nextValue === undefined ? "" : String(nextValue);

  return previousNormalized === nextNormalized;
};

const draftsAreIdentical = (currentDrafts, nextDrafts) => {
  const currentKeys = Object.keys(currentDrafts);
  const nextKeys = Object.keys(nextDrafts);

  if (currentKeys.length !== nextKeys.length) {
    return false;
  }

  for (const key of nextKeys) {
    if (!Object.prototype.hasOwnProperty.call(currentDrafts, key)) {
      return false;
    }

    const previousEntry = currentDrafts[key];
    const nextEntry = nextDrafts[key];

    if (!previousEntry || !nextEntry) {
      return false;
    }

    const fieldKeys = new Set([
      ...Object.keys(previousEntry),
      ...Object.keys(nextEntry),
    ]);

    for (const fieldKey of fieldKeys) {
      if (!valuesAreEqual(previousEntry[fieldKey], nextEntry[fieldKey])) {
        return false;
      }
    }
  }

  return true;
};

const columnDefinitions = [
  {
    key: "index_scrip",
    label: "Index Scrip",
    type: "text",
    readOnly: true,
  },
  {
    key: "contract_expiry",
    label: "Contract Expiry",
    type: "expiry-select",
    width: "160px",
  },
  {
    key: "transaction",
    label: "Transaction",
    type: "select",
    options: ["BUY", "SELL"],
  },
  {
    key: "no_of_lots",
    label: "No Of Lots",
    type: "number",
  },
  {
    key: "pl_exit_lots",
    label: "PL Exit Lots",
    type: "number",
  },
  {
    key: "premium_price",
    label: "Premium Price",
    type: "number",
  },
  {
    key: "pl_points",
    label: "PL Points",
    type: "number",
  },
  {
    key: "sl_points",
    label: "SL Points",
    type: "number",
  },
  {
    key: "trailing_points",
    label: "Trail Points",
    type: "number",
  },
];

export default function InstrumentsPage() {
  const dispatch = useDispatch();
  const { items, status, error, updatingId } = useSelector(
    (state) => state.instruments
  );
  const authUsername = getAuthUsername();

  const [drafts, setDrafts] = useState({});
  const [pendingInstrument, setPendingInstrument] = useState(null);
  const [errorDialogMessage, setErrorDialogMessage] = useState(null);

  const dataSource = useMemo(
    () => (items.length ? items : defaultInstruments),
    [items]
  );

  const setDraftValue = useCallback(
    (instrumentId, key, rawValue, shouldFlush = false) => {
      const normalizedValue = key === "active" ? Boolean(rawValue) : rawValue;

      const applyUpdate = () => {
        setDrafts((prev) => {
          const existingEntry = prev[instrumentId];
          const baseEntry =
            existingEntry ||
            createDraftFromInstrument(
              dataSource.find((item) => item.id === instrumentId) || {}
            );

          if (baseEntry && valuesAreEqual(baseEntry[key], normalizedValue)) {
            return prev;
          }

          return {
            ...prev,
            [instrumentId]: {
              ...baseEntry,
              [key]: normalizedValue,
            },
          };
        });
      };

      if (shouldFlush && typeof flushSync === "function") {
        flushSync(applyUpdate);
      } else {
        applyUpdate();
      }
    },
    [setDrafts, dataSource]
  );

  useEffect(() => {
    if (!authUsername) {
      return undefined;
    }

    const cacheEntry = getCacheEntry(INSTRUMENTS_CACHE_NAMESPACE, authUsername);
    if (cacheEntry?.value) {
      dispatch(hydrateInstrumentsFromCache(cacheEntry.value));
    }

    const age = cacheEntry
      ? Date.now() - cacheEntry.timestamp
      : Number.POSITIVE_INFINITY;

    const triggerFetch = () => {
      dispatch(fetchInstruments(authUsername));
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

  useEffect(() => {
    if (!dataSource.length) {
      setDrafts({});
      return;
    }

    const shape = dataSource.reduce((acc, instrument) => {
      acc[instrument.id] = createDraftFromInstrument(instrument);
      return acc;
    }, {});
    setDrafts((current) => {
      if (draftsAreIdentical(current, shape)) {
        return current;
      }
      return shape;
    });
  }, [dataSource]);

  const columns = useMemo(() => columnDefinitions, []);

  const handleFieldChange = (instrumentId, key, value) => {
    if (key === "index_scrip") {
      return;
    }
    const shouldFlush = key === "contract_expiry" || key === "transaction";
    setDraftValue(instrumentId, key, value, shouldFlush);
  };

  const handleToggleActive = (instrumentId) => {
    const currentActive = drafts[instrumentId]?.active;
    setDraftValue(instrumentId, "active", !currentActive);
  };

  const initiateUpdate = (instrument) => {
    if (instrument.placeholder) {
      return;
    }
    setPendingInstrument(instrument);
  };

  const runInstrumentUpdate = (instrument) => {
    if (!instrument || instrument.placeholder || !authUsername) {
      return;
    }

    const currentDraft = drafts[instrument.id];
    if (!currentDraft) {
      return;
    }

    const payload = { ...currentDraft };
    delete payload.index_scrip;
    delete payload.placeholder;
    numericFields.forEach((field) => {
      if (payload[field] !== "" && payload[field] !== null) {
        payload[field] = Number(payload[field]);
      }
    });

    dispatch(
      updateInstrument({
        id: instrument.id,
        username: authUsername,
        ...payload,
      })
    )
      .unwrap()
      .then((updatedInstrument) => {
        setDrafts((previousDrafts) => ({
          ...previousDrafts,
          [instrument.id]: createDraftFromInstrument(updatedInstrument),
        }));
      })
      .catch((message) => {
        setErrorDialogMessage(
          typeof message === "string"
            ? message
            : "Instrument not updated. Please try again."
        );
      });
  };

  const confirmPendingUpdate = () => {
    if (!pendingInstrument) {
      return;
    }
    const instrument = pendingInstrument;
    setPendingInstrument(null);
    runInstrumentUpdate(instrument);
  };

  const dismissPendingUpdate = () => {
    setPendingInstrument(null);
  };

  const closeErrorDialog = () => {
    setErrorDialogMessage(null);
  };

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold text-white">Instruments</h1>
        <p className="text-sm text-slate-400">
          Manage contract parameters and enable or disable each instrument for
          your trading strategy.
        </p>
      </header>

      {!authUsername ? (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          Sign in again to manage instruments.
        </div>
      ) : error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl shadow-black/30">
        <table className="w-full table-auto divide-y divide-slate-800 text-sm text-slate-100">
          <thead>
            <tr className="bg-slate-900/80 text-xs uppercase tracking-normal text-slate-400">
              <th className="w-16 whitespace-nowrap px-3 py-3 text-left">
                S.No
              </th>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className="whitespace-nowrap px-3 py-3 text-left"
                  style={
                    column.width
                      ? { width: column.width, minWidth: column.width }
                      : undefined
                  }
                >
                  {column.label}
                </th>
              ))}
              <th className="w-20 whitespace-nowrap px-2 py-3 text-left">
                Active
              </th>
              <th className="w-24 whitespace-nowrap px-2 py-3 text-left">
                Update
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {status === "loading" ? (
              <tr>
                <td
                  colSpan={columns.length + 2}
                  className="px-4 py-8 text-center text-sm text-slate-400"
                >
                  Loading instruments...
                </td>
              </tr>
            ) : !dataSource.length ? (
              <tr>
                <td
                  colSpan={columns.length + 2}
                  className="px-4 py-8 text-center text-sm text-slate-400"
                >
                  No instruments configured yet.
                </td>
              </tr>
            ) : (
              dataSource.map((instrument, index) => {
                const draft = drafts[instrument.id];
                return (
                  <tr key={instrument.id} className="text-sm text-slate-100">
                    <td className="w-16 whitespace-nowrap px-3 py-3 text-left align-middle text-xs text-slate-400">
                      {index + 1}
                    </td>
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className="whitespace-nowrap px-3 py-3 text-left align-middle"
                        style={
                          column.width
                            ? { width: column.width, minWidth: column.width }
                            : undefined
                        }
                      >
                        {column.readOnly ? (
                          <div className="flex h-9 w-full items-center justify-start rounded-lg bg-transparent px-2 text-sm font-medium text-slate-100">
                            {draft?.[column.key] || "—"}
                          </div>
                        ) : column.type === "expiry-select" ? (
                          <div className="relative" style={{ width: "100%" }}>
                            <select
                              value={draft?.[column.key] ?? ""}
                              onChange={(event) =>
                                handleFieldChange(
                                  instrument.id,
                                  column.key,
                                  event.target.value
                                )
                              }
                              className="h-9 w-full appearance-none rounded-lg border border-slate-700 bg-slate-900/70 px-3 pr-8 text-left text-sm text-white focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                              disabled={
                                !(instrument.available_expiries || []).length
                              }
                            >
                              {(instrument.available_expiries || [])
                                .length ? null : (
                                <option value="">No expiries</option>
                              )}
                              {(instrument.available_expiries || []).map(
                                (option) => (
                                  <option key={option} value={option}>
                                    {option}
                                  </option>
                                )
                              )}
                            </select>
                            <span className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-slate-400">
                              <svg
                                aria-hidden="true"
                                className="h-3 w-3"
                                viewBox="0 0 12 12"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                              >
                                <path
                                  d="M2 4.5L6 8.5L10 4.5"
                                  stroke="currentColor"
                                  strokeWidth="1.5"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                />
                              </svg>
                            </span>
                          </div>
                        ) : column.type === "select" ? (
                          <div className="relative" style={{ width: "100%" }}>
                            <select
                              value={draft?.[column.key] ?? ""}
                              onChange={(event) =>
                                handleFieldChange(
                                  instrument.id,
                                  column.key,
                                  event.target.value
                                )
                              }
                              className="h-9 w-full appearance-none rounded-lg border border-slate-700 bg-slate-900/70 px-3 pr-8 text-left text-sm text-white focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                            >
                              {column.options?.map((option) => {
                                const value =
                                  typeof option === "string"
                                    ? option
                                    : option.value;
                                const label =
                                  typeof option === "string"
                                    ? option
                                    : option.label || option.value;
                                return (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                );
                              })}
                            </select>
                            <span className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-slate-400">
                              <svg
                                aria-hidden="true"
                                className="h-3 w-3"
                                viewBox="0 0 12 12"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                              >
                                <path
                                  d="M2 4.5L6 8.5L10 4.5"
                                  stroke="currentColor"
                                  strokeWidth="1.5"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                />
                              </svg>
                            </span>
                          </div>
                        ) : (
                          <input
                            type={column.type}
                            value={draft?.[column.key] ?? ""}
                            onChange={(event) =>
                              handleFieldChange(
                                instrument.id,
                                column.key,
                                event.target.value
                              )
                            }
                            inputMode={
                              column.type === "number" ? "decimal" : undefined
                            }
                            step={column.type === "number" ? "any" : undefined}
                            className="h-9 w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 text-left text-sm text-white focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                          />
                        )}
                      </td>
                    ))}
                    <td className="w-20 whitespace-nowrap px-2 py-3 text-left align-middle">
                      <button
                        type="button"
                        onClick={() => handleToggleActive(instrument.id)}
                        className={`inline-flex h-6 w-11 items-center rounded-full border border-transparent px-1 transition ${
                          draft?.active
                            ? "justify-end bg-emerald-500/30"
                            : "justify-start bg-slate-700/80"
                        }`}
                      >
                        <span className="h-4 w-4 rounded-full bg-white/90" />
                      </button>
                    </td>
                    <td className="w-24 whitespace-nowrap px-2 py-3 text-left align-middle">
                      <button
                        type="button"
                        onClick={() => initiateUpdate(instrument)}
                        disabled={
                          updatingId === instrument.id || instrument.placeholder
                        }
                        className="flex h-9 w-full items-center justify-center rounded-lg bg-brand-500 px-4 text-sm font-semibold text-white shadow-lg shadow-brand-500/30 transition hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-slate-600"
                      >
                        Update
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {pendingInstrument ? (
        <Modal
          title="Confirm Update"
          onClose={dismissPendingUpdate}
          footer={
            <>
              <button
                type="button"
                onClick={dismissPendingUpdate}
                className="rounded-lg border border-slate-600 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmPendingUpdate}
                className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-brand-500/40 transition hover:bg-brand-400"
              >
                Update
              </button>
            </>
          }
        >
          <div className="flex h-full flex-col justify-between text-slate-200">
            <p className="text-sm">
              Update settings for
              <span className="mx-1 font-semibold text-white">
                {pendingInstrument.index_scrip || "this instrument"}
              </span>
              using the current values?
            </p>
            <p className="text-xs text-slate-400">
              Changes will overwrite the stored configuration immediately.
            </p>
          </div>
        </Modal>
      ) : null}
      {errorDialogMessage ? (
        <Modal
          title="Update Failed"
          onClose={closeErrorDialog}
          footer={
            <button
              type="button"
              onClick={closeErrorDialog}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-brand-500/40 transition hover:bg-brand-400"
            >
              Close
            </button>
          }
        >
          <div className="flex h-full flex-col justify-between text-slate-200">
            <p className="text-sm">
              {errorDialogMessage ||
                "Instrument not updated. Please try again."}
            </p>
            <p className="text-xs text-slate-400">
              Verify your inputs and network connection before retrying.
            </p>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
