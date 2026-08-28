---
name: repository-activity-digest
description: >-
  Build evidence-linked GitHub project intelligence from issues, pull requests,
  reviews, commits, merges, closes, reopens, reverts, releases, and code-change
  signals. Use for scheduled repository monitoring, daily engineering
  intelligence, project-health reviews, contributor onboarding, opportunity
  discovery, or requests about activity and trends over 24-hour, 7-day, and
  30-day windows.
---

# Repository Activity Digest

Two steps of one command, and the division between them is the design.
`digest.py fetch` collects the evidence; `digest.py render` turns judgement into
the finished report. Between them you supply the judgement — which changes
mattered, which way a theme is moving, what to do about it — as structured
fields, and never as finished prose.

That split is not stylistic. A report composed freely from the evidence varies in
section set, in section order, in header shape and in its numbers, from one day
to the next, with nothing having changed but the run. The numbers are the part
that fails silently: an invented count reads exactly like a measured one. So
every number the report states is read by the renderer out of the run's own file,
and the findings format has no field to put a count in.

The section set is the renderer's for the same reason. Every section is written
on every run, and one that found nothing says so in a line of its own rather than
disappearing — so the only thing you decide is what this run found, never which
sections today's report should have.

Throughout, `<skill>` means this Skill's own directory — the one containing this
file. Resolve it to an absolute path before running any command below; the
scripts do not infer it.

## The reply is the delivery

**Whatever this run replies with is what the reader gets. There is no separate
send.** Write the report into the reply itself, as the whole reply, with nothing
before it and nothing after it.

Concretely, and each of these has been observed as a delivered message that
carried no report:

- **Never reply with a description of the report.** "The digest has been
  generated", an execution summary, a list of what was fetched, or a note that a
  file was written are all replies that leave the reader with no report.
- **Never name the file.** A path is input. It publishes the host's directory
  layout to whoever can read the channel, and the reader cannot open it.
- **Never say the report "will now be delivered", or that it "has been
  delivered".** Neither is an action available to a later step, because there is
  no later step; the reply ends the turn. A run that writes either sentence has
  replaced the report with a claim about it.
- **Never treat delivery as a missing tool.** A scheduled run does not hold a
  chat credential and does not need one — the host takes the reply and posts it.
  Looking for a posting tool, failing to find one, and writing the report to a
  file instead produces a file nobody reads.

A working file is fine as scratch, and belongs in the per-run directory the
fetch prints as `paths.run_dir`. It is never the deliverable. Do not invent a
scratch directory of your own: each command runs in a fresh shell, so a variable
set by one command is gone by the next, and a directory whose name was never
written down cannot be found again.

Two consequences of the same fact are worth stating on their own:

- **A scheduled run cannot confirm its own delivery.** The reply goes out after
  the turn has ended, so nothing inside the run can check whether it landed. An
  instruction of the form "after posting, do X" is unsatisfiable and simply never
  happens. Anything that must happen has to happen before the reply.
- **The window is consumed by the fetch, not by the reply.** The fetcher advances
  the watermark when it succeeds, before a single word of the report exists. A
  run that then declines to reply does not defer that window — it loses it, and
  the next run starts after it. **There is no failure that is improved by
  replying with nothing.** Report what you have, say what is wrong with it, and
  send it.

## Workflow

1. Determine the repository (`owner/name`), the daily window and the state-file
   path. A scheduled run is given all three by its prompt.

   **The state-file path is the only path this workflow types.** Both steps take
   it, both derive everything else from it, and it comes from the prompt rather
   than from a previous command's output — so it is copied once, from a fixed
   place, and never reproduced from memory.

2. Collect the evidence:

   ```bash
   python3 <skill>/scripts/digest.py fetch \
     --repo owner/name \
     --hours 24 \
     --mode updated \
     --history-days 30 \
     --detail-limit 5 \
     --state-file "<state-file the prompt names>"
   ```

   **Pass `--state-file` as an absolute path**, the one the prompt gives. A
   relative path is accepted and is anchored to the default project workspace
   rather than to the working directory — but the working directory of a
   scheduled run is not the one a person running the command by hand is in, and
   a relative path that resolves correctly is still a relative path nobody can
   verify by looking. Write it out.

   `--raw-output` overrides where the complete structure is written, resolved the
   same way, and `--summary-limit` sets how many records each stdout list keeps;
   the defaults suit a daily digest.

   `scripts/fetch_repository_activity.py` is the same program with the same
   options and still runs directly; `digest.py fetch` exists so the render step
   can be reached without naming a second path.

3. If the command fails, reply with what went wrong and stop. Nothing was
   committed by a failed fetch, so the next run repeats the window. If optional
   endpoints are incomplete, continue: the coverage warnings are carried into the
   report by the renderer and are not yours to drop.

4. Read the command's stdout. **It is the answer, not a pointer to one.** It is
   a summary, sized to be read directly; it is the evidence base for the report;
   and nothing has to be extracted from it, parsed out of it, or saved out of it
   before it can be used. Obey these rules without exception:

   - Use the paths under `paths` exactly as printed. Never construct, guess, or
     reuse a remembered path, and never read a state, report, or dump file the
     command did not name. These paths are long, and a single wrong character
     produces a command that fails for a reason nothing in it shows — the
     observed cost is a run that reissues the same broken command until the
     host stops it.
   - **Never re-run a command unchanged after it failed.** It cannot succeed the
     second time, and a host that watches for repeated identical calls will end
     the run rather than let it continue. Read the error, change something, and
     only then run again.
   - `paths.raw_output` holds the complete structure. It is far too large to
     read; when the summary is genuinely insufficient, filter that file with a
     script and read only the filtered result. Write that script with the
     file-write tool — `write_file`, or `edit_file` to amend one — and not with a
     shell heredoc or a `>` redirect: a script quoting a repository name or a PR
     title eventually meets an apostrophe or a parenthesis, which ends the
     shell's quoting early and turns the rest of the file into shell syntax, so
     the same command line fails identically however often it is retried. Write
     it into `paths.run_dir`, not into the working directory — a helper script
     left behind is picked up by the next day's run, which then follows it
     instead of this workflow. `paths.run_dir` is emptied at the start of every run, so
     nothing written there can reach the next one — and so nothing may be
     written there until the fetch has returned.
   - **Never write into `paths.run_dir` on the same command line as the fetch.**
     The fetch empties that directory as its first action, so a `>` redirect
     into it — on the fetch itself, or on anything piped from it — makes a file
     the fetch then deletes while it is still being written. The fetch refuses
     such a command line rather than performing it, and the refusal costs a
     whole fetch, which is the expensive half of the run. There is nothing to
     gain from one either: what a pipeline like that reaches for is already on
     stdout and already in `paths.summary`. The files this run writes are the
     ones named under `paths`; a name that is not one of them — a
     `template.json`, a `raw_data.json`, a saved copy of this output — is a file
     nothing here produces and nothing here reads. `template` and `paths` are
     keys of the document you are reading: read them where they are.
   - **Every name on stdout means the same thing in `paths.raw_output`**, under
     the same key and the same nesting, so a filter written from what you just
     read matches there. Only `summary_format`, `notes`, `template` and
     `paths.raw_output_bytes` are the summary's own. The raw file is the wider
     one: it keeps every record where stdout keeps a ranked extract, and it
     carries lists stdout only counts. `paths.summary` is this exact stdout
     document on disk, so a filter can be written against the file that was read.
   - A filter that returns `{}` or an empty list has **exited 0 and reported
     nothing wrong**. That is not evidence of a quiet window; check the name
     against `paths.summary` before concluding anything from an empty result.
   - `truncated` lists what was omitted from each summary list. Say a list was
     truncated rather than presenting it as the whole population.
   - Treat `generated_at_utc` as the report's own timestamp. If it does not match
     the intended report date, the data is stale: say so in the report rather
     than presenting old activity as current.

5. Read `<skill>/references/report-format.md` for the analysis method, and
   `<skill>/references/findings-schema.md` for the fields you are about to fill.
   When the destination is a chat channel, read
   `<skill>/references/slack-report-format.md` as well — it describes what
   survives delivery there.

6. Cluster related Issue, PR, Review, Commit, CI, Merge, Close, Reopen, Revert,
   and Release records into one change narrative instead of listing duplicates.
   `highlights` already carries review states, CI conclusions, changed files, and
   the latest discussion for the deeply inspected items.

7. Deep-read the 3-5 highest-impact clusters with available GitHub or web tools:
   inspect descriptions, relevant patches/files, review comments, maintainer
   replies, linked history, and CI. Do not call an item significant from its
   title alone.

8. Weight maintainer involvement, code depth, core-module impact, discussion
   intensity, persistence, merge status, and user impact — not raw item count
   alone. The counts are rendered for you; your job is what they mean.

9. Write the findings — the judgement half of the report — in the **output
   language**, and resolve that language once, before writing, in this order:

   1. the language the user explicitly asked the report to be in;
   2. `preferred_language` at the top level of the installation's `config.yaml` —
      `$JIUWENSWARM_HOME/config/config.yaml`, or `~/.jiuwenswarm/config/config.yaml`
      when that variable is unset;
   3. English, when neither of the above settles it.

   `preferred_language` is the setting this installation already uses to say
   which language its operator reads, so the report follows it rather than
   carrying a second, private notion of the same thing.

   The fetch prints the whole envelope on stdout as `template`: every key the
   renderer reads, with one worked example under each. **Copy `template` and fill
   it in.** Those keys are the entire document — nothing wraps them, and a key of
   your own beside them (a `generated_at_utc`, a `findings` holding the rest) is
   read as none of the schema, so the report renders with everything missing. The
   field names on the examples are the only names read, on every item as well as
   at the top level: a field name guessed at is not read, not rendered and not
   inferred from, and an evidence url written as `link` is dropped exactly as if
   no evidence had been gathered.

   **Every value in `template` is marked `PLACEHOLDER-REPLACE-THIS`.** Those are
   examples of the shape, not findings. Replace each with what this run measured,
   and delete any you do not replace: the renderer publishes nothing carrying that
   marker — it drops the entry and says so in the report — because an item you did
   not write is not a finding, and under a heading it reads exactly like one.

   `references/findings-schema.md` says what each field means, when
   `significant_changes` may be left empty, and what the renderer refuses.

10. Render and check in one command, passing the findings on the command itself:

    ```bash
    python3 <skill>/scripts/digest.py render \
      --state-file "<the same state-file path from step 2>" \
      --check-language \
      --findings - <<'JSON'
    { ... the filled-in template ... }
    JSON
    ```

    `--state-file` is the path the prompt gave, unchanged: the run directory,
    the activity file and the output path are all derived from it, exactly as
    the fetch derived them. Nothing here is copied out of the fetch's output.

    Passing the findings inline is what makes rendering before they exist
    impossible to express — writing them to a file first and then rendering has
    a gap between the two, and a render that lands in it fails on a missing file
    and sends the run looking for a path problem it does not have. Writing
    `findings.json` into `paths.run_dir` still works, and the renderer reads it
    when nothing arrives on the command — but write that file with the file-write
    tool, `write_file` or `edit_file`, and never with a heredoc redirected into a
    file or a `>` of your own text. The quoted heredoc above is safe because it
    feeds this command's stdin and ends at its own `JSON` line; the moment the
    same text is aimed at a file instead, an apostrophe or a parenthesis in a PR
    title ends the quoting early and the rest becomes shell syntax, which fails
    the same way every time the line is retried.

    `--run-dir`, `--activity` and `--findings <path>` all still work, and
    `scripts/render_report.py` still runs directly with the same options.

    Exit 0 is a finished report, **including when stderr lists reporting
    shortfalls**. An item that fell short of a report rule — a conclusion with no
    evidence link, an item with no title, a severity outside its vocabulary — is
    published carrying ⚠️ and named under a *Reporting Shortfalls* section. That
    report is the deliverable exactly as it stands: reply with it.

    Exit 2 means nothing was rendered: the findings are in another schema, `tldr`
    is empty, `significant_changes` is empty on a window the run measured activity
    in, or a filesystem path reached the text. `significant_changes` may be left
    empty only when every measure the run counted for the window is zero; the
    section then says so itself, and the refusal names what was counted when it
    was not. Exit 1 is
    a language finding, and the report was still printed: source text reached it
    in a language the reader was not promised. `UNGLOSSED` names text pasted from
    a source with no rendering; `LEADS` names a rendering that is missing or is
    behind its own original.

    **Fix the findings and render again.** Rendering is free and consumes
    nothing: the window was committed by step 2, and a second render neither
    re-reads GitHub nor moves the watermark. Never resolve a finding by deleting
    the item — the activity happened, and dropping it silently narrows the digest
    to whatever was convenient to write. The one thing to delete rather than fix
    is an example you never replaced: that is not a finding to lose. Never
    abandon the run over a render error; a report with one clumsy line beats no
    report at all.

    **Never re-run this command unchanged.** It cannot succeed the second time.
    Every message it prints names something in the findings, so the findings are
    what changes before the next attempt — and if you cannot see what to change,
    reply with the report you have rather than issuing the same command again. A
    host that watches for repeated identical calls ends the run, and a run ended
    there delivers nothing at all.

    Pass `--language` only when the report was explicitly asked for in a language
    other than the installation's, so the check follows the report.

11. Reply with the rendered text, exactly as the renderer produced it, as the
    entire reply. See "The reply is the delivery" above.

## Rules

- Use `updated` for daily intelligence; use `created` only for explicitly
  creation-focused reports.
- Prefer `GITHUB_TOKEN` from the environment. Never print or persist the token.
- Keep the state file outside the Skill folder so upgrades do not erase the
  watermark. The prompt names it; nothing this Skill emits repeats it.
- Pass the state-file path exactly as the prompt wrote it, to both steps. It is
  the only path this workflow types, so a character lost from it is the only path
  mistake left — and it is one that creates a directory rather than refusing.
- Keep every working file in `paths.run_dir`, and write it with a command of
  its own after the fetch has returned — the fetch empties that directory when
  it starts. The working directory of a scheduled run is shared with every other
  run on the host and is not cleaned between them.
- Never print `paths.raw_output`, `paths.state_file`, or any other filesystem
  path in the report. The renderer refuses one it can recognise, but it can only
  see what reaches it.
- Never paste an Issue title, PR title, commit subject, or comment into a finding
  in a language other than the output language. Put the rendering in `text` and
  the source's own wording in `original`; the renderer places them in the order
  the language gate checks. `original` is for wording the reader would otherwise
  not see, so leave it out when it would repeat `text` — the renderer drops a
  copy rather than printing a sentence after itself. Names keep their own
  Latin-script form and are not translated — see "Source text in another
  language" in `<skill>/references/report-format.md`.
- Mark important statements as **Fact**, **Inference**, or **Recommendation**,
  through the `label` field.
- Attach a PR, Issue, Commit, Release, Discussion, or CI link to every important
  factual conclusion. The renderer requires one on every significant change and
  every trend signal, and publishes the ones that arrive without it marked as
  unverified — so an omission costs the claim its standing with the reader
  rather than costing the reader the report.
- Separate explicit missing capabilities from inferred gaps. Give each inference
  high, medium, or low confidence and state its basis.
- Do not claim absence merely because no Issue was found.
- Distinguish small fixes, docs/dependencies, ordinary features, and core
  architecture work so volume does not hide impact.
- If no new activity matches, still report trend context and coverage. A silent
  run is indistinguishable from a broken one.
- Do not present private roadmaps, user adoption, or offline decisions as known.
- Do not narrate tool calls, data collection, intermediate reasoning, or report
  construction, in the findings or in the reply.

## Scheduled use

Nothing here schedules anything: a digest is always triggered by a prompt, and
whether that prompt is pasted by a person or handed to the run by a scheduler is
the host's business.

A scheduling prompt carries what the deployment knows and leaves every procedure
to this file, which the model reads on demand: the repository, the daily and
history windows, the absolute state-file path, the audience, and this Skill's
name. Keep host paths, channel ids and repository names there — they are
deployment values, and none of them belongs in this Skill's scripts.

Two host properties decide whether a scheduled digest arrives at all, and both
are worth establishing before trusting one:

- **Whether the reply is the delivery.** On a host that sends the reply after the
  turn ends, it is, and everything under "The reply is the delivery" applies. A
  host that instead hands the run a posting tool and reports the result back
  wants the opposite shape, and this Skill's workflow is the wrong one for it.
- **Whether a scheduled result reaches the channel at top level.** Where the host
  offers such a setting, turn it on for a recurring channel report: the marker
  described in `<skill>/references/slack-report-format.md` then keeps the brief
  in the channel and puts supporting detail in the brief's own thread, and
  without it the whole report is flattened into one message inside the thread the
  job was created from.

## References

- `<skill>/scripts/digest.py` — `fetch` and `render`, both anchored to the state
  file. `--help` prints the two commands. The scripts it calls,
  `fetch_repository_activity.py` and `render_report.py`, still run directly with
  every option they have always taken.
- `<skill>/references/report-format.md` — the analysis method, the impact
  ranking, and the rule for source text in another language.
- `<skill>/references/findings-schema.md` — every field the renderer accepts,
  what it requires, and what it refuses.
- `<skill>/references/slack-report-format.md` — what a chat destination does and
  does not render, and the marker that splits brief from detail.
