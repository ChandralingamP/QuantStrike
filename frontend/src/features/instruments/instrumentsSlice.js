import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import apiClient from "../../utils/axiosConfig.js";
import { setCacheEntry } from "../../utils/dataCache.js";

const INSTRUMENTS_CACHE_NAMESPACE = "instruments";

export const fetchInstruments = createAsyncThunk(
  "instruments/fetchInstruments",
  async (username, thunkAPI) => {
    if (!username) {
      return thunkAPI.rejectWithValue(
        "Username is required to load instruments"
      );
    }
    try {
      const response = await apiClient.get(`/instruments/`, {
        params: { username },
      });
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || "Unable to load instruments"
      );
    }
  }
);

export const updateInstrument = createAsyncThunk(
  "instruments/updateInstrument",
  async ({ id, username, ...updates }, thunkAPI) => {
    if (!username) {
      return thunkAPI.rejectWithValue(
        "Username is required to update instrument"
      );
    }
    try {
      const response = await apiClient.put(`/instruments/${id}/`, updates, {
        params: { username },
      });
      return response.data;
    } catch (error) {
      const payload = error.response?.data;
      return thunkAPI.rejectWithValue(
        payload?.detail || payload || "Unable to update instrument"
      );
    }
  }
);

const initialState = {
  items: [],
  status: "idle",
  error: null,
  updatingId: null,
  updateError: null,
};

const instrumentsSlice = createSlice({
  name: "instruments",
  initialState,
  reducers: {
    hydrateFromCache: (state, action) => {
      state.items = Array.isArray(action.payload) ? action.payload : [];
      state.status = "succeeded";
      state.error = null;
      state.updateError = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchInstruments.pending, (state) => {
        state.status = state.items.length ? "refreshing" : "loading";
        state.error = null;
      })
      .addCase(fetchInstruments.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
        const username = action.meta.arg;
        if (username) {
          setCacheEntry(INSTRUMENTS_CACHE_NAMESPACE, username, state.items);
        }
      })
      .addCase(fetchInstruments.rejected, (state, action) => {
        state.status = state.items.length ? "succeeded" : "failed";
        state.error = action.payload;
      })
      .addCase(updateInstrument.pending, (state, action) => {
        state.updatingId = action.meta.arg.id;
        state.updateError = null;
      })
      .addCase(updateInstrument.fulfilled, (state, action) => {
        state.updatingId = null;
        const index = state.items.findIndex(
          (instrument) => instrument.id === action.payload.id
        );
        if (index !== -1) {
          state.items[index] = action.payload;
        }
        const username = action.meta.arg.username;
        if (username) {
          setCacheEntry(INSTRUMENTS_CACHE_NAMESPACE, username, state.items);
        }
      })
      .addCase(updateInstrument.rejected, (state, action) => {
        state.updateError = action.payload;
        state.updatingId = null;
      });
  },
});

export const { hydrateFromCache } = instrumentsSlice.actions;

export default instrumentsSlice.reducer;
