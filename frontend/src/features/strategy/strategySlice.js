import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import apiClient from "../../utils/axiosConfig.js";

export const fetchStrategies = createAsyncThunk(
  "strategy/fetchStrategies",
  async (_, thunkAPI) => {
    try {
      const response = await apiClient.get(`/strategies/`);
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
      const response = await apiClient.post(`/strategies/`, payload);
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
