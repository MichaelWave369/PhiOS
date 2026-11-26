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
