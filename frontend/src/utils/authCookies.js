const COOKIE_NAME = "qs_username";
const SESSION_TIMEOUT_MINUTES = 15;
export const SESSION_TIMEOUT_MS = SESSION_TIMEOUT_MINUTES * 60 * 1000;
const SESSION_TIMEOUT_SECONDS = Math.floor(SESSION_TIMEOUT_MS / 1000);
const LAST_ACTIVE_KEY = "quantstrike_last_active";
const USER_ROLE_KEY = "quantstrike_is_superuser";
const USER_STAFF_KEY = "quantstrike_is_staff";
let lastCookieRefresh = 0;

const buildCookieValue = (username) =>
  `${COOKIE_NAME}=${encodeURIComponent(
    username
  )}; Max-Age=${SESSION_TIMEOUT_SECONDS}; Path=/; SameSite=Lax`;

const readCookieUsername = () => {
  if (typeof document === "undefined") {
    return null;
  }
  const cookies = document.cookie ? document.cookie.split(";") : [];
  for (const cookie of cookies) {
    const [rawKey, ...rest] = cookie.trim().split("=");
    if (rawKey === COOKIE_NAME) {
      return decodeURIComponent(rest.join("="));
    }
  }
  return null;
};

const persistLastActive = () => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(LAST_ACTIVE_KEY, String(Date.now()));
  } catch (error) {
    // ignore storage failures
  }
};

const persistUserRole = (isSuperuser) => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(USER_ROLE_KEY, isSuperuser ? "1" : "0");
  } catch (error) {
    // ignore storage failures
  }
};

const removeUserRole = () => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(USER_ROLE_KEY);
  } catch (error) {
    // ignore storage failures
  }
};

const persistStaffRole = (isStaff) => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(USER_STAFF_KEY, isStaff ? "1" : "0");
  } catch (error) {
    // ignore storage failures
  }
};

const removeStaffRole = () => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(USER_STAFF_KEY);
  } catch (error) {
    // ignore storage failures
  }
};

const readLastActive = () => {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const stored = window.localStorage.getItem(LAST_ACTIVE_KEY);
    return stored ? Number(stored) : null;
  } catch (error) {
    return null;
  }
};

const refreshSessionCookie = () => {
  const username = readCookieUsername();
  if (!username) {
    return;
  }
  const now = Date.now();
  if (now - lastCookieRefresh < 30000) {
    return;
  }
  if (typeof document !== "undefined") {
    document.cookie = buildCookieValue(username);
    lastCookieRefresh = now;
  }
};

export const markSessionActive = () => {
  if (!readCookieUsername()) {
    return;
  }
  persistLastActive();
  refreshSessionCookie();
};

export const setAuthUsername = (username, options = {}) => {
  if (!username || typeof document === "undefined") {
    return;
  }
  document.cookie = buildCookieValue(username);
  lastCookieRefresh = Date.now();
  persistLastActive();
  if (Object.prototype.hasOwnProperty.call(options, "isSuperuser")) {
    persistUserRole(Boolean(options.isSuperuser));
  }
  if (Object.prototype.hasOwnProperty.call(options, "isStaff")) {
    persistStaffRole(Boolean(options.isStaff));
  }
};

export const setUserRole = (isSuperuser) => {
  persistUserRole(Boolean(isSuperuser));
};

export const setUserIsStaff = (isStaff) => {
  persistStaffRole(Boolean(isStaff));
};

export const hasSessionExpired = () => {
  const lastActive = readLastActive();
  if (lastActive === null) {
    return false;
  }
  return Date.now() - lastActive >= SESSION_TIMEOUT_MS;
};

export const getAuthUsername = () => {
  const username = readCookieUsername();
  if (!username) {
    clearAuthUsername();
    return null;
  }
  if (hasSessionExpired()) {
    clearAuthUsername();
    return null;
  }
  return username;
};

export const getUserRole = () => {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const stored = window.localStorage.getItem(USER_ROLE_KEY);
    if (stored === null) {
      return null;
    }
    return stored === "1";
  } catch (error) {
    return null;
  }
};

export const getUserIsStaff = () => {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const stored = window.localStorage.getItem(USER_STAFF_KEY);
    if (stored === null) {
      return null;
    }
    return stored === "1";
  } catch (error) {
    return null;
  }
};

export const clearAuthUsername = () => {
  if (typeof document !== "undefined") {
    document.cookie = `${COOKIE_NAME}=; Max-Age=0; Path=/; SameSite=Lax`;
  }
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(LAST_ACTIVE_KEY);
      window.localStorage.removeItem(USER_ROLE_KEY);
      window.localStorage.removeItem(USER_STAFF_KEY);
    } catch (error) {
      // ignore storage failures
    }
  }
  lastCookieRefresh = 0;
};
