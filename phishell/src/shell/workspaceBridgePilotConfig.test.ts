import { describe, expect, it } from "vitest";
import { reviewPhiOfficePilotEndpoint } from "./workspaceBridgePilotConfig";

describe("PhiOffice pilot endpoint gate", () => {
  const host = "http://localhost:5173";
  it("is disabled unless the operator explicitly configures URL and expected origin", () => {
    expect(reviewPhiOfficePilotEndpoint(undefined, undefined, host)).toBeNull();
    expect(reviewPhiOfficePilotEndpoint("http://localhost:5174/", undefined, host)).toBeNull();
    expect(reviewPhiOfficePilotEndpoint(undefined, "http://localhost:5174", host)).toBeNull();
  });
  it("accepts exact, different-origin HTTPS or loopback endpoints only", () => {
    expect(reviewPhiOfficePilotEndpoint("http://localhost:5174/", "http://localhost:5174", host))
      .toEqual({ url: "http://localhost:5174/", origin: "http://localhost:5174" });
    expect(reviewPhiOfficePilotEndpoint("https://office.example.test/app", "https://office.example.test", host))
      .toEqual({ url: "https://office.example.test/app", origin: "https://office.example.test" });
  });
  it("rejects unrelated, same-origin, insecure, redirected or credentialed candidates", () => {
    for (const [url, origin] of [
      ["http://localhost:5173/", host],
      ["http://office.example.test/", "http://office.example.test"],
      ["https://evil.example.test/", "https://office.example.test"],
      ["https://user:pass@office.example.test/", "https://office.example.test"],
      ["https://office.example.test/app?token=abc", "https://office.example.test"],
      ["https://office.example.test/app#fragment", "https://office.example.test"],
    ]) {
      expect(reviewPhiOfficePilotEndpoint(url, origin, host)).toBeNull();
    }
  });
});
