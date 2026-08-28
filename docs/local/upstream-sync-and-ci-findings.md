# Upstream sync and CI: what actually reaches `develop`, and what silently does not

Written 2026-08-27, before the machine migration. Nothing here has been applied
and nothing here is a change to our own code -- it is a record of how the
upstream pipeline behaves, so that decisions about what to file and how to chase
it are not re-derived from scratch each time.

Measured 2026-08-26 and 2026-08-27 against `openJiuwen-ai/agent-core` (GitHub)
and `openJiuwen/agent-core` (GitCode). The two are one project kept in sync in
both directions; the mirror bot writes a `Paired:` line into every body naming
the counterpart, which is how origin can be told after the fact.

Findings are separated from inference throughout. Several conclusions here rest
on the *absence* of a signal rather than on an error message, and where that is
so it is said explicitly.

---

## 1 · A merge reassigns authorship, and the rule is not the obvious one

Upstream lands a pull request as a single squash commit whose `author` and
`committer` are both `openJiuwen-bot <cla@openjiuwen.com>`, with no
`Co-authored-by` and no `Signed-off-by`. The contributor's name is not anywhere
in the resulting commit object.

Verified on `51c55c33` (from our PR #365): one parent, and a diff byte-identical
to the authored commit -- `git patch-id --stable` gives
`106370cd4b20bd7134bcae989abde4cffe29d486` for both `51c55c33` and the head
commit `96c6c50e`. The content survived intact; only the identity did not.

**The rule is not "GitHub-origin loses the author".** GitCode's squash resolves
the head commit's author **email** to a GitCode account and writes that
account's identity into the landed commit: the email is preserved, the display
name is replaced by the account login. With no account bound to that email it
falls back to the CLA bot.

Both halves of that were confirmed directly against GitCode's own API, which
exposes the resolution it performed:

| case | authored as | GitCode resolved | landed as |
| --- | --- | --- | --- |
| `20e35736` (MR !2428) | `yangyuan <…@huawei.com>` | login `yyuse` | `yyuse <…@huawei.com>` |
| `839fe1f8` (MR !2455) | `xiajing <…@huawei.com>` | login `hwxiajing` | `hwxiajing <…@huawei.com>` |
| `8535d0f8` (MR !2456) | `weichenhao <…@qq.com>` | `author: {}` -- nothing | `openJiuwen-bot <cla@openjiuwen.com>` |

In the second row the resolved account's own display name is a Chinese one, and
the landed commit uses neither it nor the authored name: it writes the account
**login**. So the identity that survives a merge is an account handle on a
platform the GitHub-side contributor may not have.

The empty `author` object in the third row is the mechanism in plain sight: no
bound account, so no identity to write, so the bot.

Counts over the last 40 commits on `develop`, classified by the bot metadata
block in each body (`bot1-mirror-meta` = mirrored from GitHub, `source: gitcode`
= native GitCode):

| origin | author kept | author replaced |
| --- | --- | --- |
| GitHub | 0 | 3 |
| GitCode | 32 | 3 |
| neither marker | 2 | 0 |

All three GitCode-origin exceptions are the same contributor using a `@qq.com`
address, consistent with the table above. GitHub-origin loses the author every
time not because of its origin but because a GitHub fork's commit email is
never bound to a GitCode account.

This is long-standing rather than a regression. **File it against GitCode's
squash-merge author resolution, not against the mirror bot** -- the mirror bot
relays the commit faithfully, as the patch-id equality shows.

## 2 · The PR body becomes the commit message, and the authored message is discarded

Verified across the last 20 commits on `develop`: every one carries its PR
body verbatim, with the subject taken from the PR title. The message the
contributor wrote on the commit does not survive. Eighteen of the twenty
reproduce the full PR template, checkbox list and HTML comments included; the
two that do not are simply PRs whose authors wrote a custom body, which lands
just as verbatim.

For a mirrored PR this is worse than it sounds, because the message that lands
is the *mirror MR's* description, which the bot composed. `51c55c33`'s commit
message contains the mirror header, the `Paired:` line, and the entire
`bot1-mirror-meta` block -- `github_pr`, `head_repo`, `head_ref`, `head_sha`,
`base_sha`, `github_user` -- before it reaches any prose the author wrote.

Separate defect from the author reassignment, though they share a cause: both
are the squash step taking its inputs from the wrong place. Worth filing
separately, since fixing one does not fix the other.

Practical consequence for us: a PR body is not a description of a change, it is
the change's permanent commit message. That is the reason PR bodies must not
enumerate commits -- the squashed message is all that reaches `git blame`.

## 3 · Mirrored issue state is not evidence of the issue's real state

GitHub #250 was created and closed by the bot three seconds apart, with zero
comments and no human action in between, while its GitCode original (issue 1011)
is open, assigned, and priority 1. A second mirrored pair checked the same day
behaved correctly, so this is an anomaly rather than the norm.

The consequence is what matters: **the mirror's copy of an issue cannot be used
to determine whether that issue is open.** Check the GitCode side before
concluding anything from a closed mirror.

## 4 · The bot edits filed text after the fact

It rewrites `#792` to `#<U+200B>792` -- a zero-width space after the hash --
inside issue bodies, presumably to stop GitHub auto-linking a number that means
something on the other platform.

This is not cosmetic for anyone editing that text. A patch generated against a
locally held copy of a body failed on 2 of 14 hunks against the live body while
applying cleanly to the local copy, because the invisible character had been
inserted in the interval.

**Always generate a patch against a freshly fetched body, and re-verify against
a fresh fetch immediately before applying.** The failure mode is silent
otherwise, and the diff that explains it is not visible on screen.

## 5 · The bot harvests issue references into closing keywords

Any issue number mentioned anywhere in prose becomes a `Fixes` line. PR #960
acquired `Fixes #250 #470 #501 #831` within minutes of filing; it fixes none of
them. Backticked placeholders are not harvested, which is the only reliable way
to write a number without claiming it. Removal reportedly does not stick.

Consequence for drafting: assume every bare issue number in a PR or issue body
will be turned into a closing keyword, and write accordingly.

## 6 · CI runs on GitCode and reports back as GitHub comments

The bot posts `bot2-ci-writeback` comments carrying a results table with the
stages `静态检查`, `禁用词扫描`, `防投毒检查`, `开源合规检查`, `UT测试`,
`ST测试`, `build`, `ruff codecheck`.

The label lifecycle on the GitHub side is split across two bots:
`openjiuwen-ci-bot` applies `ci-running`; `openjiuwen-collaboration-bot` later
posts the results, removes `ci-running` and applies `ci-successful` or
`ci-failed`.

The healthy GitCode-side sequence, observed end to end on `!2537` and `!2538`:
MR created → t+2s approvers assigned → t+4s sig label → t+8s
`openJiuwen-cla/no` → t+17s `openJiuwen-cla/yes` → t+50s `openJiuwen-bot` posts
a pipeline comment **and** adds `ci-running` on GitCode → t+~10min the results
table. The pipeline number equals the MR number.

Note that "completed" and "passed" are different things: `!2537` and `!2538`
both completed, and both completed as `ci-failed`. Completion is the property
under discussion in the next section, not success.

## 7 · `ci-running` on GitHub does not mean a pipeline is running

This corrects the reading that a pipeline "stalls indefinitely". **No pipeline
was ever created in these cases.**

`openjiuwen-ci-bot` stamps `ci-running` on the GitHub PR about ten seconds after
the GitCode mirror MR is created, and consistently *before* any pipeline starts.
Measured on PR #960: PR opened `09:08:42Z`, mirror MR `!2530` created
`09:10:46Z`, `ci-running` applied `09:10:57Z` -- eleven seconds after the mirror,
and on a mirror that has never carried a CI label of any kind. The label means
"handed off to GitCode", not "a pipeline is running", and there is no path by
which it is removed if the handoff leads nowhere.

So `ci-running` for four hours reads as: the mirror was created and nothing ever
reported back.

Three independent absences confirm that `!2530` had no pipeline:

- its GitCode `operate_logs` carry **no `ci-*` label at any point** -- nine
  events, all within twenty seconds of creation, nothing since;
- no `openJiuwen-bot` comment of the form "The pipeline(pipeline number:2530) is
  running", which working MRs do get;
- no artifact under the CI artifact bucket path for `ut/2530`, while `ut/2536`
  through `ut/2539` are present. Note that this check needs the exact object
  path, taken from a writeback comment's link: the bucket denies listing and
  answers `403` to a guessed path whether or not the object exists, so a
  `403` on its own proves nothing.

**This was inferred from three absences and never from an error message.** No
component reported a failure; the finding is that nothing reported anything.

The finding to record is therefore: **the GitCode-side CI trigger intermittently
drops MR events, and nothing retries.** Roughly 8 genuine misses in 400 MRs
surveyed -- about 2% -- and they clump rather than scattering evenly.

For scale on the normal case: across 87 sampled PRs by other authors the median
time to completion is 12 minutes, p90 is 26, and none exceeded 34.

### Two explanations that look likely and are refuted

Worth recording so they are not re-derived.

- **Base staleness is not the cause.** 51 PRs on a stale base got CI normally,
  and five PRs sharing the identical parent `dce36fc8` completed in ten minutes.
- **It is not per-author, not mirror-specific, and not burst-related.** `!2525`
  is a **native, non-mirror** MR by a different author, filed in isolation on the
  same day. Its full bot chain ran -- approvers, sig label, CLA -- and no
  pipeline followed. Four `operate_logs` events, none of them a CI label.

`!2540`, the fresh mirror created by #970's force-push, is another instance: no
CI label, at roughly twelve times the normal trigger latency.

### A different failure that looks the same from GitHub

PR #808's mirror `!2442` carries **only** the `github-mirror` label -- no sig
label, no CLA label at all. The entire bot chain failed there, not just the CI
trigger. Six events, four of them description edits.

That matters because from the GitHub side #808 looks like the same "stuck in
`ci-running` for days" case, and it is not. The remedies differ.

## 8 · A conflicted PR is never mirrored and never queued

PR #970 carried the `conflicted` label, had no GitCode counterpart, no
`ci-running`, and zero bot comments of any kind. After a force-push resolving
the conflict it was mirrored as a **new** MR -- `!2540`, outside the
`!2530`–`!2535` block its siblings occupy -- and `ci-running` appeared on the
GitHub side.

So a PR that looks stuck has at least two distinct causes, and they need
different remedies: a conflicted PR needs the conflict resolved before anything
will happen at all, while a mirrored-but-untriggered PR needs a new head sha.

## 9 · There is no way to ask for a retry

The community bot's documented command set is `/check-pr`, `/check-cla`,
`/cla cancel`, `/lgtm`, `/approve`, `/close`, `/reopen`, `/rebase`, `/squash`.
**There is no `/retest` and no `/recheck`.**

A new head sha re-triggers the pipeline, so **pushing a trivial commit or a
force-push is the only retry available from our side.** Anything else requires a
maintainer to trigger the pipeline manually.

This is the most actionable line in this note. Given section 7 -- a ~2% silent
drop rate with no timeout and no writeback -- a re-push is not a workaround for
an unusual situation, it is the routine response to a run that has not reported
within the p90 of 26 minutes.

## 10 · Observability, and why this cost hours

GitCode's pipeline internals are not visible anonymously.

- `api.gitcode.com/api/v5` serves MR data, comments and `operate_logs`, and is
  the one genuinely useful surface -- `operate_logs` is where the label
  lifecycle can be read event by event, with timestamps.
- It has **no CI surface**: every checks, pipelines and statuses endpoint 404s.
- The pipeline page is an empty SPA shell.
- The CI host `openlibing.com` returns HTTP 418 from its WAF.

What is observable is the bot lifecycle on the MR, plus the CI artifact bucket.
Everything in section 7 was assembled from those two.

The compounding problem is that **the false `ci-running` signal on GitHub makes
a never-started pipeline indistinguishable from a running one**. That is worth
stating as its own defect rather than as a footnote to the trigger drop: even a
correct fix to the trigger would leave the observer unable to tell the two
apart, and the label is applied by a bot that knows perfectly well it has only
performed a handoff.

## 11 · `href="None"` in the results table is usually cosmetic

`ruff codecheck` reports SUCCESS with a null link on all 79 observed
occurrences, because on success there is nothing to link to. Treat it as
expected.

One genuine anomaly exists: `静态检查` reported FAILED with a null link on a
single PR, 1 of 8 such failures. A single instance is not a pattern, and it is
recorded here only so that the next occurrence can be counted rather than
rediscovered.

---

## Recommendations

Everything above was measured or, where stated, inferred from absence. The
following are proposals.

1. **File the author reassignment against GitCode's squash-merge author
   resolution.** The evidence to lead with is the resolution table in section 1
   -- an empty `author` object next to a populated one, with the two landed
   commits alongside -- rather than the counts, which invite an argument about
   sampling.

2. **File the commit-message substitution separately.** Same squash step,
   different input, and the fix for one is not the fix for the other. The
   strongest single exhibit is a landed commit whose message contains the bot's
   own `head_sha` metadata block.

3. **Treat a run with no writeback after ~30 minutes as dropped, and re-push.**
   That is inside the observed p90 and there is no cheaper signal to wait for.
   Do not wait days; nothing is going to arrive.

4. **Before concluding a PR is stuck on CI, check the GitCode side's
   `operate_logs`.** It distinguishes the three cases in one call: a full bot
   chain with no CI label (trigger dropped), only `github-mirror` (whole chain
   failed), and no MR at all (conflicted, never mirrored).

5. **Consider reporting the false `ci-running` label as its own issue.** It is
   the cheapest of the three to fix -- the bot could stamp a distinct
   "mirrored" state and let the CI bot own `ci-running` -- and it is what makes
   the underlying drop invisible.
