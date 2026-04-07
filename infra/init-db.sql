-- ───────────────────────────────────────────────
-- RTS CPI — Postgres Init Script
-- Runs once when the postgres container is first created.
-- ───────────────────────────────────────────────

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create a separate schema for Superset metadata
CREATE SCHEMA IF NOT EXISTS superset;

-- Grant the cpi user access to superset schema
GRANT ALL ON SCHEMA superset TO cpi;
