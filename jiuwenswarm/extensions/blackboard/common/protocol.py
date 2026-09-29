"""RPC method and event names shared by the host, the client and the browser.

Every method the host serves is also registered on the member's own web channel
as a proxy, so the browser only ever talks to its own jiuwenswarm.
"""

from __future__ import annotations

# Host methods (milestone 2).
ME = "blackboard.me"
ME_SET_NAME = "blackboard.me.set_name"
WORKSPACE_LIST = "blackboard.workspace.list"
WORKSPACE_CREATE = "blackboard.workspace.create"
WORKSPACE_RENAME = "blackboard.workspace.rename"
WORKSPACE_ARCHIVE = "blackboard.workspace.archive"
WORKSPACE_UNARCHIVE = "blackboard.workspace.unarchive"
WORKSPACE_DELETE = "blackboard.workspace.delete"
MEMBER_LIST = "blackboard.member.list"
MEMBER_SET_ROLE = "blackboard.member.set_role"
MEMBER_REMOVE = "blackboard.member.remove"
INVITE_CREATE = "blackboard.invite.create"
INVITE_LIST = "blackboard.invite.list"
INVITE_REVOKE = "blackboard.invite.revoke"
INVITE_ACCEPT = "blackboard.invite.accept"

# Host methods (milestone 3): documents and references.
DOC_LIST = "blackboard.doc.list"
DOC_CREATE = "blackboard.doc.create"
DOC_RENAME = "blackboard.doc.rename"
DOC_ARCHIVE = "blackboard.doc.archive"
DOC_SET_INSTRUCTIONS = "blackboard.doc.set_instructions"
DOC_PIN = "blackboard.doc.pin"
DOC_IMPORT_MARKDOWN = "blackboard.doc.import_markdown"
DOC_TOKEN = "blackboard.doc.token"
DOC_READ = "blackboard.doc.read"
REFERENCE_LIST = "blackboard.reference.list"
REFERENCE_REMOVE = "blackboard.reference.remove"
REFERENCE_URL = "blackboard.reference.url"
REFERENCE_SET_NOTE = "blackboard.reference.set_note"
MANDATE_LIST = "blackboard.mandate.list"
MANDATE_CANCEL = "blackboard.mandate.cancel"
SUGGESTION_LIST = "blackboard.suggestion.list"
SUGGESTION_DECIDE = "blackboard.suggestion.decide"

# Host methods (milestone 5): comments, the workspace chat, decisions.
COMMENT_CREATE = "blackboard.comment.create"
COMMENT_REPLY = "blackboard.comment.reply"
COMMENT_EDIT = "blackboard.comment.edit"
COMMENT_RESOLVE = "blackboard.comment.resolve"
COMMENT_REOPEN = "blackboard.comment.reopen"
COMMENT_LIST = "blackboard.comment.list"
CHAT_POST = "blackboard.chat.post"
CHAT_LIST = "blackboard.chat.list"
DECISION_LIST = "blackboard.decision.list"
DECISION_GET = "blackboard.decision.get"
DECISION_ANSWER = "blackboard.decision.answer"
DECISION_ACCEPT = "blackboard.decision.accept"
DECISION_CANCEL = "blackboard.decision.cancel"
MANDATE_RESOLVE_UNKNOWN = "blackboard.mandate.resolve_unknown"

# Host methods (milestone 6): version history and export.
HISTORY_LIST = "blackboard.history.list"
HISTORY_GET = "blackboard.history.get"
HISTORY_DIFF = "blackboard.history.diff"
HISTORY_SAVE = "blackboard.history.save"
HISTORY_RESTORE = "blackboard.history.restore"
DOC_EXPORT = "blackboard.doc.export"

# Host methods (milestone 7): reading a reference's text, shared IM bots (the host operator's), and
# the IM accounts a person connects to their user.
REFERENCE_READ = "blackboard.reference.read"
BOT_CREATE = "blackboard.bot.create"
BOT_LIST = "blackboard.bot.list"
BOT_REVOKE = "blackboard.bot.revoke"
IDENTITY_LINK_CODE = "blackboard.identity.link_code"
IDENTITY_LIST = "blackboard.identity.list"
IDENTITY_UNLINK = "blackboard.identity.unlink"
# Host methods (milestone 8): the operator's list of people on the host, and turning one off or on.
USER_LIST = "blackboard.user.list"
USER_SET_STATUS = "blackboard.user.set_status"

HOST_METHODS: tuple[str, ...] = (
    ME,
    ME_SET_NAME,
    WORKSPACE_LIST,
    WORKSPACE_CREATE,
    WORKSPACE_RENAME,
    WORKSPACE_ARCHIVE,
    WORKSPACE_UNARCHIVE,
    WORKSPACE_DELETE,
    MEMBER_LIST,
    MEMBER_SET_ROLE,
    MEMBER_REMOVE,
    INVITE_CREATE,
    INVITE_LIST,
    INVITE_REVOKE,
    DOC_LIST,
    DOC_CREATE,
    DOC_RENAME,
    DOC_ARCHIVE,
    DOC_SET_INSTRUCTIONS,
    DOC_PIN,
    DOC_IMPORT_MARKDOWN,
    DOC_TOKEN,
    DOC_READ,
    REFERENCE_LIST,
    REFERENCE_REMOVE,
    REFERENCE_URL,
    REFERENCE_SET_NOTE,
    MANDATE_LIST,
    MANDATE_CANCEL,
    SUGGESTION_LIST,
    SUGGESTION_DECIDE,
    COMMENT_CREATE,
    COMMENT_REPLY,
    COMMENT_EDIT,
    COMMENT_RESOLVE,
    COMMENT_REOPEN,
    COMMENT_LIST,
    CHAT_POST,
    CHAT_LIST,
    DECISION_LIST,
    DECISION_GET,
    DECISION_ANSWER,
    DECISION_ACCEPT,
    DECISION_CANCEL,
    MANDATE_RESOLVE_UNKNOWN,
    HISTORY_LIST,
    HISTORY_GET,
    HISTORY_DIFF,
    HISTORY_SAVE,
    HISTORY_RESTORE,
    DOC_EXPORT,
    REFERENCE_READ,
    BOT_CREATE,
    BOT_LIST,
    BOT_REVOKE,
    IDENTITY_LINK_CODE,
    IDENTITY_LIST,
    IDENTITY_UNLINK,
    USER_LIST,
    USER_SET_STATUS,
)

# A new member token for the caller. Only the person's own jiuwenswarm calls it (through the local
# method HOSTS_ROTATE_TOKEN), so the token never reaches a browser.
ME_ROTATE_TOKEN = "blackboard.me.rotate_token"

# Methods a member's agent and dispatcher call on the host with the member's token (the toolkit
# in the AgentServer, the dispatcher in the Gateway); they are not proxied for browsers.
EDIT = "blackboard.edit"
# The agent's question to the workspace (blackboard_ask).
DECISION_CREATE = "blackboard.decision.create"
# The dispatcher: picking up an offered turn, reporting its end, and the turns offered while offline.
MANDATE_CLAIM = "blackboard.mandate.claim"
MANDATE_REPORT = "blackboard.mandate.report"
MANDATE_PENDING = "blackboard.mandate.pending"
AGENT_METHODS: tuple[str, ...] = (EDIT, DECISION_CREATE, MANDATE_CLAIM, MANDATE_REPORT, MANDATE_PENDING)

# A shared IM bot calls with its bot token. For itself it may check who it is and connect a person's
# IM account with their link code; on behalf of a connected person (the X-BB-On-Behalf-Of header,
# "<platform>:<platform user id>") it may only read.
IDENTITY_LINK = "blackboard.identity.link"
BOT_WHOAMI = "blackboard.bot.whoami"
BOT_OWN_METHODS = frozenset({IDENTITY_LINK, BOT_WHOAMI})
BOT_READ_METHODS = frozenset(
    {ME, WORKSPACE_LIST, DOC_LIST, DOC_READ, SUGGESTION_LIST, REFERENCE_LIST, REFERENCE_READ, DECISION_LIST, CHAT_LIST}
)
ON_BEHALF_HEADER = "X-BB-On-Behalf-Of"
# Set by the agent's tools, whose calls are rate limited; the browser's are not.
AGENT_HEADER = "X-BB-Agent"

# Methods the host serves without a member token.
NO_AUTH_METHODS = frozenset({INVITE_ACCEPT})

# Local methods of the client part (served by the member's own jiuwenswarm).
HOSTS_LIST = "blackboard.hosts.list"
HOSTS_JOIN = "blackboard.hosts.join"
HOSTS_REMOVE = "blackboard.hosts.remove"
HOSTS_SET_DEFAULT = "blackboard.hosts.set_default"
HOSTS_ROTATE_TOKEN = "blackboard.hosts.rotate_token"
HOST_STATUS = "blackboard.host.status"
HOST_SET_SETTINGS = "blackboard.host.set_settings"
HOST_HEALTH = "blackboard.host.health"
# The browser sends a file here; the client part posts it to the host as multipart.
REFERENCE_UPLOAD = "blackboard.reference.upload"
# Sessions attached to a workspace, where the agent gets Blackboard's tools.
SESSION_ATTACH = "blackboard.session.attach"
SESSION_DETACH = "blackboard.session.detach"
SESSION_LIST = "blackboard.session.list"
# Shared-bot credentials of this jiuwenswarm (milestone 7): the bot links it was given.
BOTS_LIST = "blackboard.bots.list"
BOTS_CONNECT = "blackboard.bots.connect"
BOTS_REMOVE = "blackboard.bots.remove"

# Events pushed by the host (and forwarded to browsers with a `host` field).
EV_WORKSPACE_UPDATED = "blackboard.workspace.updated"
EV_MEMBER_UPDATED = "blackboard.member.updated"
EV_ME_UPDATED = "blackboard.me.updated"
EV_MEMBER_ROLE_CHANGED = "blackboard.member.role_changed"
# The host's name changed; sent to every connected member.
EV_HOST_UPDATED = "blackboard.host.updated"
EV_DOC_UPDATED = "blackboard.doc.updated"
EV_REFERENCE_UPDATED = "blackboard.reference.updated"
EV_MANDATE_UPDATED = "blackboard.mandate.updated"
EV_SUGGESTIONS_CHANGED = "blackboard.doc.suggestions_changed"
EV_THREAD_UPDATED = "blackboard.thread.updated"
EV_CHAT_MESSAGE = "blackboard.chat.message"
EV_DECISION_UPDATED = "blackboard.decision.updated"
EV_DOC_VERSIONS = "blackboard.doc.versions"
# To the requester's own jiuwenswarm only: run a turn of a mandate, or stop it. The client part
# handles them and does not forward them to browsers.
EV_MANDATE_RUN = "blackboard.mandate.run"
EV_MANDATE_STOP = "blackboard.mandate.stop"
# Events of the client part.
EV_HOSTS_UPDATED = "blackboard.hosts.updated"
EV_HOST_STATUS = "blackboard.host.status_changed"
EV_SESSIONS_UPDATED = "blackboard.sessions.updated"

HOST_EVENTS = frozenset(
    {
        EV_WORKSPACE_UPDATED,
        EV_MEMBER_UPDATED,
        EV_ME_UPDATED,
        EV_MEMBER_ROLE_CHANGED,
        EV_HOST_UPDATED,
        EV_DOC_UPDATED,
        EV_REFERENCE_UPDATED,
        EV_MANDATE_UPDATED,
        EV_SUGGESTIONS_CHANGED,
        EV_THREAD_UPDATED,
        EV_CHAT_MESSAGE,
        EV_DECISION_UPDATED,
        EV_DOC_VERSIONS,
        EV_MANDATE_RUN,
        EV_MANDATE_STOP,
    }
)

# Paths on the host's HTTP server.
RPC_PATH = "/blackboard/rpc"
EVENTS_PATH = "/blackboard/events"
JOIN_PATH = "/blackboard/join/"
HEALTH_PATH = "/blackboard/health"
FILES_PATH = "/blackboard/files/"
# A bot link is <host base URL><BOT_PATH>#<bot token>; the token stays out of server logs.
BOT_PATH = "/blackboard/bot"
# Exports, opened by the browser with a short-lived token.
EXPORT_PATH = "/blackboard/export/"
# The document service announces new versions here (X-BB-Secret).
VERSIONS_HOOK_PATH = "/blackboard/internal/versions"
