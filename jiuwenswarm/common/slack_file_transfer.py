# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""One host and three limits, for pulling a file's bytes out of Slack.

Two subsystems fetch files from Slack with the bot token attached, and they have
almost nothing else in common. The connector downloads what somebody attached to
an inbound message, before any model has seen it. The runtime's history toolkit
opens a file the model named by id, after a membership gate has decided it may.
Different triggers, different callers, different vocabularies for refusing --
and exactly the same four decisions about the transfer itself: which host may
receive the credential, how many bytes are worth pulling down, how long any one
network operation may take, and which characters may reach a path.

**Why the four live here rather than in either caller.** The toolkit must not
import the connector: ``slack_connect`` pulls in ``slack_bolt``, so importing it
from a harness tool would drag the gateway's dependency tree into the runtime
and invert the layering. That constraint is real, and for a while the answer to
it was a documented copy of each value in the toolkit with a comment asking the
next reader to keep the two in step. But ``jiuwenswarm/common`` sits below both
layers and both already import from it -- ``slack_history_policy`` is the same
shape of thing, written once and read by the connector, the cron scheduler and
the toolkit alike -- so the copies bought nothing the layering did not already
allow, and cost the one guarantee that matters most for the first of them.

That first one is why this module exists and not merely why it is tidy.
``SLACK_FILE_HOST`` decides which host may be sent a live workspace credential.
A security boundary with two definitions and nothing asserting they agree is
drift waiting to happen in the one place drift is expensive: the copy that is
never edited is the copy that stays right, and there is no telling in advance
which of two that will be. Written once, the question cannot be answered two
ways.

What is deliberately *not* here: ``_safe_path_component`` and ``_https_host``,
which both callers also keep local copies of. Those are small pure functions
rather than shared decisions -- two unrelated subsystems arriving at the same
ten lines is a different thing from two subsystems that must agree on a value --
and each is documented as a copy where it stands.
"""

from __future__ import annotations

import re

#: The only file host Slack serves its own uploads from. ``url_private`` on a
#: hosted file is ``https://files.slack.com/files-pri/<team>-<file>/<name>``,
#: and ``url_private_download`` is the same with ``/download/`` inserted.
#:
#: Not the whole allow-list, and each caller widens it the same way: the
#: workspace's own host -- ``auth.test``'s ``url``, which is
#: ``https://<workspace>.slack.com/`` -- is accepted beside it, because that is
#: where ``permalink`` lives and a deployment may be served its files from
#: there. Two entries and no wildcard: a suffix match on ``.slack.com`` would be
#: a rule about a string rather than about a host Slack itself named.
#:
#: Nothing else is accepted. The reason is what the check exists for. For
#: an *external* file (``is_external: true``, ``mode: "external"``) Slack fills
#: ``url_private`` in with the URL whoever registered the file supplied. A real
#: ``files.remote.add`` record reads ``"url_private":
#: "https://docs.google.com/document/d/..."`` -- a host chosen by the poster,
#: not by Slack. Attaching the bot token to that as a bearer header hands the
#: live credential to whoever chose the URL, and anybody who can share an
#: external file into a channel the bot is in can choose it.
SLACK_FILE_HOST = "files.slack.com"

#: Matches ``media_attachments``' ceiling for browser uploads. Slack itself
#: allows 1 GB, which is not something to pull into a session directory
#: unprompted.
MAX_FILE_BYTES = 30 * 1024 * 1024

#: Passed to httpx as a single value, which sets connect, read, write and pool
#: alike. It bounds each individual operation and nothing more: the read timeout
#: is measured per chunk, so a transfer that keeps trickling bytes in never
#: trips it however long it runs. A caller that needs the *whole* wait bounded
#: has to say so separately, and both of them do: the connector with a phase
#: budget measured across every attachment on one message, the toolkit with a
#: budget over the single transfer it was asked for. Each is holding a request
#: open while it fetches, and neither can get that guarantee from this value.
#:
#: Those two budgets are theirs and are not shared here. This value is shared
#: because the two callers must not answer it differently; how long each of
#: them is willing to hold its own caller waiting is a question they are
#: entitled to answer differently, and they do.
FILE_TRANSFER_TIMEOUT_SECONDS = 60.0

#: Path components are built from Slack-supplied names, which are user input and
#: arrive with directory separators, spaces and non-ASCII intact, so everything
#: outside this set is replaced rather than trusted.
UNSAFE_PATH_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")

__all__ = [
    "FILE_TRANSFER_TIMEOUT_SECONDS",
    "MAX_FILE_BYTES",
    "SLACK_FILE_HOST",
    "UNSAFE_PATH_CHARS_RE",
]
