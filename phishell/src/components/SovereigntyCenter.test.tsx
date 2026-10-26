import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SovereigntyCenter } from "./SovereigntyCenter";

describe("sovereignty center", () => {
  it("does not pretend that a local checklist is an OS attestation", () => {
    const html = renderToStaticMarkup(<SovereigntyCenter />);
    expect(html).toContain("OVERALL: UNVERIFIED");
    expect(html).toContain("not independently verified");
    expect(html).toContain("The backup is NOT encrypted");
    expect(html).toContain("Download my checklist JSON");
    expect(html.match(/NOT END-TO-END VERIFIED/g)).toHaveLength(7);
  });
});
