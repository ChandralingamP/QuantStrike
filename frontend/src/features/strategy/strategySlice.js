import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

export const fetchStrategies = createAsyncThunk(
  "strategy/fetchStrategies",
  async (_, thunkAPI) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/strategies/`);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || "Unable to fetch strategies"
      );
    }
  }
);

export const createStrategy = createAsyncThunk(
  "strategy/createStrategy",
  async (payload, thunkAPI) => {
    try {
      const response = await axios.post(`${API_BASE_URL}/strategies/`, payload);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data || "Unable to create strategy"
      );
    }
  }
);

const strategySlice = createSlice({
  name: "strategy",
  initialState: {
    items: [],
    status: "idle",
    error: null,
    lastCreated: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchStrategies.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchStrategies.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchStrategies.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload;
      })
      .addCase(createStrategy.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(createStrategy.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items.unshift(action.payload);
        state.lastCreated = action.payload;
      })
      .addCase(createStrategy.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload;
      });
  },
});

export default strategySlice.reducer;
