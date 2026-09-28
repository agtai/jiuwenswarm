"""The page an invite link opens in a browser: it explains where to paste the link."""

from __future__ import annotations

from html import escape

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blackboard invite</title>
<style>
  :root {{ color-scheme: light dark; --text: #1f2328; --muted: #59636e; --page: #ffffff; --card: #f6f8fa; --line: #d1d9e0; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --text: #e6edf3; --muted: #9198a1; --page: #0d1117; --card: #161b22; --line: #30363d; }} }}
  body {{ margin: 0; font: 15px/1.55 system-ui, sans-serif; background: var(--page); color: var(--text); }}
  main {{ max-width: 560px; margin: 12vh auto; padding: 0 16px; }}
  h1 {{ font-size: 22px; margin: 0 0 8px; }}
  p {{ margin: 0 0 12px; color: var(--muted); }}
  code {{ display: block; padding: 10px 12px; background: var(--card); border: 1px solid var(--line); border-radius: 6px;
          word-break: break-all; color: var(--text); }}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
<p>{lead}</p>
<code>{link}</code>
<p style="margin-top:12px">Open <b>Blackboard</b> in your jiuwenswarm, choose <b>Join with a link</b>, and paste the link above.</p>
</main>
</body>
</html>
"""


def join_page(link: str, workspace_title: str | None, role: str | None, state: str) -> str:
    if state == "active" and workspace_title:
        title = f"You are invited to {workspace_title}"
        lead = f"You will join as {role}." if role else "You are invited to a Blackboard workspace."
    elif state == "not_found":
        title = "This invite link is not valid"
        lead = "Ask the workspace owner for a new link."
    else:
        title = "This invite link can no longer be used"
        lead = f"It is {state.replace('_', ' ')}. Ask the workspace owner for a new link."
    return _PAGE.format(title=escape(title), lead=escape(lead), link=escape(link))
