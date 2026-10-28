from enum import StrEnum


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    # Reserved for sharing a workspace, which the MVP doesn't offer yet.
    MEMBER = "member"
