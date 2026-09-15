# Atlas presentation and consumed decisions (2026-09-15)

Scope: repair the user-observed English executor prose leaking into voice chat,
contradictory expense wording, consumed approvals reported as expired, and
question/answer reordering. Baselines: Atlas 83deb44; Swarm 66e50148.

Tier 2: decision recovery is read-only when no gate remains; the existing exact
revision, snapshot, per-turn gate and callback validation remain on mutations.
No new authorization, protocol, executor or financial transaction is introduced.
No model-driven amount editing is added: conditional edits must not be reported
as applied or turned into a new claim; the existing form remains the edit surface.

Owned surfaces: Atlas chat reducer/shell, both Atlas form-pending projections,
Swarm local host receipts and shared response instructions, focused regression
checks. Detailed source records, policy exceptions and on-demand environment
facts remain available. Default presentation uses form status, not environment
labels. Native executor routing and audio transport are unchanged.

Acceptance: voice executor prose is inspectable but not a second chat answer;
text-only replies, approval cards and files continue to work. Late transcription
and execution binding preserve causal question/answer order. Repeated decisions
return current facts with zero decide effects, including completed, declined and
lost-receipt cases. Changed pending decisions still reject with zero effects.
Language comes from microphone input, not backend prose. No claim of new real
Provider/audio acceptance is made from deterministic checks.

Verification:
- Swarm: atlas_approval, atlas_local_host, atlas_voice_style and native_business_tools:
  129 passed with pytest --no-cov (2026-09-15).
- Atlas workbench live-voice + superapp-state: 34 passed. Covers delayed text
  acceptance during voice, source output retained in details, causal ordering,
  user interjections and withdrawn segment lifecycle.
- Desktop live-voice-business: 20 passed, plus the opt-in actual Python bridge
  integration passed separately with JIUWEN_WORK_PYTHON configured.
- Python bridge test_live_voice: 7 passed; existing test_config_pair_and_close
  fails on Windows because stat().st_mode reports 0666 rather than POSIX 0600.
  That credential-permission assertion is outside this presentation repair.
- TypeScript typechecks, scoped ESLint, core/workbench/desktop builds passed;
  Vite reports its existing large-bundle advisory.

Independent complete-diff review by presentation_review found an early text
acceptance race and a segment-cache lifecycle problem. Both were corrected:
raw segments remain untouched and only rendering is filtered; text acceptance
resolves temporary origin classification. The focused follow-up review found
no remaining blocking issue. No live Chinese audio acceptance is claimed;
provider phrasing requires the user's real conversation.

No existing order, claim or approval was modified by deployment or tests.
Conditional amount adjustment remains an explicitly unsupported voice edit,
not a silently successful edit or replacement task. This is a limitation of the
existing form execution interface, separate from consumed-decision recovery.
