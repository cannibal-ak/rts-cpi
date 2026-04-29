# Open Architectural Questions

## 1. JY Ingestion Data Attribution
**Observation**: The JY ingest script (`scripts/ingest_daily.py:46`) hardcodes the **Skywave admin tenant UUID** (`a0000000-0000-0000-0000-000000000001`) instead of the JY tenant UUID (`dd000000-0000-0000-0000-000000000001`).

**Implications**: Because of strict RLS, data loaded for JY will be attributed to Skywave. JY users will be completely unable to see their own data.
**Interpretations**:
1. **By-Design**: Skywave intentionally owns all ingested data centrally, and JY users are supposed to access it via an explicit scope bypass. (Evidence against: RLS policies strictly enforce `tenant_id` match, not `tenant_code` match).
2. **Bug**: A copy-paste error occurred during tenant dictionary creation, failing to update the Skywave UUID to the newly generated JY canonical UUID.

## 2. Superset Filter Bar Orientation
**Observation**: The JY Dashboard filter bar is currently horizontal (`json_metadata` orientation is `None`).
**Resolution Needed**: Confirm if we should update the Superset metadata to enforce a VERTICAL, left-hand filter bar for the JY dashboard.
