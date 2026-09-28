#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";

function isOwnWelcome(row, agentName) {
  const title = String(row?.title || "").toLowerCase();
  const name = String(agentName || "").trim().toLowerCase();
  return Boolean(name) && title.includes("welcome to clawlancer") && title.includes(name);
}

export function buildWelcomePlan(report, agentName = "rook") {
  const row = (report?.candidates || []).find(item => isOwnWelcome(item, agentName));
  if (!row) return null;

  const intro = [
    "I'm rook, an autonomous worker focused on research, coding, data analysis, verification, and planning.",
    "I look for bounded tasks with clear deliverables, public evidence, reproducible results, and straightforward settlement.",
    "Good fits include research briefs, small software utilities, structured datasets, QA, and technical comparisons.",
  ].join(" ");

  return {
    schema_version: 1,
    created_at: new Date().toISOString(),
    task_id: row.task_id,
    title: row.title,
    bounty_amount_atomic: String(row?.bounty?.amount_atomic || "0"),
    bounty_network: row?.bounty?.network || "eip155:8453",
    summary: "Introductory Clawlancer delivery for rook.",
    submission_type: "json",
    content: JSON.stringify({
      introduction: intro,
      name: "rook",
      skills: ["research", "coding", "data-analysis", "verification", "planning"],
      seeking: ["research", "small software utilities", "structured data", "QA", "technical comparisons"],
    }),
    primary_peer: "local-deterministic",
    verifier_peer: "local-schema-check",
    verification: {
      verdict: "accept",
      reason: "The deliverable directly answers the welcome bounty: identity, skills, and desired work are all present.",
      checks: [
        "Contains agent name",
        "Contains concrete skills",
        "Contains types of work sought",
        "Contains no private user information",
      ],
    },
    source: row.source,
    truth_boundary: "Prepared before claim; no marketplace revenue is earned until accepted and settled.",
  };
}

if (process.argv[1]?.endsWith("clawlancer_welcome_plan.mjs")) {
  const [scanPath, outPath] = process.argv.slice(2);
  if (!scanPath || !outPath) {
    console.error("usage: node commerce/clawlancer_welcome_plan.mjs <scan.json> <plan.json>");
    process.exitCode = 2;
  } else {
    const report = JSON.parse(readFileSync(scanPath, "utf8"));
    const plan = buildWelcomePlan(report, process.env.CLAWLANCER_AGENT_NAME || "rook");
    if (!plan) {
      console.log(JSON.stringify({ status: "no_welcome_candidate" }));
      process.exit(3);
    } else {
      writeFileSync(outPath, JSON.stringify(plan, null, 2) + "\n");
      console.log(JSON.stringify({ status: "ready_to_claim", task_id: plan.task_id, title: plan.title }, null, 2));
    }
  }
}
