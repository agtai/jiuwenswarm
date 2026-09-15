# Spoken expense amount correction

User scope: an explicit correction of a line in the current Paris draft updates
the bound form, recalculates totals/policy, publishes matching claim.json/claim.md
and invalidates old submission consent. It does not submit or create another
voice task. Immutable ledger reports are preserved via a linked corrective
mandate; task and original form IDs stay the same.

Tier 3 local host callback extension (`adjust`); existing authenticated loopback
binding applies. Native operation schema remains task.adjust with its existing
adjustment string, carrying a closed JSON amount-edit payload. Tier 2 form
reservation and side effects: exact hash, draft status, stable unique line ID,
finite nonnegative two-decimal amount; editing blocks submission and other edits.
Files publish only through the existing mandate gate, with versioned receipts.
Partial failure blocks submission (edit_failed) instead of claiming success.
Stale/wrong-target/invalid edits have zero mutation. Lost outcome requires a
read of authoritative details, never a blind retry. Submitted forms are excluded.
Native task adjustments, weather, cancellation and demo parallelism are excluded.

Evidence (2026-09-15):
- Real Python Bridge + authenticated HTTP callback + gate publication flow:
  dinner EUR86.50 -> EUR80, total EUR1376.40, both artifact contents checked,
  stable form/task ID, stale confirmation refused and new confirmation submits.
- Bridge/expense/combined regression: 25 passed; one pre-existing Windows POSIX
  file-mode assertion excluded (config_pair_and_close, 0666 versus 0600).
- Desktop business/local-server: 24 passed including actual Python Bridge;
  TypeScript build, scoped ESLint and formatting passed.
- Swarm Atlas host/approval: 29 passed; updated same-turn edit/approval fence
  checked again with all 23 approval tests. Native tools/instructions: 98 passed.
- Invalid values, unknown line, stale snapshot, already submitted, parallel edit,
  patch/reset during reservation, and partial publication failure verified.
  Partial publication leaves edit_failed and suspends the corrective mandate.
- Independent read-only review found stale historical summary and patch/reset
  reservation bypass. Both fixed, regressions added, reviewer verified closure.
  Current form facts always override historical adjustment summaries.
- New amount requires a subsequent explicit user answer, not the edit turn.

Usage: after the Paris draft is ready, say "把晚餐报销金额改成80欧元".
The model reads the exact line/hash, edits the same task, and asks about submitting
its new total. Ambiguous expenses require clarification. Already submitted claims
cannot be reopened by this tool. A receipt remains inspectable in task.details.
These tests do not constitute microphone/Provider audio acceptance. No weather,
cancellation, or parallel-demo execution changes. No remote push in this change.

