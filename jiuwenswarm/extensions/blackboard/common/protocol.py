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
)

# Methods a member's agent calls on the host with the member's token (the toolkit in the
# AgentServer); they are not proxied for browsers.
EDIT = "blackboard.edit"
AGENT_METHODS: tuple[str, ...] = (EDIT,)

# Methods the host serves without a member token.
NO_AUTH_METHODS = frozenset({INVITE_ACCEPT})

# Local methods of the client part (served by the member's own jiuwenswarm).
HOSTS_LIST = "blackboard.hosts.list"
HOSTS_JOIN = "blackboard.hosts.join"
HOSTS_REMOVE = "blackboard.hosts.remove"
HOSTS_SET_DEFAULT = "blackboard.hosts.set_default"
HOST_STATUS = "blackboard.host.status"
HOST_SET_SETTINGS = "blackboard.host.set_settings"
# The browser sends a file here; the client part posts it to the host as multipart.
REFERENCE_UPLOAD = "blackboard.reference.upload"
# Sessions attached to a workspace, where the agent gets Blackboard's tools.
SESSION_ATTACH = "blackboard.session.attach"
SESSION_DETACH = "blackboard.session.detach"
SESSION_LIST = "blackboard.session.list"

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
    }
)

# Paths on the host's HTTP server.
RPC_PATH = "/blackboard/rpc"
EVENTS_PATH = "/blackboard/events"
JOIN_PATH = "/blackboard/join/"
HEALTH_PATH = "/blackboard/health"
FILES_PATH = "/blackboard/files/"
