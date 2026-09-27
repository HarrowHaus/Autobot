"""Verify Grazer over loopback HTTP against an unmodified pinned RIP-302 module.

The SQLite jobs are explicitly synthetic local fixtures, not funded production
jobs or evidence of demand. No keys, signatures, live POSTs, claims or payments.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import platform
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from importlib.metadata import version
from flask import Flask, request
from werkzeug.serving import make_server
from grazer_rip302 import GrazerRIP302

NODE_COMMIT = "a4d39e9604897caf30693b05a79181018521811f"
NODE_BLOB = "bb8d08a1ca9966032731047d63a1270af19ae3d1"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest_database(path):
    with sqlite3.connect(path) as connection:
        return hashlib.sha256("\n".join(connection.iterdump()).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-module", required=True, type=Path)
    args = parser.parse_args()
    raw = args.node_module.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(blob == NODE_BLOB, "Upstream module differs from inspected/pinned blob")
    spec = importlib.util.spec_from_file_location("verified_rip302_node", args.node_module)
    require(spec is not None and spec.loader is not None, "Cannot load node module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.CREATE_REQUIRE_SIG, "Default signature enforcement must remain enabled")
    traces = []
    cases = []
    with tempfile.TemporaryDirectory(prefix="grazer-node-local-") as temporary:
        db = str(Path(temporary) / "synthetic-jobs.sqlite")
        app = Flask("grazer-local-node-proof")
        module.register_agent_economy(app, db)

        @app.before_request
        def refuse_mutations():
            if request.method != "GET":
                return {"error": "this verification only permits GET"}, 405

        @app.after_request
        def record_http(response):
            traces.append({"method": request.method, "path": request.full_path,
                           "http_status": response.status_code, "body": response.get_json()})
            return response

        now = int(time.time())
        fixtures = [
            ("job_local_a", "writing", 2, "open"),
            ("job_local_b", "writing", 10, "open"),
            ("job_local_c", "code", 15, "open"),
            ("job_local_d", "writing", 15, "open"),
            ("job_local_e", "code", 15, "open"),
            ("job_local_f", "research", 5, "claimed"),
            ("job_local_g", "writing", 20, "completed"),
        ]
        with sqlite3.connect(db) as connection:
            for i, (jid, category, reward, status) in enumerate(fixtures):
                connection.execute("""INSERT INTO agent_jobs
                    (job_id, poster_wallet, title, description, category,
                     reward_rtc, reward_i64, escrow_i64, platform_fee_i64,
                     status, created_at, expires_at, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (jid, "synthetic-local-poster", "Local fixture " + jid,
                     "Synthetic fixture, not a funded production job", category,
                     reward, reward * 1000000, 0, 0, status, now - i,
                     now + 3600, '["local-fixture"]'))
            connection.commit()
        before = digest_database(db)
        server = make_server("127.0.0.1", 0, app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(server.server_port)
        client = GrazerRIP302(base, timeout=5)
        try:
            specifications = [
                ("open", {}, {"job_local_a", "job_local_b", "job_local_c", "job_local_d", "job_local_e"}),
                ("writing", {"category": "writing"}, {"job_local_a", "job_local_b", "job_local_d"}),
                ("minimum", {"min_reward": 10}, {"job_local_b", "job_local_c", "job_local_d", "job_local_e"}),
                ("combined", {"category": "writing", "min_reward": 10}, {"job_local_b", "job_local_d"}),
                ("empty", {"category": "audio"}, set()),
                ("claimed", {"status": "claimed"}, {"job_local_f"}),
            ]
            for name, parameters, expected in specifications:
                rows = client.browse(**parameters)
                require({row["job_id"] for row in rows} == expected, "Wrong result: " + name)
                require(len(rows) == len(expected), "Duplicate row: " + name)
                require(all(row["description"].startswith("Synthetic fixture") for row in rows), "Unexpected source data")
                cases.append({"name": name, "passed": True, "ids": sorted(expected)})
            pages = [client.browse(limit=2, offset=offset) for offset in (0, 2, 4)]
            flattened = [row for page in pages for row in page]
            require(len(flattened) == 5, "Paging row count mismatch")
            require(len({row["job_id"] for row in flattened}) == 5, "Paging lost distinct jobs")
            require(sum(row["reward_rtc"] == 15 for row in flattened) == 3, "Equal-reward jobs were merged")
            cases.append({"name": "three_pages_equal_reward_preservation", "passed": True,
                          "ids": [row["job_id"] for row in flattened]})
            for row in flattened:
                opportunity = client.to_opportunity(row, node=base)
                require(opportunity["raw"] == row and opportunity["url"].startswith(base + "/agent/jobs/"), "Wrong local provenance")
            cases.append({"name": "origin_and_raw_provenance", "passed": True})
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        require(not thread.is_alive(), "Local HTTP server did not stop")
        after = digest_database(db)
        require(before == after, "GET verification changed SQLite state")
        require(len(traces) == 9 and all(t["method"] == "GET" and t["http_status"] == 200 for t in traces), "HTTP trace mismatch")
        require(hashlib.sha1(b"blob " + str(len(args.node_module.read_bytes())).encode() + b"\0" + args.node_module.read_bytes()).hexdigest() == NODE_BLOB, "Source modified during test")
        result = {
            "schema": "grazer-local-node-evidence/1", "status": "PASS",
            "upstream_commit": NODE_COMMIT, "upstream_blob": blob,
            "upstream_sha256": hashlib.sha256(raw).hexdigest(),
            "client_sha256": hashlib.sha256(Path(__file__).with_name("grazer_rip302.py").read_bytes()).hexdigest(),
            "python": platform.python_version(), "flask": version("Flask"),
            "cases": cases, "http_requests": traces,
            "database_before": before, "database_after": after,
            "fixture_kind": "synthetic SQLite job records served by real unmodified upstream node over loopback HTTP",
            "mock_http": False, "live_wallet_access": False, "signing": False,
            "financial_transactions": 0, "production_job_claims": 0,
            "production_reachability_proven": False,
            "maintainer_acceptance": "not asserted",
        }
        print("GRAZER_LOCAL_NODE_RECEIPT_BEGIN")
        print(json.dumps(result, sort_keys=True, indent=2))
        print("GRAZER_LOCAL_NODE_RECEIPT_END")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
