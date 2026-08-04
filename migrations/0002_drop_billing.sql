-- Removes the account / credit / API-key / checkout system entirely.
--
-- These tables backed a billing flow that was never enabled, never reviewed,
-- and never tested against real money. They are dropped rather than left
-- empty: an unused table storing emails and key hashes is a standing
-- liability (and a standing privacy claim we'd have to keep making), and
-- keeping the schema around invites someone to wire it back up without the
-- review that flow actually needs.
--
-- failed_conversion_signals is dropped for the same reason: the code that
-- wrote to it (hashed CSV headers of unrecognized uploads) was removed
-- during the containment pass, so the table only served to imply a data
-- collection behavior that no longer exists.

DROP TABLE IF EXISTS credit_ledger;
DROP TABLE IF EXISTS api_keys;
DROP TABLE IF EXISTS checkout_sessions;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS failed_conversion_signals;

-- conversions.account_id referenced accounts(id). Rebuild the table without
-- it so no per-user linkage remains: usage metadata is now fully anonymous.
CREATE TABLE conversions_new (
  id TEXT PRIMARY KEY,
  processor TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT NOT NULL, -- 'ok' | 'error'
  row_count INTEGER,
  error_code TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO conversions_new (id, processor, target, status, row_count, error_code, created_at)
  SELECT id, processor, target, status, row_count, error_code, created_at FROM conversions;

DROP TABLE conversions;
ALTER TABLE conversions_new RENAME TO conversions;
