import { describe, expect, it } from "vitest";
import {
  claimClassFor,
  createNode,
  createPromotionProposal,
  createReturnPointer,
  normalizeTags,
  relatedSeeds,
} from "./symbolLab";

const at = "2026-09-25T20:00:00.000Z";

describe("Symbol Lab contracts", () => {
  it("maps artifact kinds to explicit claim classes", () => {
    expect(claimClassFor("symbol")).toBe("non_claim");
    expect(claimClassFor("question")).toBe("open_question");
    expect(claimClassFor("hypothesis")).toBe("hypothesis");
    expect(claimClassFor("association")).toBe("unverified_association");
  });

  it("creates zero-authority session nodes", () => {
    const node = createNode({
      id: "n1",
      kind: "creative_seed",
      title: "Nested bubble gear",
      content: "Explore the symbol without asserting physics.",
      createdAt: at,
    });

    expect(node.operationalAuthority).toBe(false);
    expect(node.actionAuthority).toBe(false);
    expect(node.executionAuthority).toBe(false);
  });

  it("normalizes tags deterministically", () => {
    expect(normalizeTags(" Gear, rhythm,GEAR, water ")).toEqual([
      "gear",
      "rhythm",
      "water",
    ]);
  });

  it("keeps promotion as proposal_only with no authority", () => {
    const proposal = createPromotionProposal({
      id: "p1",
      nodeId: "n1",
      target: "research",
      createdAt: at,
    });

    expect(proposal.status).toBe("proposal_only");
    expect(proposal.operationalAuthority).toBe(false);
    expect(proposal.actionAuthority).toBe(false);
    expect(proposal.executionAuthority).toBe(false);
  });

  it("keeps return pointers zero-authority", () => {
    const pointer = createReturnPointer({
      id: "r1",
      nodeId: "n1",
      prompt: "Return to the relationship between rhythm and recursion.",
      createdAt: at,
    });

    expect(pointer.operationalAuthority).toBe(false);
    expect(pointer.actionAuthority).toBe(false);
    expect(pointer.executionAuthority).toBe(false);
  });

  it("prefers explicit lineage and shared tags without stop-word noise", () => {
    const root = createNode({
      id: "root",
      kind: "symbol",
      title: "Nested bubble gear",
      content: "Recursive structure and timing.",
      tags: ["gear", "recursion"],
      createdAt: at,
    });
    const child = createNode({
      id: "child",
      kind: "question",
      title: "Could gear timing make rhythm?",
      content: "Explore timing as a musical metaphor.",
      tags: ["gear", "rhythm"],
      parentIds: ["root"],
      createdAt: at,
    });
    const unrelated = createNode({
      id: "other",
      kind: "creative_seed",
      title: "Neighborhood BBS",
      content: "A community network for local communication.",
      tags: ["bbs", "network"],
      createdAt: at,
    });

    const related = relatedSeeds(root, [root, child, unrelated]);

    expect(related[0].node.id).toBe("child");
    expect(related[0].reasons).toContain("direct child");
    expect(related.some((item) => item.node.id === "other")).toBe(false);
  });
});
