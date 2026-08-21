import { beforeEach, describe, expect, it, vi } from "vitest";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("novel-video API session recovery", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it("renews an expired session and retries the original request once", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse(403, { detail: { code: "session_expired", message: "expired" } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse(200, { id: "project-1" }));
    vi.stubGlobal("fetch", fetchMock);
    const { request } = await import("./client");

    await expect(request("/core/novel-video/projects/project-1")).resolves.toEqual({ id: "project-1" });
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/core/novel-video/session",
      "/api/core/novel-video/projects/project-1",
      "/api/core/novel-video/session",
      "/api/core/novel-video/projects/project-1",
    ]);
  });

  it("does not renew for an unrelated forbidden response", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse(403, { detail: { code: "forbidden", message: "no" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { ApiError, request } = await import("./client");

    await expect(request("/core/novel-video/projects/project-1")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not loop when the retried request still requires a session", async () => {
    const sessionRequired = () => jsonResponse(403, { detail: { code: "session_required", message: "required" } });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(sessionRequired())
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(sessionRequired());
    vi.stubGlobal("fetch", fetchMock);
    const { ApiError, request } = await import("./client");

    await expect(request("/core/novel-video/projects/project-1")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
