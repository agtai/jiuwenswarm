"""The signature a personal-identity reply carries (design §13, matrix S.5).

Under a personal connection the platform records the agent's reply as the person's
own -- neither Google nor Feishu has an "executed by an agent" mark -- so the
signature line at the end of the reply is the only in-document signal that a
program, not the person, wrote it. Two halves, with different owners:

* the **body** is the person's to word (``clouddoc.personal_signature``; the
  default names them: "-- executed by {name}'s JiuwenSwarm agent");
* the **receipt number** is the code's, appended after the body every time, and is
  neither configurable nor omittable. It is what lets a reader go from the thread
  to the ledger entry that vouches for the post.

Wording an empty body does not remove the signature: an empty template falls back
to the default, because a reply with no signature at all is the failure this line
exists to prevent.
"""

from __future__ import annotations

DEFAULT_SIGNATURE_TEMPLATE = "— 由 {name} 的 JiuwenSwarm 代理执行"

# The fixed tail. ``回执`` is the same word the panel's history uses for a receipt,
# so a reader can search for it.
RECEIPT_TAIL = "回执 {receipt_id}"

# A signature body is one line: a newline in the template would let the body
# masquerade as reply content above a fake signature line.
_MAX_BODY_CHARS = 120


def signature_body(template: str | None, *, name: str) -> str:
    """The person's half, rendered. Falls back to the default when the template is
    empty or renders to nothing; never returns an empty string."""
    raw = str(template or "").strip()
    if not raw:
        raw = DEFAULT_SIGNATURE_TEMPLATE
    body = raw.replace("{name}", name or "").strip()
    body = " ".join(body.split())
    if not body:
        body = DEFAULT_SIGNATURE_TEMPLATE.replace("{name}", name or "").strip()
    return body[:_MAX_BODY_CHARS]


def render_signature(template: str | None, *, name: str, receipt_id: str) -> str:
    """The full line: body, then the receipt number. Raises on an empty receipt id --
    the caller must have a ledger entry before it may sign anything."""
    rid = str(receipt_id or "").strip()
    if not rid:
        raise ValueError("a signature needs a receipt id; none was given")
    return f"{signature_body(template, name=name)} · {RECEIPT_TAIL.format(receipt_id=rid)}"


def sign_reply(content: str, template: str | None, *, name: str, receipt_id: str) -> str:
    """Append the signature line to a reply's content, mechanically."""
    text = str(content or "").rstrip()
    return f"{text}\n\n{render_signature(template, name=name, receipt_id=receipt_id)}"
