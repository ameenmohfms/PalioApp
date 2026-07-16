# Versioned screening instruments

Populated in Phase 3: `asrs_v1_1.{en,ar}.json`, `phq9.{en,ar}.json`, `gad7.{en,ar}.json`.

Rules (spec §7, Hard Rule A3):
- Item text is stored verbatim with a `source` provenance citation and rendered verbatim in
  fixed UI cards. The conversation wraps the instrument; it never rewrites it.
- Arabic files remain `"placeholder": true` until the operator supplies clinically verified
  translations (spec §16 #2). Placeholder-flagged instruments are not offered to users.
- Scoring rules ship with each file and are unit-tested against published test vectors.
