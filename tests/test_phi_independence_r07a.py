import json
from pathlib import Path

import pytest

from scripts import phi_independence_r07a as field


def fixture_manifest():
    m = field.template()
    m.update(campaign_id="synthetic-test", observed_utc="2025-01-01T00:00:00Z",
             observer="fixture")
    m["source_commits"] = {k: "a"*40 for k in field.REPOS}
    m["versions"] = {k: "fixture" for k in m["versions"]}
    return m


def put(root, manifest, gate, name, value):
    raw = field.canonical(value)
    (root / name).write_bytes(raw)
    manifest["gates"][gate]["artifacts"][name] = field.sha(raw)
    manifest["gates"][gate]["observation"] = "OBSERVED_PASS"


def observation(name):
    return {"schema":"phios.field-observation.v1", "observed_utc":"2025-01-01T00:00:00Z",
            "observer":"fixture", "method":"synthetic fixture, not field evidence",
            "checks":{k:True for k in field.MANUAL[name]}}


def test_empty_is_held(tmp_path):
    r = field.evaluate(tmp_path, fixture_manifest())
    assert r["correlated_gates"] == 0 and r["sovereignty_status"] == "UNVERIFIED"
    assert not r["exit_verified"]


def test_manual_observation_cannot_certify(tmp_path):
    m = fixture_manifest()
    name = "wan-observation.json"
    put(tmp_path, m, "wan_denied", name, observation(name))
    r = field.evaluate(tmp_path, m)
    assert r["correlated_gates"] == 1 and r["state"] == "HELD"
    assert not r["offline_verified"] and not r["exit_verified"]


def test_restore_correlation_and_mismatch(tmp_path):
    m = fixture_manifest()
    digest = "b"*64
    put(tmp_path, m, "vault_restore", "vault-verify.json",
        {"schema":1,"status":"INTEGRITY_VERIFIED","sha256":digest,"nodes":3})
    put(tmp_path, m, "vault_restore", "vault-restore.json",
        {"schema":1,"status":"RESTORED","sha256":digest,"nodes":3})
    obs = dict(observation("restore-observation.json"), original_sha256=digest, restored_sha256=digest)
    put(tmp_path, m, "vault_restore", "restore-observation.json", obs)
    assert field.evaluate(tmp_path,m)["gates"]["vault_restore"]["state"] == "CORRELATED_SELF_REPORTED"
    put(tmp_path,m,"vault_restore","restore-observation.json",dict(obs, restored_sha256="c"*64))
    assert field.evaluate(tmp_path,m)["gates"]["vault_restore"]["state"] == "HELD"


def test_hash_mismatch_and_no_overclaim(tmp_path):
    m = fixture_manifest()
    name = "r01.json"
    r = {"schema":1,"certification":"UNVERIFIED","operator_declared_offline":True,
         "offline_verified":False,"inference":{"status":"PASS","scope":"loopback_marker_only"}}
    put(tmp_path,m,"readiness",name,r)
    assert field.evaluate(tmp_path,m)["correlated_gates"] == 1
    (tmp_path/name).write_text("{}")
    assert field.evaluate(tmp_path,m)["gates"]["readiness"]["reason"] == "ARTIFACT_HASH_MISMATCH"
    put(tmp_path,m,"readiness",name,dict(r,certification="EXIT-VERIFIED"))
    assert field.evaluate(tmp_path,m)["correlated_gates"] == 0


def test_inventory_no_writes_and_duplicates(tmp_path):
    p = tmp_path/"r01.json"
    p.write_text('{"x":1,"x":2}')
    assert field.inventory(tmp_path)["artifact_sha256"]["r01.json"] is None
    assert list(tmp_path.iterdir()) == [p]


def test_reject_git_directory(tmp_path):
    (tmp_path/".git").mkdir()
    with pytest.raises(ValueError):
        field.evaluate(tmp_path, fixture_manifest())


def test_all_correlated_never_certifies(tmp_path, monkeypatch):
    # Isolate aggregation policy from per-gate contract tests.
    m = fixture_manifest()
    for gate,names in field.GATES.items():
        for name in names:
            put(tmp_path,m,gate,name,{"synthetic":True})
    monkeypatch.setattr(field,"correlate",lambda *args:None)
    r = field.evaluate(tmp_path,m)
    assert r["correlated_gates"] == 9 and r["state"] == "REVIEW_READY_NOT_CERTIFIED"
    assert r["sovereignty_status"] == "PARTIAL"
    assert not any(r[k] for k in ("exit_verified","offline_verified","authority_granted",
                                  "source_commits_verified","independent_review_verified"))


def test_forge_rejects_mismatched_plan():
    p = {"schema":"agentora.phiforge.r05b.v1","state":"CANDIDATE_REVIEW_REQUIRED"}
    b = {"schema":"agentora.phiforge.r05a.v1","state":"BUILD_PASS_REVIEW_ONLY","exit_code":0}
    with pytest.raises(ValueError):
        field.correlate("forge",dict(zip(field.GATES["forge"],(p,{},b))))


def test_mesh_rejects_unknown_restart():
    import hashlib
    nonce = "a"*64
    value = bytes.fromhex(nonce)
    for _ in range(369):
        value=hashlib.sha256(value).digest()
    a = {"schema":"phios.mesh.challenge.v1","state":"PINNED_PEER_CHALLENGE_PASSED",
         "tls_pin_verified":True,"rounds":369,"nonce":nonce,"node":"node02",
         "result_sha256":value.hex(),"execution_authority":False,"inference_verified":False,
         "offline_verified":False,"remote_workload_authorized":False}
    b = {"schema":"phios.mesh.inference.v1","state":"FINISHED","outcome":"CORRECT",
         "job":"b"*64,"node":"node02","model_requested":"test:local","case":"logic",
         "model_identity_attested":False,"offline_verified":False,"execution_authority":False}
    spec = {"schema":b["schema"],"job":b["job"],"node":b["node"],"model":b["model_requested"],"case":b["case"]}
    b["task_sha256"] = field.sha(field.canonical(spec))
    field.correlate("mesh",dict(zip(field.GATES["mesh"],(a,b,b))))
    with pytest.raises(ValueError):
        field.correlate("mesh",dict(zip(field.GATES["mesh"],(a,b,dict(b,state="OUTCOME_UNKNOWN")))))


def test_forge_positive_unicode_and_drift():
    task = {"source_sha":"a"*40,"instruction":"Review Φ"}
    patch = "+Φ\n"
    proposal = {"patch":patch,"patch_sha256":field.sha(patch.encode()),
                "after_sha256":"b"*64}
    pplan = {"task":task,"model":"test:local"}
    import hashlib
    # Independent producer serialization convention, not the verifier helper.
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    p = {"schema":"agentora.phiforge.r05b.v1","state":"CANDIDATE_REVIEW_REQUIRED",
         "plan":pplan,"plan_sha256":digest(pplan),"proposal":proposal,
         "operator_declared_offline":True,"build_authorized":False,
         "eligible_for_merge":False,"execution_authority":False,"offline_verified":False}
    image = "sha256:"+"c"*64
    plan = {"schema":"agentora.phiforge.r05a.v1","state":"REVIEW_REQUIRED",
            "task":task,"proposal":proposal,"image_id":image}
    wrapper = {"plan":plan,"plan_sha256":digest(plan)}
    b = {"schema":"agentora.phiforge.r05a.v1","state":"BUILD_PASS_REVIEW_ONLY",
         "exit_code":0,"plan_sha256":digest(plan),"source_sha":task["source_sha"],
         "image_id":image,"patch_sha256":proposal["patch_sha256"],
         "after_sha256":proposal["after_sha256"],"operator_declared_offline":True,
         "network_none_requested":True,"pull_never_requested":True,
         "eligible_for_merge":False,"execution_authority":False,"offline_verified":False}
    values = dict(zip(field.GATES["forge"],(p,wrapper,b)))
    field.correlate("forge",values)
    b["after_sha256"] = "d"*64
    with pytest.raises(ValueError):
        field.correlate("forge",values)


def test_inference_counts_and_duplicate_cases():
    cases = ("arithmetic","ordering","logic","extraction","code_trace","instruction")
    reports = []
    for model in ("test:one","test:two"):
        reports.append({"model":model,"attempts":[{"case":c,"repeat":1,
                        "status":"CORRECT","correct":True} for c in cases],
                        "correct":6,"attempted":6,"expected_attempts":6,
                        "errors":0,"exact_match_fraction":1})
    r = {"schema":1,"suite":"phi-inference-smoke-v1","complete":True,
         "operator_declared_offline":True,"offline_verified":False,
         "routing_authority":False,"repeats":1,"reports":reports}
    field.correlate("inference",{"r03.json":r})
    reports[0]["attempts"][0]["case"] = "logic"
    with pytest.raises(ValueError):
        field.correlate("inference",{"r03.json":r})


def test_bridge_unicode_review_digest():
    review = {k:"Φ synthetic" for k in ("assessment","risks","next_steps","uncertainties")}
    r = {"schema":"agentora.phibuddy-review-receipt.v1",
         "state":"LOCAL_REVIEW_UNVERIFIED","consent_sha256":"a"*64,
         "packet_sha256":"b"*64,"review_sha256":field.sha(field.canonical(review)),
         "review":review,"human_review_required":True,"tool_calls":0,
         "execution_authority":False,"source_verified":False,"completion_verified":False,
         "model_identity_attested":False,"offline_verified":False,"persisted_by_bridge":False}
    field.correlate("bridge",{"r04b.json":r})
    r["review"]["risks"]="modified"
    with pytest.raises(ValueError):
        field.correlate("bridge",{"r04b.json":r})
