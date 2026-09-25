import { useMemo, useState } from "react";
import {
  claimClassFor,
  createNode,
  createPromotionProposal,
  createReturnPointer,
  normalizeTags,
  relatedSeeds,
  type PromotionProposal,
  type PromotionTarget,
  type SymbolKind,
  type SymbolLabNode,
} from "../curiosity/symbolLab";

const kinds: Array<{ kind: SymbolKind; label: string; glyph: string }> = [
  { kind: "symbol", label: "Symbol", glyph: "◈" },
  { kind: "metaphor", label: "Metaphor", glyph: "≈" },
  { kind: "question", label: "Question", glyph: "?" },
  { kind: "hypothesis", label: "Hypothesis", glyph: "△" },
  { kind: "association", label: "Association", glyph: "↔" },
  { kind: "pattern", label: "Pattern", glyph: "⌘" },
  { kind: "dream_fragment", label: "Dream", glyph: "☾" },
  { kind: "creative_seed", label: "Seed", glyph: "✦" },
];

const targets: Array<{ target: PromotionTarget; label: string }> = [
  { target: "research", label: "Offer to Research" },
  { target: "build", label: "Offer to Build" },
  { target: "ledger_review", label: "Offer to Ledger Review" },
];

function nowIso() {
  return new Date().toISOString();
}

function newId(prefix: string) {
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2, 8)}`;
}

export function SymbolLab() {
  const [nodes, setNodes] = useState<SymbolLabNode[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [kind, setKind] = useState<SymbolKind>("creative_seed");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [parentId, setParentId] = useState("");
  const [returnPrompt, setReturnPrompt] = useState("");
  const [returnContext, setReturnContext] = useState("");
  const [proposals, setProposals] = useState<PromotionProposal[]>([]);

  const selected = nodes.find((node) => node.id === selectedId) ?? null;
  const related = useMemo(
    () => (selected ? relatedSeeds(selected, nodes).slice(0, 6) : []),
    [selected, nodes],
  );

  function addNode() {
    if (!title.trim() || !content.trim()) return;
    const node = createNode({
      id: newId("curiosity"),
      kind,
      title,
      content,
      tags: normalizeTags(tags),
      parentIds: parentId ? [parentId] : [],
      createdAt: nowIso(),
    });
    setNodes((current) => [...current, node]);
    setSelectedId(node.id);
    setTitle("");
    setContent("");
    setTags("");
    setParentId("");
  }

  function appendReturnPointer() {
    if (!selected || !returnPrompt.trim()) return;
    const pointer = createReturnPointer({
      id: newId("return"),
      nodeId: selected.id,
      prompt: returnPrompt,
      context: returnContext,
      createdAt: nowIso(),
    });
    setNodes((current) =>
      current.map((node) =>
        node.id === selected.id
          ? { ...node, returnPointers: [...node.returnPointers, pointer] }
          : node,
      ),
    );
    setReturnPrompt("");
    setReturnContext("");
  }

  function offer(target: PromotionTarget) {
    if (!selected) return;
    const proposal = createPromotionProposal({
      id: newId("promotion"),
      nodeId: selected.id,
      target,
      createdAt: nowIso(),
    });
    setProposals((current) => [proposal, ...current]);
  }

  return (
    <section className="symbol-lab">
      <header className="symbol-lab-head">
        <div>
          <div className="eyebrow">ΦDREAM · CURIOSITY LANE</div>
          <h1>Symbol Lab</h1>
          <p>
            Explore before deciding. Symbols may remain symbols; hypotheses may remain open.
          </p>
        </div>
        <div className="symbol-boundary">
          <b>SESSION LOCAL / UNPERSISTED</b>
          <span>ZERO AUTHORITY · NO EXECUTE PATH</span>
        </div>
      </header>

      <div className="symbol-lab-layout">
        <aside className="symbol-capture panel">
          <div className="panel-title">CAPTURE A SEED</div>
          <div className="symbol-kind-grid">
            {kinds.map((item) => (
              <button
                key={item.kind}
                className={kind === item.kind ? "active" : ""}
                onClick={() => setKind(item.kind)}
                title={item.label}
              >
                <b>{item.glyph}</b>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          <label>
            <span>Title</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Name the spark…"
            />
          </label>

          <label>
            <span>Fragment / thought</span>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="What are you noticing, wondering, or imagining?"
            />
          </label>

          <label>
            <span>Tags</span>
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="gear, water, rhythm"
            />
          </label>

          <label>
            <span>Parent thread</span>
            <select value={parentId} onChange={(event) => setParentId(event.target.value)}>
              <option value="">No parent</option>
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.title}
                </option>
              ))}
            </select>
          </label>

          <div className="claim-preview">
            <span>CLAIM CLASS</span>
            <b>{claimClassFor(kind).replaceAll("_", " ")}</b>
          </div>

          <button className="capture-seed" onClick={addNode}>
            Add to Session Field
          </button>
          <small className="symbol-disclaimer">
            This creates an ephemeral Curiosity object in the current PhiShell session. It does
            not write the Python Curiosity Store yet.
          </small>
        </aside>

        <section className="symbol-field panel">
          <div className="symbol-field-head">
            <div>
              <div className="panel-title">CONSTELLATION</div>
              <small>{nodes.length} SESSION OBJECTS</small>
            </div>
            <span>meaning ≠ verification</span>
          </div>

          {nodes.length === 0 ? (
            <div className="symbol-empty">
              <b>The field is empty.</b>
              <p>
                Add a symbol, strange question, dream fragment, metaphor, hypothesis, or creative
                seed. Nothing here has to earn a verdict yet.
              </p>
            </div>
          ) : (
            <div className="symbol-node-grid">
              {nodes.map((node, index) => (
                <button
                  key={node.id}
                  className={
                    selectedId === node.id
                      ? `symbol-node selected node-${index % 6}`
                      : `symbol-node node-${index % 6}`
                  }
                  onClick={() => setSelectedId(node.id)}
                >
                  <small>{node.kind.replaceAll("_", " ")}</small>
                  <b>{node.title}</b>
                  <span>{node.claimClass.replaceAll("_", " ")}</span>
                  <em>{node.tags.slice(0, 3).join(" · ") || "untagged"}</em>
                  {node.parentIds.length > 0 && <i>↳ child thread</i>}
                  {node.returnPointers.length > 0 && <i>↻ return marked</i>}
                </button>
              ))}
            </div>
          )}
        </section>

        <aside className="symbol-inspector panel">
          <div className="panel-title">THREAD INSPECTOR</div>
          {!selected ? (
            <div className="symbol-empty compact">
              Select a curiosity object to inspect its lineage, neighbors, and return path.
            </div>
          ) : (
            <>
              <div className="symbol-inspector-title">
                <small>{selected.kind.replaceAll("_", " ")}</small>
                <h2>{selected.title}</h2>
                <span>{selected.claimClass.replaceAll("_", " ")}</span>
              </div>
              <p className="symbol-content">{selected.content}</p>

              <div className="symbol-authority-grid">
                <div><span>OPERATIONAL</span><b>FALSE</b></div>
                <div><span>ACTION</span><b>FALSE</b></div>
                <div><span>EXECUTION</span><b>FALSE</b></div>
              </div>

              <section className="symbol-related">
                <h3>RELATED SEEDS</h3>
                {related.length === 0 ? (
                  <small>No transparent relationship found yet.</small>
                ) : (
                  related.map((item) => (
                    <button key={item.node.id} onClick={() => setSelectedId(item.node.id)}>
                      <b>{item.node.title}</b>
                      <span>{item.reasons.join(" · ")}</span>
                    </button>
                  ))
                )}
              </section>

              <section className="symbol-return">
                <h3>RETURN POINTER</h3>
                <input
                  value={returnPrompt}
                  onChange={(event) => setReturnPrompt(event.target.value)}
                  placeholder="Where should we resume?"
                />
                <textarea
                  value={returnContext}
                  onChange={(event) => setReturnContext(event.target.value)}
                  placeholder="Optional context to preserve…"
                />
                <button onClick={appendReturnPointer}>Mark Return</button>
                {selected.returnPointers.length > 0 && (
                  <div className="return-history">
                    {[...selected.returnPointers].reverse().slice(0, 3).map((pointer) => (
                      <article key={pointer.id}>
                        <b>{pointer.prompt}</b>
                        <small>{pointer.context || "No extra context."}</small>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="symbol-promote">
                <h3>EXPLICIT HANDOFF</h3>
                {targets.map((item) => (
                  <button key={item.target} onClick={() => offer(item.target)}>
                    {item.label}
                  </button>
                ))}
                <small>Creates proposal_only state. No destination admits it automatically.</small>
              </section>
            </>
          )}
        </aside>
      </div>

      <section className="symbol-proposals panel">
        <div className="panel-title">PROMOTION PROPOSALS · SESSION ONLY</div>
        {proposals.length === 0 ? (
          <div className="empty-state">Nothing has been offered downstream.</div>
        ) : (
          proposals.slice(0, 6).map((proposal) => {
            const node = nodes.find((item) => item.id === proposal.nodeId);
            return (
              <article key={proposal.id}>
                <b>{node?.title ?? "Unknown node"}</b>
                <span>→ {proposal.target.replaceAll("_", " ")}</span>
                <em>{proposal.status}</em>
                <small>authority: 0</small>
              </article>
            );
          })
        )}
      </section>
    </section>
  );
}
