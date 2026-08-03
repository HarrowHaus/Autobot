import type { Env } from "./types.js";

const NEW_PAIR_THRESHOLD = 10; // failed-conversion signals in the window
const QUALITY_THRESHOLD = 10; // "didn't find your platform" asks in the window
const WINDOW_DAYS = 30;
const GITHUB_REPO = "harrowhaus/autobot";

interface SignalGroup {
  processor_guess: string | null;
  target: string | null;
  count: number;
}

async function createGithubIssue(env: Env, title: string, body: string): Promise<void> {
  if (!env.GITHUB_TOKEN) return; // growth loop detection still runs; issue filing is best-effort

  await fetch(`https://api.github.com/repos/${GITHUB_REPO}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "payoutsplit-growth-loop",
    },
    body: JSON.stringify({ title, body, labels: ["growth-loop"] }),
  });
}

/**
 * Weekly cron entry point. Pure detection over the last WINDOW_DAYS of
 * signals — the actual build step (scaffolding a new parser/mapper pair)
 * is done by an agent reviewing the resulting GitHub issues, not here.
 */
export async function runGrowthLoopDetection(env: Env): Promise<void> {
  const failedGroups = await env.DB.prepare(
    `SELECT processor_guess, target, COUNT(*) as count
     FROM failed_conversion_signals
     WHERE created_at >= datetime('now', ?)
     GROUP BY processor_guess, target
     HAVING count >= ?`
  )
    .bind(`-${WINDOW_DAYS} days`, NEW_PAIR_THRESHOLD)
    .all<SignalGroup>();

  for (const group of failedGroups.results ?? []) {
    await createGithubIssue(
      env,
      `[growth-loop] New pair candidate: ${group.processor_guess ?? "unknown"} -> ${group.target ?? "unknown"}`,
      `${group.count} failed-conversion signals in the last ${WINDOW_DAYS} days for this processor/target combination.\n\n` +
        `Next step: find the public export format spec for "${group.processor_guess}", scaffold a parser + mapper following the existing pattern in \`src/parsers/\` and \`src/mappers/\`, add fixtures/tests, generate its landing page, and deploy.`
    );
  }

  const queries = await env.DB.prepare(
    `SELECT query_text, COUNT(*) as count
     FROM landing_page_queries
     WHERE created_at >= datetime('now', ?)
     GROUP BY query_text
     HAVING count >= ?`
  )
    .bind(`-${WINDOW_DAYS} days`, QUALITY_THRESHOLD)
    .all<{ query_text: string; count: number }>();

  for (const q of queries.results ?? []) {
    await createGithubIssue(
      env,
      `[growth-loop] Repeated "missing platform" request: ${q.query_text}`,
      `Requested ${q.count} times in the last ${WINDOW_DAYS} days via the landing-page feedback box.`
    );
  }
}
