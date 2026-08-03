-- PayoutSplit core schema.
-- Note: transaction/file CONTENT is never stored anywhere in this schema by design.
-- Only metadata (counts, status codes, hashed signatures) is persisted.

CREATE TABLE accounts (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  stripe_customer_id TEXT UNIQUE,
  credit_balance INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE api_keys (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id),
  key_hash TEXT UNIQUE NOT NULL,
  key_prefix TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  revoked_at TEXT,
  last_used_at TEXT
);
CREATE INDEX idx_api_keys_account ON api_keys(account_id);

CREATE TABLE checkout_sessions (
  id TEXT PRIMARY KEY,
  stripe_session_id TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL, -- 'web_credit_pack' | 'api_credit_pack'
  credits_granted INTEGER NOT NULL,
  account_id TEXT REFERENCES accounts(id),
  status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'fulfilled'
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE credit_ledger (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id),
  delta INTEGER NOT NULL,
  reason TEXT NOT NULL, -- 'purchase' | 'conversion' | 'free_trial' | 'adjustment'
  stripe_session_id TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_credit_ledger_account ON credit_ledger(account_id);

-- Metadata only: never processor names' worth of PII, never row content.
CREATE TABLE conversions (
  id TEXT PRIMARY KEY,
  account_id TEXT REFERENCES accounts(id),
  processor TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT NOT NULL, -- 'ok' | 'error'
  row_count INTEGER,
  error_code TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Growth-loop signal: unrecognized format inputs. Only a hashed header
-- signature is stored, never any transaction content.
CREATE TABLE failed_conversion_signals (
  id TEXT PRIMARY KEY,
  processor_guess TEXT,
  target TEXT,
  reason_code TEXT NOT NULL,
  header_signature_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_failed_signals_lookup ON failed_conversion_signals(processor_guess, target, created_at);

-- Growth-loop signal: "didn't find your platform?" landing-page submissions.
CREATE TABLE landing_page_queries (
  id TEXT PRIMARY KEY,
  query_text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
