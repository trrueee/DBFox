"""Hierarchical namespace builder for LongTermMemory.

Namespaces are tuples that organize memories by ownership scope
(user, project, datasource, workspace) so that retrieval never
leaks across tenants.
"""
from __future__ import annotations


class MemoryNamespace:
    """Factory for memory namespace tuples.

    Namespaces follow the pattern::

        ("user", user_id)
        ("user", user_id, "project", project_id)
        ("datasource", datasource_id)
        ("project", project_id)
    """

    @staticmethod
    def user(user_id: str) -> tuple[str, ...]:
        return ("user", user_id)

    @staticmethod
    def project(project_id: str) -> tuple[str, ...]:
        return ("project", project_id)

    @staticmethod
    def datasource(datasource_id: str) -> tuple[str, ...]:
        return ("datasource", datasource_id)

    @staticmethod
    def workspace(workspace_id: str) -> tuple[str, ...]:
        return ("workspace", workspace_id)

    @staticmethod
    def user_project(user_id: str, project_id: str) -> tuple[str, ...]:
        return ("user", user_id, "project", project_id)

    @staticmethod
    def user_datasource(user_id: str, datasource_id: str) -> tuple[str, ...]:
        return ("user", user_id, "datasource", datasource_id)

    @staticmethod
    def project_datasource(project_id: str, datasource_id: str) -> tuple[str, ...]:
        return ("project", project_id, "datasource", datasource_id)

    @staticmethod
    def scoped(
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        datasource_id: str | None = None,
    ) -> list[tuple[str, ...]]:
        """Return all relevant namespaces for retrieval.

        Always includes the most specific and broader scopes so that
        project-level rules are visible alongside user-level prefs.
        """
        namespaces: list[tuple[str, ...]] = []
        if user_id:
            namespaces.append(("user", user_id))
        if project_id:
            namespaces.append(("project", project_id))
        if datasource_id:
            namespaces.append(("datasource", datasource_id))
        if user_id and project_id:
            namespaces.append(("user", user_id, "project", project_id))
        if user_id and datasource_id:
            namespaces.append(("user", user_id, "datasource", datasource_id))
        if project_id and datasource_id:
            namespaces.append(("project", project_id, "datasource", datasource_id))
        return namespaces
