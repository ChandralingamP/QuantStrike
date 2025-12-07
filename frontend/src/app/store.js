import { configureStore } from "@reduxjs/toolkit";
import homeReducer from "../features/home/homeSlice";
import instrumentsReducer from "../features/instruments/instrumentsSlice";
import pnlReducer from "../features/pnl/pnlSlice";
import algoReducer from "../features/algo/algoSlice";

export const store = configureStore({
  reducer: {
    home: homeReducer,
    instruments: instrumentsReducer,
    pnl: pnlReducer,
    algo: algoReducer,
  },
});
