### Automated EngineVerse Learner Vault Sync — redacted 2026-10-19

This issue was opened on 2026-10-16 by the pre-fix static-copy sync flow, which
embedded a learner snapshot **including credential material** in the issue body.

The body has been **redacted** under `docs/INCIDENT_RESPONSE.md` (credential
posted in a public issue/comment). Editing this issue is containment, not
erasure: GitHub may retain edit history and the value may have been copied while
it was visible, so the exposed password is treated as permanently public.

No data from this issue was merged into `data/learners/registry.json`. Current
code strips credential fields from snapshots
(`github_storage.validate_snapshot`), the sync workflow requires a maintainer
dispatch, and the browser runtime no longer adopts credential hashes from
pulled snapshots.
