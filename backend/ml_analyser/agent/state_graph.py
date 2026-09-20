"""Project state graph construction from observed repository metadata."""

from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import (
    GraphEdgeType,
    GraphNodeType,
    ProjectEdge,
    ProjectNode,
    ProjectStateGraph,
    RepositoryInventory,
)


class InventoryStateGraphBuilder:
    """Create a deterministic project/category/file graph."""

    def build(self, project_id: str, inventory: RepositoryInventory) -> ProjectStateGraph:
        root_id = stable_id("project", project_id, inventory.project_root)
        nodes = [
            ProjectNode(
                id=root_id,
                type=GraphNodeType.PROJECT,
                label=project_id,
                metadata={
                    "project_root": inventory.project_root,
                    "total_files": inventory.total_files,
                    "total_bytes": inventory.total_bytes,
                },
            )
        ]
        edges: list[ProjectEdge] = []

        category_ids: dict[str, str] = {}
        for category in sorted(inventory.category_counts):
            category_id = stable_id("category", project_id, category)
            category_ids[category] = category_id
            nodes.append(
                ProjectNode(
                    id=category_id,
                    type=GraphNodeType.CATEGORY,
                    label=category,
                    metadata={"file_count": inventory.category_counts[category]},
                )
            )
            edges.append(
                ProjectEdge(
                    source_id=root_id,
                    target_id=category_id,
                    type=GraphEdgeType.CONTAINS,
                )
            )

        for file in inventory.files:
            file_id = stable_id("file", project_id, file.path, file.sha256 or file.hash_status)
            nodes.append(
                ProjectNode(
                    id=file_id,
                    type=GraphNodeType.FILE,
                    label=file.path,
                    metadata={
                        "path": file.path,
                        "category": file.category.value,
                        "language": file.language,
                        "size_bytes": file.size_bytes,
                        "sha256": file.sha256,
                        "hash_status": file.hash_status,
                    },
                )
            )
            edges.append(
                ProjectEdge(
                    source_id=category_ids[file.category.value],
                    target_id=file_id,
                    type=GraphEdgeType.CONTAINS,
                )
            )

        return ProjectStateGraph(
            project_id=project_id,
            nodes=nodes,
            edges=edges,
        )
