import { configureStore } from "@reduxjs/toolkit";
import deviationReducer from "./features/deviationSlice";

export const store = configureStore({
  reducer: { deviation: deviationReducer },
  middleware: (getDefault) =>
    getDefault({
      // An uploaded File is passed as a thunk argument (never stored in state) - allow it in action meta.
      serializableCheck: { ignoredActionPaths: ["meta.arg.file"] },
    }),
});
