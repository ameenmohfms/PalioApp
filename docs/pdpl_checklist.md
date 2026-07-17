# PDPL posture checklist (spec §14)

Status legend: ✅ implemented in code · 🟡 implemented, operator action required · 🔴 blocked on operator (§16)

## Data minimization & lawful basis
- ✅ No legal-name column, no date-of-birth column anywhere in the schema (N9). Identity =
  nickname + locale; optional email/Google sub only after explicit account upgrade.
- ✅ 18+ handled as attestation boolean, never a birth date.
- ✅ City collected only when the user sets it, used only for referral filtering.
- ✅ Consent records versioned in `consents` (screening consent, report-share consent);
  privacy-policy consent key reserved.
- 🔴 Consent/privacy text review by counsel before public release (§16 #5).

## Sensitive-data handling
- ✅ Health-adjacent content treated as sensitive: TLS assumed at the edge (12-factor);
  encryption at rest delegated to the DB volume/provider (D7).
- ✅ PII-scrubbed observability: safety/audit ledgers store event metadata with opaque
  subject IDs; a write-time scrubber drops text/content keys; the Case Review case file
  carries event counts, never message text (tested).
- ✅ No third-party analytics or ads SDKs anywhere in the app or API.
- ✅ LLM calls go only to the Anthropic API through one gateway; no other processors.
- 🟡 Data-processing agreement with the model provider — operator to execute.

## User rights (implemented in-app)
- ✅ Access/portability: full JSON export (`GET /account/export`).
- ✅ Erasure: hard delete (`DELETE /account`) cascades every user-owned row; verified by
  test that no user rows survive outside the append-only ledgers.
- ✅ Restriction-adjacent: per-session memory pause; pattern-level edit/delete.

## Residency & transfers
- 🟡 `DATA_REGION` config exists and is logged at boot; production must point at a KSA/ME
  region (operator verifies provider availability at deploy time).
- 🟡 Cross-border transfer assessment for LLM API traffic — counsel review required.

## Retention (defaults for counsel review — see README)
- User content: until user deletion (hard delete).
- `safety_events` / `audit_log`: 24 months, opaque subject IDs, append-only (DB-trigger
  enforced).
- Job rows: 90 days (automated purge in the worker).
- Report PDFs: stored artifacts follow user deletion 🟡 (operator to schedule artifact GC;
  DB rows already cascade).

## Accountability
- ✅ Append-only audit ledger for safety-relevant events and operator-facing flags.
- ✅ Crisis resources and referral directory are operator-verified data with hard boot
  gates against placeholders (N8).
- 🔴 Records-of-processing + DPO designation as applicable — operator/counsel.
