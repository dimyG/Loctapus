import { useDispatch, useSelector } from "react-redux";
import type { AppDispatch, RootState } from "./store";

/** Dispatch hook typed to the app's store, so thunks and action creators type-check. */
export const useAppDispatch = useDispatch.withTypes<AppDispatch>();

/** Selector hook typed to {@link RootState}, so selections need no manual typing. */
export const useAppSelector = useSelector.withTypes<RootState>();
