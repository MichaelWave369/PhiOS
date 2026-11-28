"""Read-only Local Intelligence R0.1 census. No model execution or downloads."""

import argparse
import http.client
import json

MAX_RESPONSE = 2 * 1024 * 1024
REGISTRY = json.loads(r'''[
  {
    "id": "vessie",
    "repository": "SuperPhiVessel",
    "kind": "companion",
    "backend": "bounded local Ollama trial; opt-in PhiServe drafts",
    "source": "https://github.com/MichaelWave369/SuperPhiVessel/blob/main/README.md",
    "limit": "Hosted cockpit is review-only; no general local integration assumed.",
    "verification": "documentation_only"
  },
  {
    "id": "gaia",
    "repository": "GypsyAI",
    "kind": "companion",
    "backend": "optional browser-to-local Ollama",
    "source": "https://github.com/MichaelWave369/GypsyAI/blob/main/README.md",
    "limit": "Browser permissions required; deterministic readers are not neural models.",
    "verification": "documentation_only"
  },
  {
    "id": "phibuddy",
    "repository": "PhiBuddy",
    "kind": "companion",
    "backend": "Ollama; three role prompts",
    "source": "https://github.com/MichaelWave369/PhiBuddy/blob/main/README.md",
    "limit": "Desktop source preview; not three independent trained models.",
    "verification": "documentation_only"
  },
  {
    "id": "brainc",
    "repository": "BrainC",
    "kind": "companion",
    "backend": "Ollama and local tools",
    "source": "https://github.com/MichaelWave369/BrainC/blob/main/README.md",
    "limit": "Tool execution requires independent safety qualification.",
    "verification": "documentation_only"
  },
  {
    "id": "braincbrain",
    "repository": "BrainC",
    "kind": "model_config",
    "backend": "Qwen2.5:14b via Ollama Modelfile",
    "source": "https://github.com/MichaelWave369/BrainC/blob/main/model/Modelfile",
    "limit": "Custom system prompt and parameters; no new weights demonstrated.",
    "verification": "documentation_only"
  },
  {
    "id": "brainc-mk1",
    "repository": "BrainC-MK1",
    "kind": "companion",
    "backend": "Ollama",
    "source": "https://github.com/MichaelWave369/BrainC-MK1/blob/main/README.md",
    "limit": "Legacy lineage; prefer current BrainC for first pilot.",
    "verification": "documentation_only"
  },
  {
    "id": "pocketbrain",
    "repository": "PocketBrain",
    "kind": "companion",
    "backend": "browser WebLLM or optional local bridge",
    "source": "https://github.com/MichaelWave369/PocketBrain/blob/main/README.md",
    "limit": "Browser model availability and hardware remain unverified.",
    "verification": "documentation_only"
  },
  {
    "id": "privatespark",
    "repository": "PrivateSpark",
    "kind": "companion",
    "backend": "Ollama chat and optional embeddings",
    "source": "https://github.com/MichaelWave369/PrivateSpark/blob/main/README.md",
    "limit": "Use loopback binding for local testing.",
    "verification": "documentation_only"
  },
  {
    "id": "thinktank",
    "repository": "think-tank",
    "kind": "companion",
    "backend": "explicit local Ollama council bridge",
    "source": "https://github.com/MichaelWave369/think-tank/blob/main/README.md",
    "limit": "Public Pages simulation is not live model execution.",
    "verification": "documentation_only"
  },
  {
    "id": "mindora",
    "repository": "Mindora",
    "kind": "companion",
    "backend": "optional Ollama reflection",
    "source": "https://github.com/MichaelWave369/Mindora/blob/main/README.md",
    "limit": "Specialized reflection, not medical care or a coding agent.",
    "verification": "documentation_only"
  },
  {
    "id": "agentora",
    "repository": "Agentora",
    "kind": "agent_workspace",
    "backend": "Ollama chat, teams and workflows",
    "source": "https://github.com/MichaelWave369/Agentora/blob/main/README.md",
    "limit": "Default mock launch is not live inference; actions require approval.",
    "verification": "documentation_only"
  },
  {
    "id": "phiserve",
    "repository": "PhiServe",
    "kind": "serving",
    "backend": "llama-server plus existing GGUF",
    "source": "https://github.com/MichaelWave369/PhiServe/blob/main/README.md",
    "limit": "No bundled weights; target-machine qualification needed.",
    "verification": "documentation_only"
  },
  {
    "id": "phistream",
    "repository": "PhiStream",
    "kind": "inference_research",
    "backend": "narrow Llama-family safetensors token-ID inference",
    "source": "https://github.com/MichaelWave369/PhiStream/blob/main/README.md",
    "limit": "Not a production chat engine or arbitrary checkpoint runtime.",
    "verification": "documentation_only"
  },
  {
    "id": "model-forge",
    "repository": "PhiStream",
    "kind": "training",
    "backend": "local QLoRA research lane",
    "source": "https://github.com/MichaelWave369/PhiStream/blob/main/docs/PHI_MODEL_FORGE_R05.md",
    "limit": "No trained model included; explicit reviewed-data gate.",
    "verification": "documentation_only"
  },
  {
    "id": "phicortex",
    "repository": "PhiCortex",
    "kind": "routing",
    "backend": "local Ollama-compatible text gateway",
    "source": "https://github.com/MichaelWave369/PhiCortex/blob/main/README.md",
    "limit": "No independently trained router established.",
    "verification": "documentation_only"
  },
  {
    "id": "microintelligence",
    "repository": "PhiMicroIntelligence369",
    "kind": "inference_research",
    "backend": "TNY2 JavaScript inference",
    "source": "https://github.com/MichaelWave369/PhiMicroIntelligence369/blob/main/README.md",
    "limit": "Upstream weights separate; numerical parity unverified.",
    "verification": "documentation_only"
  },
  {
    "id": "phibot",
    "repository": "phibot",
    "kind": "agent_workspace",
    "backend": "governed micro-agent runtime",
    "source": "https://github.com/MichaelWave369/phibot/blob/main/README.md",
    "limit": "Physical qualification remains; not a neural model.",
    "verification": "documentation_only"
  },
  {
    "id": "phiflow",
    "repository": "PhiFlow",
    "kind": "routing",
    "backend": "deterministic agent-flow primitives",
    "source": "https://github.com/MichaelWave369/PhiFlow/blob/main/README.md",
    "limit": "Not a model inference backend.",
    "verification": "documentation_only"
  },
  {
    "id": "phigenesis",
    "repository": "PhiGenesis",
    "kind": "learning_research",
    "backend": "language-free relational experiments",
    "source": "https://github.com/MichaelWave369/PhiGenesis/blob/main/README.md",
    "limit": "Not a conversational LLM.",
    "verification": "documentation_only"
  },
  {
    "id": "devmesh",
    "repository": "PhiDevelopmentalIntelligenceMesh",
    "kind": "learning_research",
    "backend": "offline associative learner",
    "source": "https://github.com/MichaelWave369/PhiDevelopmentalIntelligenceMesh/blob/main/README.md",
    "limit": "Not LLM training or autonomous developmental intelligence.",
    "verification": "documentation_only"
  },
  {
    "id": "phimemory9",
    "repository": "PhiMemory9",
    "kind": "memory",
    "backend": "recursive memory lifecycle",
    "source": "https://github.com/MichaelWave369/PhiMemory9/blob/main/README.md",
    "limit": "Production integration held.",
    "verification": "documentation_only"
  },
  {
    "id": "memoria",
    "repository": "Memoria",
    "kind": "memory",
    "backend": "local persistent storage",
    "source": "https://github.com/MichaelWave369/Memoria/blob/main/README.md",
    "limit": "Research candidate; sensitive-data use held.",
    "verification": "documentation_only"
  },
  {
    "id": "tribrain",
    "repository": "PhiTriBrain369",
    "kind": "memory",
    "backend": "model-independent evidence store",
    "source": "https://github.com/MichaelWave369/PhiTriBrain369/blob/main/README.md",
    "limit": "Three logical roles, not autonomous brains.",
    "verification": "documentation_only"
  },
  {
    "id": "phiark",
    "repository": "PhiARK",
    "kind": "memory",
    "backend": "offline knowledge vault",
    "source": "https://github.com/MichaelWave369/PhiARK/blob/main/README.md",
    "limit": "No model inference required.",
    "verification": "documentation_only"
  },
  {
    "id": "compaware",
    "repository": "CompAware",
    "kind": "learning_research",
    "backend": "computational awareness research",
    "source": "https://github.com/MichaelWave369/CompAware/blob/main/README.md",
    "limit": "No consciousness finding.",
    "verification": "documentation_only"
  },
  {
    "id": "phirsi",
    "repository": "PhiRSI",
    "kind": "learning_research",
    "backend": "measurable systems-improvement harness",
    "source": "https://github.com/MichaelWave369/PhiRSI/blob/main/README.md",
    "limit": "Not a self-improving model.",
    "verification": "documentation_only"
  }
]''')


def model_inventory(payload):
    """Describe API entries, never infer physical weight residency."""
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ValueError("invalid model inventory")
    models = payload["models"]
    if len(models) > 4096:
        raise ValueError("too many model entries")
    result = []
    seen = set()
    for row in models:
        if not isinstance(row, dict):
            raise ValueError("invalid model row")
        name = row.get("name", row.get("model"))
        if (not isinstance(name, str) or not name.strip() or len(name) > 512
                or any(ord(c) < 32 or ord(c) == 127 for c in name)
                or name in seen):
            raise ValueError("invalid or duplicate model name")
        seen.add(name)
        size = row.get("size")
        if size is not None and (type(size) is not int or size < 0):
            raise ValueError("invalid declared size")
        remote = row.get("remote_host") or row.get("remote_model")
        cloud_hint = name.casefold().endswith("-cloud") or name.casefold().endswith(":cloud")
        result.append({
            "name": name,
            "declared_bytes": size,
            "location": "CLOUD_REFERENCE" if remote or cloud_hint else "UNVERIFIED",
        })
    return sorted(result, key=lambda row: row["name"])


def probe_ollama():
    """Only GET fixed loopback /api/tags; never follow redirects or use proxies."""
    conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=2)
    try:
        conn.request("GET", "/api/tags", headers={"Accept": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            return {"status": "HTTP_ERROR", "models": []}
        body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            return {"status": "INVALID_RESPONSE", "models": []}
        return {"status": "API_REPORTED", "models": model_inventory(json.loads(body))}
    except (OSError, http.client.HTTPException):
        return {"status": "UNAVAILABLE", "models": []}
    except (ValueError, UnicodeError, RecursionError):
        return {"status": "INVALID_RESPONSE", "models": []}
    finally:
        conn.close()


def census(include_ollama=False):
    return {
        "schema": "phios.local-intelligence.r01",
        "status": "REVIEW_ONLY",
        "source_snapshot": "2026-11-27",
        "scope": "selected documented candidates; not an exhaustive code or weight audit",
        "registry": REGISTRY,
        "ollama": probe_ollama() if include_ollama else {"status": "NOT_CHECKED", "models": []},
        "inference_executed": False,
        "authority_granted": False,
        "physical_weights_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", action="store_true", help="explicit read-only loopback inventory")
    args = parser.parse_args()
    print(json.dumps(census(args.ollama), indent=2, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
