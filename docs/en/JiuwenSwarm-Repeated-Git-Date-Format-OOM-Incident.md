# JiuwenSwarm Repeated Git Date-Format OOM Incident

## 1. Summary

After a user submitted a natural-language request in JiuwenSwarm to check the date of the latest commit, the Agent generated and executed the following command:

```text
git log -1 --format=%ad --date=format:'%m月%d日'
```

When Git for Windows ran this command, its memory usage kept growing until it returned:

```text
fatal: Out of memory, realloc failed
```

After JiuwenSwarm received the first failure, the Agent did not change the command or stop. Instead, it invoked the same tool again with the same arguments. A single user request ultimately produced 11 `tool_call` events: 10 returned the same OOM failure, and the 11th was manually cancelled while it was running. The request never produced a final answer.

The incident contains two consecutive but distinct behaviors:

1. A single Git process repeatedly expands an internal buffer until it runs out of memory and exits with one failure.
2. After JiuwenSwarm receives that failure, it starts a new Git process with the same command, causing multiple independent OOM events.

The earlier commands did not merely fail normally with only the final attempt reaching OOM. The very first execution already ended in OOM; every later invocation repeated the same OOM-producing command.

## 2. What Happened

The user's original intent was to inspect a commit date. In the text delivered to the Agent, the Chinese phrase for “year, month, and day” (`年月日`) had been transcribed as the similar-sounding `念月日`. The model then chose a Git date format containing literal Chinese characters.

The model used for this request was `gamma4`.

The complete sequence was:

```text
The user submits one date query
→ JiuwenSwarm sends the request to the Agent
→ The model generates a Git command containing the Chinese “month/day” literals
→ Terminal Tool starts a Git child process
→ The Git child process repeatedly expands an internal buffer
→ Git runs out of memory and exits with a non-zero status
→ Terminal Tool returns the failure to the Agent
→ The model selects the same tool with the same arguments again
→ JiuwenSwarm starts another Git child process
→ The same OOM occurs again
→ The 11th invocation is manually cancelled while running
```

Observed results:

- User requests: 1
- `tool_call` events: 11
- Completed calls returning the same failure: 10
- Final answers: 0
- One abnormal Git child process reached approximately 8.5 GB Working Set / 49 GB Private Memory
- The resources were released after the Git process exited
- The command did not modify the repository; the working tree remained clean

## 3. Single-Process Git OOM vs. Repeated JiuwenSwarm Invocations

### 3.1 Inside the Git Process

Running the problematic command once in a standalone terminal reproduces the same OOM. One command starts one Git process. That process repeatedly attempts to expand an internal buffer until memory allocation fails, then prints one OOM error and exits.

```text
Git process 1
→ Repeated internal buffer growth
→ OOM
→ Return one failure
→ Process exits
```

### 3.2 JiuwenSwarm Agent Loop

After JiuwenSwarm receives the failure from the preceding Git process, the model issues the same tool call again. Each tool call starts a new Git process, and each process independently repeats the internal buffer growth and OOM sequence.

```text
Git process 1: internal growth → OOM → exit
Git process 2: internal growth → OOM → exit
Git process 3: internal growth → OOM → exit
…
```

Git's internal buffer growth explains why one command runs out of memory. JiuwenSwarm's repeated invocations explain why the same OOM occurred ten times.

## 4. Independent Reproduction and Controls

Problematic command:

```text
git log -1 --format=%ad --date=format:'%m月%d日'
```

Control commands:

```text
git log -1 --format=%ad --date=short
git log -1 --format=%ad --date=format:'%Y-%m-%d'
```

The following behavior was observed on Git for Windows `2.47.1.windows.2`:

| Item | Non-ASCII `format:` | `--date=short` / ASCII `format:` |
|---|---|---|
| Returns a date | No | Yes |
| Process memory | Grows continuously and abnormally | Normal |
| Final result | `fatal: Out of memory, realloc failed` | Succeeds immediately |
| Reproduces outside JiuwenSwarm | Yes | No abnormal behavior |

This shows that the direct execution-layer cause of the first OOM is not JiuwenSwarm: the same command still causes the Git child process to run out of memory when executed outside the Agent. JiuwenSwarm's problem is that it continues executing after receiving an explicit, identical failure.

## 5. Role of the Input Text

The transcribed phrase `念月日` is not passed directly to Git and does not directly trigger the failure. It is only natural-language context seen by the model when generating the command.

Git actually receives:

```text
--date=format:'%m月%d日'
```

The change from `年月日` to `念月日` can therefore only be considered a factor that may have influenced command selection, not the root cause of the OOM. Even with perfectly transcribed input, the model could still choose the same Chinese date format on its own.

## 6. Assessment of the Git OOM Mechanism

The current evidence most closely matches this execution path:

```text
Git DATE_STRFTIME date mode
→ strbuf_addftime(...)
→ C Runtime strftime(...)
→ Repeatedly returns 0 in the current environment
→ Git interprets 0 as an insufficient buffer
→ Expands the buffer and calls strftime again
→ The buffer repeatedly doubles
→ xrealloc eventually reports OOM
```

Git's custom `format:` date path enters `strbuf_addftime`. This implementation calls `strftime` and expands the buffer when the return value is 0. Microsoft CRT documentation states that `strftime` returns 0 when the buffer is too small, and that invalid-parameter paths may also return 0.

If the non-ASCII or locale conversion used by Git for Windows keeps returning 0 in the current environment instead of succeeding after the buffer grows, Git will continue expanding the buffer until `xrealloc` reports OOM.

This mechanism explains why a single standalone execution also runs out of memory, but the exact low-level branch that continually returns 0 has not yet been identified.

## 7. What the Incident Exposed in JiuwenSwarm

Git OOM is the direct execution-layer fault, but the incident became severe inside JiuwenSwarm because the failure did not converge promptly:

- One user request continued producing the same tool call after the first deterministic failure
- The tool name, execution arguments, and complete failure result did not change
- Repeated execution added no new information and did not move the Agent closer to a correct answer
- Every retry started another Git child process capable of consuming a large amount of memory
- The request still had not ended or returned a readable final error after 10 failures
- The 11th invocation ultimately had to be cancelled manually

At the time, the project already contained a tool-loop detector, but the general Circuit Breaker was not enabled by default. Even if enabled, the existing default error threshold would have acted too late for a failure capable of consuming substantial resources during a single invocation. Terminal Tool also lacked sufficiently strong memory, timeout, and process-tree limits for an individual child process, allowing the first invocation alone to place visible pressure on the machine.

From JiuwenSwarm's perspective, this was more than “Git returned an error normally.” A reproducible OOM in an external tool was repeatedly amplified by the Agent loop, and the system did not end the request within a reasonable number of attempts.

## 8. Layered Assessment

| Layer | Observed behavior | Relationship to the JiuwenSwarm issue |
|---|---|---|
| Input text | `年月日` became `念月日` | May have influenced command selection; does not directly trigger OOM |
| Model (`gamma4`) | Generated a non-ASCII date format and selected the same command again after receiving the failure | Determined both the trigger condition and the repetition strategy |
| Git for Windows | A single process expanded its internal buffer until OOM | Direct execution-layer cause of the first and every independent OOM |
| Terminal Tool | Returned an explicit failure, but one process could consume substantial resources | Exposed insufficient child-process resource boundaries |
| Agent Runtime | Did not stop after repeated identical tool calls, arguments, and failures | Amplified one external-tool failure into multiple OOM events |

## 9. Confirmed and Unconfirmed Findings

### Confirmed

- The problematic Git command reproduces the OOM outside JiuwenSwarm
- `--date=short` and ASCII date formats work normally
- One Git child process grows abnormally and exits with OOM
- One JiuwenSwarm user request produced 11 identical tool calls
- The 10 completed calls returned the same failure; the 11th was manually cancelled
- JiuwenSwarm did not produce a final answer promptly after repeated deterministic failures
- Resources were released after each process exited, and the repository was not modified
- The model used for the request was `gamma4`

### Unconfirmed

- The exact internal location at which `strftime` continually returns 0
- The respective responsibility of Microsoft CRT, MSYS/locale conversion, and Git for Windows adaptation code
- The `errno` value and internal locale state for each `strftime` call
- Under what condition or after how many invocations the Agent would stop without manual cancellation

## 10. Conclusion

The incident can be summarized accurately as follows:

> A single natural-language request in JiuwenSwarm, processed using the `gamma4` model, triggered a non-ASCII date-format OOM that is independently reproducible in Git for Windows. The first Git invocation already ran out of memory. After receiving the same failure, JiuwenSwarm repeatedly started the same command, amplifying one external-tool fault into ten completed OOM events and one in-flight invocation, without ever producing a final answer.

The direct OOM belongs to the Git for Windows execution path. Repeating the same deterministic failure while continuously starting high-resource child processes is the core JiuwenSwarm issue exposed by this incident.

## 11. References

- [Git `date.c`](https://github.com/git/git/blob/master/date.c): path through which custom date formats enter `strbuf_addftime`.
- [Official mirror of Git `strbuf.c`](https://kernel.googlesource.com/pub/scm/git/git/+/a066a90db68da5262e81e74a50d18eaeddc6783f/strbuf.c): `strftime` and buffer-growth logic in `strbuf_addftime`.
- [Microsoft `strftime` / `wcsftime` documentation](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/strftime-wcsftime-strftime-l-wcsftime-l?view=msvc-170): return values, insufficient-buffer behavior, and invalid-parameter behavior.
