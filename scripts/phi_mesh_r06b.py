"""R06-B: one preauthorized synthetic LAN inference job, durable admission."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import hmac
import http.client
import json
from pathlib import Path
import sqlite3
import sys

from scripts import phi_mesh_r06a as mesh
from scripts import phi_inference_r03 as inference
from phios.network.homenode import HomeNodeConfig, load_trust

SCHEMA = "phios.mesh.inference.v1"
PORT = 3770
CASES = {case[0]: case for case in inference.CASES}


def task(job, node, model, case):
    if (not isinstance(job, str) or not mesh.HEX.fullmatch(job)
            or not isinstance(node, str) or not mesh.NODE.fullmatch(node)
            or not isinstance(model, str) or not inference.validate_model(model)
            or "cloud" in model.lower() or not isinstance(case, str) or case not in CASES):
        raise ValueError("invalid task")
    return {"schema": SCHEMA, "job": job, "node": node, "model": model, "case": case}


def digest(value):
    return hashlib.sha256(mesh.canonical(value)).hexdigest()


def receipt(spec, state, outcome=None):
    if state not in {"NOT_ADMITTED", "OUTCOME_UNKNOWN", "FINISHED"}:
        raise ValueError("invalid state")
    if ((state == "FINISHED" and outcome not in {"CORRECT", "INCORRECT", "ERROR"})
            or (state != "FINISHED" and outcome is not None)):
        raise ValueError("invalid outcome")
    return {"schema": SCHEMA, "task_sha256": digest(spec), "job": spec["job"],
            "node": spec["node"], "model_requested": spec["model"], "case": spec["case"],
            "state": state, "outcome": outcome, "model_identity_attested": False,
            "offline_verified": False, "execution_authority": False}


def validate_receipt(spec, value):
    if (type(value) is not dict or mesh.canonical(value) !=
            mesh.canonical(receipt(spec, value.get("state"), value.get("outcome")))):
        raise ValueError("receipt mismatch")
    return value


def database_path(path):
    path = Path(path)
    if (not path.is_absolute() or not path.parent.is_dir() or path.is_symlink()
            or any((p / ".git").exists() for p in path.resolve().parents)):
        raise ValueError("private database path required outside Git")
    return path.resolve()


class Journal:
    """Single-job journal. A committed admission is never automatically retried."""

    def __init__(self, path, spec):
        self.path = database_path(path)
        self.spec = task(spec["job"], spec["node"], spec["model"], spec["case"])
        if self.spec != spec:
            raise ValueError("task schema")
        # Explicit initialization only on a new file. Never recreate lost state
        # as part of opening a previously configured server.
    def connect(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                             timeout=5, isolation_level=None)
        db.execute("PRAGMA synchronous=FULL")
        return db

    def initialize(self):
        import os
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE job (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                       "spec BLOB NOT NULL, state TEXT NOT NULL, outcome TEXT)")
            db.execute("INSERT INTO job VALUES (1, ?, 'NOT_ADMITTED', NULL)",
                       (mesh.canonical(self.spec),))
            db.commit()

    def read(self, db):
        rows = db.execute("SELECT singleton,spec,state,outcome FROM job").fetchall()
        if len(rows) != 1 or rows[0][0] != 1 or rows[0][1] != mesh.canonical(self.spec):
            raise ValueError("journal task mismatch")
        return receipt(self.spec, rows[0][2], rows[0][3])

    def status(self):
        with closing(self.connect()) as db:
            return self.read(db)

    def submit(self, attempt=inference.attempt):
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.read(db)
            if current["state"] != "NOT_ADMITTED":
                db.commit()
                return current
            db.execute("UPDATE job SET state='OUTCOME_UNKNOWN' WHERE singleton=1")
            db.commit()
        # Admission is durable BEFORE calling the daemon. Crash or loss after
        # admission deliberately leaves OUTCOME_UNKNOWN, even if no call occurred.
        result = attempt(self.spec["model"], CASES[self.spec["case"]], 120)
        outcome = result.get("status")
        final = receipt(self.spec, "FINISHED", outcome)
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            if self.read(db)["state"] != "OUTCOME_UNKNOWN":
                raise ValueError("journal drift")
            db.execute("UPDATE job SET state='FINISHED', outcome=? WHERE singleton=1",
                       (outcome,))
            db.commit()
        return final


class Handler(mesh.Handler):
    def do_POST(self):
        server = self.server
        expected_host = "%s:%d" % server.server_address
        if (self.path not in {"/v1/submit", "/v1/status"}
                or self.headers.get_all("Host") != [expected_host]
                or "Origin" in self.headers or "Transfer-Encoding" in self.headers):
            self.respond(403, {"state": "REFUSED"})
            return
        auth = self.headers.get_all("Authorization") or []
        if (len(auth) != 1 or not mesh.re.fullmatch(r"Bearer [0-9a-f]{64}", auth[0])
                or not hmac.compare_digest(auth[0], "Bearer " + server.token)):
            self.respond(403, {"state": "REFUSED"})
            return
        sizes = self.headers.get_all("Content-Length") or []
        if (len(sizes) != 1 or not mesh.re.fullmatch(r"[0-9]{1,4}", sizes[0])
                or not 0 < int(sizes[0]) <= mesh.MAX_BODY
                or self.headers.get_all("Content-Type") != ["application/json"]):
            self.respond(400, {"state": "REFUSED"})
            return
        try:
            raw = self.rfile.read(int(sizes[0]))
            if mesh.canonical(mesh.decode(raw)) != mesh.canonical(server.journal.spec):
                self.respond(403, {"state": "REFUSED"})
                return
            result = (server.journal.submit() if self.path == "/v1/submit"
                      else server.journal.status())
        except (ValueError, OSError, sqlite3.Error, RecursionError, http.client.HTTPException):
            self.respond(503, {"state": "HELD"})
            return
        self.respond(200, result)


class Server(mesh.MeshServer):
    def __init__(self, ip, peer, context, token, journal, port=PORT):
        journal.status()  # Refuse missing, invalid or mismatched journal.
        self.journal = journal
        super().__init__(ip, peer, journal.spec["node"], context, token, port)
        self.RequestHandlerClass = Handler


def call(ip, spec, cert, pin, token_file, action, port=PORT):
    if not mesh.lan_ip(ip) or not mesh.HEX.fullmatch(pin) or action not in {"submit", "status"}:
        raise ValueError("invalid peer or action")
    if spec != task(spec["job"], spec["node"], spec["model"], spec["case"]):
        raise ValueError("invalid task schema")
    mesh.private_file(cert, 1024 * 1024)
    token = mesh.token_from_file(token_file)
    context, loaded = load_trust(HomeNodeConfig(ip, port, pin, str(cert), str(token_file)))
    if not hmac.compare_digest(token, loaded):
        raise ValueError("trust file changed")
    connection = http.client.HTTPSConnection(ip, port, context=context, timeout=150)
    try:
        connection.connect()
        peer = connection.sock.getpeercert(binary_form=True) if connection.sock else None
        if not peer or not hmac.compare_digest(hashlib.sha256(peer).hexdigest(), pin):
            raise ValueError("certificate pin mismatch")
        connection.request("POST", "/v1/" + action, body=mesh.canonical(spec),
                           headers={"Authorization": "Bearer " + token,
                                    "Content-Type": "application/json", "Connection": "close"})
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Content-Type") != "application/json":
            raise ValueError("peer refused")
        raw = response.read(mesh.MAX_BODY + 1)
        if len(raw) > mesh.MAX_BODY:
            raise ValueError("receipt size")
        return validate_receipt(spec, mesh.decode(raw))
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "init", "serve", "submit", "status"))
    parser.add_argument("--job", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--case", required=True, choices=tuple(CASES))
    parser.add_argument("--db", type=Path)
    parser.add_argument("--ip")
    parser.add_argument("--peer")
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--pin")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--approve-digest")
    parser.add_argument("--confirm-offline-lan", action="store_true")
    a = parser.parse_args(argv)
    try:
        spec = task(a.job, a.node, a.model, a.case)
        if a.stage == "plan":
            result = {"task": spec, "task_sha256": digest(spec)}
        else:
            if not a.confirm_offline_lan or a.approve_digest != digest(spec):
                raise ValueError("exact task approval required")
            if a.stage in {"init", "serve"}:
                if a.db is None:
                    raise ValueError("journal path required")
                journal = Journal(a.db, spec)
                if a.stage == "init":
                    journal.initialize()
                    result = journal.status()
                else:
                    if not all((a.ip, a.peer, a.cert, a.key, a.token_file)):
                        raise ValueError("server configuration")
                    if len({p.resolve() for p in (a.db, a.cert, a.key, a.token_file)}) != 4:
                        raise ValueError("separate private files")
                    with Server(a.ip, a.peer, mesh.server_context(a.cert, a.key),
                                mesh.token_from_file(a.token_file), journal) as server:
                        print("MESH_INFERENCE_LISTENING_ONE_APPROVED_JOB", flush=True)
                        for _ in range(3):
                            server.handle_request()
                    return 0
            else:
                if not all((a.ip, a.cert, a.pin, a.token_file)):
                    raise ValueError("client configuration")
                result = call(a.ip, spec, a.cert, a.pin, a.token_file, a.stage)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, sqlite3.Error, http.client.HTTPException, RecursionError):
        print("MESH_HELD: no confirmed result; query original journal status, never auto-retry",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
