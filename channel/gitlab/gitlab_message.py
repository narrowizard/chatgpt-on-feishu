"""
GitLab 消息解析

@author Roo code
@Date 2025/1/26
"""

from bridge.context import ContextType
from common.log import logger


class GitlabMessage:
    def __init__(self, event: dict):
        self.event = event
        self.ctype = ContextType.TEXT
        self.from_user_id = self._get_user_id()
        self.content = self._parse_event()

    def _get_user_id(self) -> int:
        event_type = self.event.get("object_kind")
        if not event_type:
            return 0

        if event_type == "push":
            return self.event.get("user_id", 0)
        elif event_type in ["issue", "merge_request"]:
            user = self.event.get("user", {})
            return user.get("id", 0)
        return 0

    def _parse_event(self) -> str:
        event_type = self.event.get("object_kind")
        if not event_type:
            return ""

        if event_type == "push":
            return self._parse_push_event()
        elif event_type == "issue":
            return self._parse_issue_event()
        elif event_type == "merge_request":
            return self._parse_merge_request_event()
        else:
            logger.warning(f"[Gitlab] unsupported event type: {event_type}")
            return ""

    def _parse_push_event(self) -> str:
        project = self.event.get("project", {}).get("name", "unknown project")
        ref = self.event.get("ref", "unknown branch")
        commits = self.event.get("commits", [])
        commit_count = len(commits)
        user = self.event.get("user_name", "unknown user")

        return f"{user} pushed {commit_count} commit(s) to {ref} in {project}"

    def _parse_issue_event(self) -> str:
        project = self.event.get("project", {}).get("name", "unknown project")
        issue = self.event.get("object_attributes", {})
        action = issue.get("action", "unknown action")
        title = issue.get("title", "unknown title")
        user = self.event.get("user", {}).get("name", "unknown user")

        return f"{user} {action} issue '{title}' in {project}"

    def _parse_merge_request_event(self) -> str:
        project = self.event.get("project", {}).get("name", "unknown project")
        merge_request = self.event.get("object_attributes", {})
        action = merge_request.get("action", "unknown action")
        title = merge_request.get("title", "unknown title")
        user = self.event.get("user", {}).get("name", "unknown user")

        return f"{user} {action} merge request '{title}' in {project}"