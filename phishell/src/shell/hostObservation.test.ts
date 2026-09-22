import { describe, expect, it } from "vitest";
import {
  FIXTURE_HOST_OBSERVATION,
  createFixtureObservationProvider,
} from "./hostObservation";

describe("host observation contract", () => {
  it("keeps read-only observation separate from execution authority", async () => {
    const provider = createFixtureObservationProvider();
    const snapshot = await provider.observe();

    expect(provider.readOnly).toBe(true);
    expect(provider.executionAuthority).toBe(false);
    expect(snapshot.readOnly).toBe(true);
    expect(snapshot.executionAuthority).toBe(false);
    expect(snapshot.effectPerformed).toBe(false);
    expect(snapshot.source).toBe("fixture");
  });

  it("does not model network addresses or MAC values in the shell contract", () => {
    for (const network of FIXTURE_HOST_OBSERVATION.network) {
      expect(Object.keys(network).sort()).toEqual(["families", "internal", "name"]);
    }
  });

  it("does not claim service-status binding", () => {
    expect(FIXTURE_HOST_OBSERVATION.init.serviceStatusBound).toBe(false);
  });
});
