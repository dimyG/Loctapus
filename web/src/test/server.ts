import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/** The MSW server every unit test file shares; lifecycle lives in setup.ts. */
export const server = setupServer(...handlers);
