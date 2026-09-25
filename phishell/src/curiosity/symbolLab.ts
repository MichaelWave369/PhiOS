export type SymbolKind =
  | "symbol"
  | "metaphor"
  | "question"
  | "hypothesis"
  | "association"
  | "pattern"
  | "dream_fragment"
  | "creative_seed";

export type ClaimClass =
  | "non_claim"
  | "open_question"
  | "hypothesis"
  | "unverified_association";

export type PromotionTarget = "research" | "build" | "ledger_review";

export interface SymbolLabNode {
  id: string;
  kind: SymbolKind;
  claimClass: ClaimClass;
  title: string;
  content: string;
  tags: string[];
  parentIds: string[];
  createdAt: string;
  returnPointers: ReturnPointer[];
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
}

export interface ReturnPointer {
  id: string;
  nodeId: string;
  prompt: string;
  context: string;
  createdAt: string;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
}

export interface PromotionProposal {
  id: string;
  nodeId: string;
  target: PromotionTarget;
  status: "proposal_only";
  createdAt: string;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
}

export interface RelatedSeed {
  node: SymbolLabNode;
  score: number;
  reasons: string[];
}

const STOPWORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "by",
  "for",
  "from",
  "in",
  "is",
  "it",
  "of",
  "on",
  "or",
  "that",
  "the",
  "this",
  "to",
  "with",
]);

const claimClassByKind: Record<SymbolKind, ClaimClass> = {
  symbol: "non_claim",
  metaphor: "non_claim",
  question: "open_question",
  hypothesis: "hypothesis",
  association: "unverified_association",
  pattern: "unverified_association",
  dream_fragment: "non_claim",
  creative_seed: "non_claim",
};

export function claimClassFor(kind: SymbolKind): ClaimClass {
  return claimClassByKind[kind];
}

function tokens(value: string): Set<string> {
  return new Set(
    value
      .toLowerCase()
      .match(/[a-z0-9]+(?:[_-][a-z0-9]+)*/g)
      ?.filter((token) => token.length > 2 && !STOPWORDS.has(token)) ?? [],
  );
}

export function normalizeTags(raw: string): string[] {
  return [...new Set(
    raw
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean),
  )].sort();
}

export function createNode(input: {
  id: string;
  kind: SymbolKind;
  title: string;
  content: string;
  tags?: string[];
  parentIds?: string[];
  createdAt: string;
}): SymbolLabNode {
  return {
    id: input.id,
    kind: input.kind,
    claimClass: claimClassFor(input.kind),
    title: input.title.trim(),
    content: input.content.trim(),
    tags: [...new Set(input.tags ?? [])].map((tag) => tag.toLowerCase()).sort(),
    parentIds: [...new Set(input.parentIds ?? [])].sort(),
    createdAt: input.createdAt,
    returnPointers: [],
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
  };
}

export function createReturnPointer(input: {
  id: string;
  nodeId: string;
  prompt: string;
  context?: string;
  createdAt: string;
}): ReturnPointer {
  return {
    id: input.id,
    nodeId: input.nodeId,
    prompt: input.prompt.trim(),
    context: (input.context ?? "").trim(),
    createdAt: input.createdAt,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
  };
}

export function createPromotionProposal(input: {
  id: string;
  nodeId: string;
  target: PromotionTarget;
  createdAt: string;
}): PromotionProposal {
  return {
    id: input.id,
    nodeId: input.nodeId,
    target: input.target,
    status: "proposal_only",
    createdAt: input.createdAt,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
  };
}

export function relatedSeeds(
  source: SymbolLabNode,
  candidates: SymbolLabNode[],
): RelatedSeed[] {
  const sourceTags = new Set(source.tags);
  const sourceTokens = tokens(`${source.title} ${source.content}`);

  return candidates
    .filter((candidate) => candidate.id !== source.id)
    .map((candidate) => {
      let score = 0;
      const reasons: string[] = [];
      const sharedTags = candidate.tags.filter((tag) => sourceTags.has(tag)).sort();

      if (sharedTags.length) {
        score += sharedTags.length * 2;
        reasons.push(`shared tags: ${sharedTags.join(", ")}`);
      }

      const candidateTokens = tokens(`${candidate.title} ${candidate.content}`);
      const overlap = [...sourceTokens].filter((token) => candidateTokens.has(token));
      const union = new Set([...sourceTokens, ...candidateTokens]);
      const lexical = union.size ? overlap.length / union.size : 0;

      if (lexical > 0) {
        score += lexical;
        reasons.push(`lexical overlap: ${lexical.toFixed(3)}`);
      }

      if (source.parentIds.includes(candidate.id)) {
        score += 4;
        reasons.push("direct parent");
      }

      if (candidate.parentIds.includes(source.id)) {
        score += 4;
        reasons.push("direct child");
      }

      return { node: candidate, score, reasons };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.node.title.localeCompare(b.node.title));
}
