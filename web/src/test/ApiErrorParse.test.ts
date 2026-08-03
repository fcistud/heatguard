import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../api";

describe("ApiError parse_error", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("raises typed parse_error when success-path JSON is invalid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => {
          throw new SyntaxError("Unexpected token");
        },
      }),
    );

    await expect(api.sites()).rejects.toEqual(
      expect.objectContaining({
        name: "ApiError",
        kind: "parse_error",
        status: 200,
      }),
    );
  });

  it("keeps http kind for non-OK responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: "Unavailable",
        json: async () => ({ detail: "down" }),
      }),
    );

    try {
      await api.sites();
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).kind).toBe("http");
      expect((e as ApiError).status).toBe(503);
    }
  });
});
