import { describe, expect, it } from "vitest";

import {
  apiCacheKeyForTest,
  RECOMMENDATION_RESPONSE_SCHEMA_VERSION
} from "@/lib/api";

describe("API cache keys", () => {
  it("includes the split recommendation schema version in Discover cache keys", () => {
    const key = apiCacheKeyForTest(
      "GET",
      "/recommendations/sections?style=balanced&limit=10"
    );

    expect(key).toContain(`schema=${RECOMMENDATION_RESPONSE_SCHEMA_VERSION}`);
    expect(key).toContain("/recommendations/sections");
  });

  it("does not add recommendation schema markers to unrelated GET cache keys", () => {
    expect(apiCacheKeyForTest("GET", "/books")).toBe("GET:/books");
  });
});
