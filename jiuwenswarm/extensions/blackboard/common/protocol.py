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
)

# Methods the host serves without a member token.
NO_AUTH_METHODS = frozenset({INVITE_ACCEPT})

# Local methods of the client part (served by the member's own jiuwenswarm).
HOSTS_LIST = "blackboard.hosts.list"
HOSTS_JOIN = "blackboard.hosts.join"
HOSTS_REMOVE = "blackboard.hosts.remove"
HOSTS_SET_DEFAULT = "blackboard.hosts.set_default"
HOST_STATUS = "blackboard.host.status"
HOST_SET_SETTINGS = "blackboard.host.set_settings"

# Events pushed by the host (and forwarded to browsers with a `host` field).
EV_WORKSPACE_UPDATED = "blackboard.workspace.updated"
EV_MEMBER_UPDATED = "blackboard.member.updated"
EV_ME_UPDATED = "blackboard.me.updated"
EV_MEMBER_ROLE_CHANGED = "blackboard.member.role_changed"
# The host's name changed; sent to every connected member.
EV_HOST_UPDATED = "blackboard.host.updated"
# Events of the client part.
EV_HOSTS_UPDATED = "blackboard.hosts.updated"
EV_HOST_STATUS = "blackboard.host.status_changed"

HOST_EVENTS = frozenset(
    {EV_WORKSPACE_UPDATED, EV_MEMBER_UPDATED, EV_ME_UPDATED, EV_MEMBER_ROLE_CHANGED, EV_HOST_UPDATED}
)

# Paths on the host's HTTP server.
RPC_PATH = "/blackboard/rpc"
EVENTS_PATH = "/blackboard/events"
JOIN_PATH = "/blackboard/join/"
HEALTH_PATH = "/blackboard/health"
