// Runs before every test file: registers jest-dom matchers, then starts the
// MSW server that intercepts fetch calls to the API base URL. Per-test handler
// overrides are reset by afterEach; the server shuts down after all files.
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
