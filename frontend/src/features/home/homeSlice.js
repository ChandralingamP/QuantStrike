import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import apiClient from "../../utils/axiosConfig.js";
import { setCacheEntry } from "../../utils/dataCache.js";

const HOME_CACHE_NAMESPACE = "home_status";

const mapConnectionStatus = (state) => {
  switch ((state || "").toLowerCase()) {
    case "connected":
      return "succeeded";
    case "failed":
      return "failed";
    default:
      return "idle";
  }
};

const applyAccountStatus = (state, payload) => {
  state.status = "succeeded";
  state.details = payload;
  state.connection.status = mapConnectionStatus(payload?.connection_state);
  state.connection.message =
    state.connection.status === "failed"
      ? payload?.connection_message || "Unable to validate session"
      : null;
  state.connection.lastConnectedAt =
    payload?.last_connected_at || state.connection.lastConnectedAt;
};

export const fetchAccountStatus = createAsyncThunk(
  "home/fetchAccountStatus",
  async (username, thunkAPI) => {
    if (!username) {
      return thunkAPI.rejectWithValue(
        "Username is required to load account status"
      );
    }
    try {
      const response = await apiClient.get(`/home/status/`, {
        params: { username },
      });
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || "Unable to load account status"
      );
    }
  }
);

export const connectBrokerage = createAsyncThunk(
  "home/connectBrokerage",
  async ({ username, mpin, totp }, thunkAPI) => {
    if (!username) {
      return thunkAPI.rejectWithValue("Username is required to connect");
    }
    try {
      const response = await apiClient.post(`/home/connect/`, {
        username,
        mpin,
        totp,
      });
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || "Unable to connect to brokerage"
      );
    }
  }
);

const initialState = {
  details: null,
  status: "idle",
  error: null,
  connection: {
    status: "idle",
    message: null,
    lastConnectedAt: null,
  },
};

const homeSlice = createSlice({
  name: "home",
  initialState,
  reducers: {
    hydrateFromCache: (state, action) => {
      applyAccountStatus(state, action.payload);
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchAccountStatus.pending, (state) => {
        state.status = state.details ? "refreshing" : "loading";
        state.error = null;
      })
      .addCase(fetchAccountStatus.fulfilled, (state, action) => {
        applyAccountStatus(state, action.payload);
        const username = action.meta.arg;
        if (username) {
          setCacheEntry(HOME_CACHE_NAMESPACE, username, action.payload);
        }
      })
      .addCase(fetchAccountStatus.rejected, (state, action) => {
        state.status = state.details ? "succeeded" : "failed";
        state.error = action.payload;
        if (!state.details) {
          state.connection.status = "idle";
          state.connection.message = null;
        }
      })
      .addCase(connectBrokerage.pending, (state) => {
        state.connection.status = "loading";
        state.connection.message = null;
      })
      .addCase(connectBrokerage.fulfilled, (state, action) => {
        state.connection.status = "succeeded";
        state.connection.message = action.payload?.message || "Connected";
        state.connection.lastConnectedAt =
          action.payload?.last_connected_at || new Date().toISOString();
        if (action.payload?.details) {
          state.details = action.payload.details;
        }
        const username = action.meta.arg?.username;
        const detailsToPersist =
          action.payload?.details || state.details || null;
        if (username && detailsToPersist) {
          setCacheEntry(HOME_CACHE_NAMESPACE, username, detailsToPersist);
        }
      })
      .addCase(connectBrokerage.rejected, (state, action) => {
        state.connection.status = "failed";
        state.connection.message = action.payload;
      });
  },
});

export const { hydrateFromCache } = homeSlice.actions;

export default homeSlice.reducer;
