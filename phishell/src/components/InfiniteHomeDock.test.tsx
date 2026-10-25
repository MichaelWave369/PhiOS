import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HOME_DOORWAYS, InfiniteHomeDock } from "./InfiniteHomeDock";

describe("PhiOS Home operator-only doorway", () => {
  it("is limited to two fixed, operator-opened destinations", () => {
    expect(HOME_DOORWAYS.map((door) => door.id)).toEqual(["porch", "commons"]);
    expect(HOME_DOORWAYS[0].href).toBe("http://127.0.0.1:7331/");
    expect(HOME_DOORWAYS[1].href).toBe("https://michaelwave369.github.io/Infinite-Commons/");
    for (const door of HOME_DOORWAYS) {
      expect(door.href).not.toContain("@");
      expect(door.href).not.toMatch(/[?#]/);
    }
  });

  it("marks real health, installation, and authority as unverified", () => {
    const html = renderToStaticMarkup(<InfiniteHomeDock />);
    expect(html).toContain("NOT OBSERVED");
    expect(html).toContain("NOT INSTALLED");
    expect(html).toContain("no account, model, file, network, or execution rights");
    expect(html).toContain("No endpoint probe or background network request");
    expect(html).toContain('target="_blank"');
    expect((html.match(/rel="noopener noreferrer"/g) ?? []).length).toBe(2);
    expect((html.match(/<a /g) ?? []).length).toBe(2);
    expect(html).not.toContain("<iframe");
    expect(html).not.toContain("<form");
  });
});
