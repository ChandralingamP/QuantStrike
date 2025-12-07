import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import axios from "axios";
import { getAuthUsername } from "../../utils/authCookies.js";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

const extractErrorMessage = (errorPayload) => {
  if (!errorPayload) {
    return "An unexpected error occurred.";
  }
  if (typeof errorPayload === "string") {
    return errorPayload;
  }
  if (typeof errorPayload === "object") {
    if (errorPayload.detail) {
      return errorPayload.detail;
    }
    return Object.entries(errorPayload)
      .map(([key, value]) => {
        if (Array.isArray(value)) {
          return `${key}: ${value.join(", ")}`;
        }
        return `${key}: ${value}`;
      })
      .join("; ");
  }
  return String(errorPayload);
};

export const fetchAlgoConfig = createAsyncThunk(
  "algo/fetchConfig",
  async (_, thunkAPI) => {
    try {
      const username = getAuthUsername();
      if (!username) {
        return thunkAPI.rejectWithValue(
          "Username is not available. Please sign in again."
        );
      }
      const response = await axios.get(`${API_BASE_URL}/algo/config`, {
        params: { username },
      });
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || "Unable to load algo configuration"
      );
    }
  }
);

export const updateAlgoConfig = createAsyncThunk(
  "algo/updateConfig",
  async (updates, thunkAPI) => {
    try {
      const username = getAuthUsername();
      if (!username) {
        return thunkAPI.rejectWithValue(
          "Username is not available. Please sign in again."
        );
      }
      const payload = {
        ...updates,
        username,
      };
      const response = await axios.put(`${API_BASE_URL}/algo/config`, payload, {
        params: { username },
      });
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data || "Unable to update algo configuration"
      );
    }
  }
);

const initialState = {
  config: null,
  status: "idle",
  error: null,
  updating: false,
  updateError: null,
};

const algoSlice = createSlice({
  name: "algo",
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchAlgoConfig.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchAlgoConfig.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.config = action.payload;
      })
      .addCase(fetchAlgoConfig.rejected, (state, action) => {
        state.status = "failed";
        state.error = extractErrorMessage(
          action.payload || action.error?.message
        );
      })
      .addCase(updateAlgoConfig.pending, (state) => {
        state.updating = true;
        state.updateError = null;
      })
      .addCase(updateAlgoConfig.fulfilled, (state, action) => {
        state.updating = false;
        state.config = action.payload;
      })
      .addCase(updateAlgoConfig.rejected, (state, action) => {
        state.updating = false;
        state.updateError = extractErrorMessage(
          action.payload || action.error?.message
        );
      });
  },
});

export default algoSlice.reducer;
