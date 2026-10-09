import { http, HttpResponse } from "msw";

/**
 * Baseline MSW handlers mirroring the S1 contract. Tests override individual
 * endpoints with server.use(...); values here are stable fixtures that later
 * tasks assert against (t-register, t-login, u-1, w-1, t-1).
 */
export const handlers = [
  http.post("*/auth/register", () =>
    HttpResponse.json({ access_token: "t-register", token_type: "bearer" }, { status: 201 }),
  ),
  http.post("*/auth/login", () =>
    HttpResponse.json({ access_token: "t-login", token_type: "bearer" }, { status: 200 }),
  ),
  http.post("*/auth/logout", () => new HttpResponse(null, { status: 204 })),
  http.get("*/users/me", () => HttpResponse.json({ user_id: "u-1", email: "user@example.test" })),
  http.get("*/projects", () => HttpResponse.json([])),
  http.post("*/projects", async ({ request }) => {
    const body = (await request.json()) as { name: string; team_id: string };
    return HttpResponse.json(
      { id: "p-new", name: body.name, is_public: false, created_at: "2026-10-09T12:00:00Z" },
      { status: 201 },
    );
  }),
  http.get("*/workspaces", () => HttpResponse.json([{ id: "w-1", name: "Default" }])),
  http.get("*/workspaces/w-1/teams", () =>
    HttpResponse.json([{ id: "t-1", name: "Default", workspace_id: "w-1" }]),
  ),
];
