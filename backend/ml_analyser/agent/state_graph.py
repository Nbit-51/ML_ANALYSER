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
from ml_analyser.tools.capabilities import detect_capabilities


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

        summary, _ = detect_capabilities(inventory)
        file_ids = {node.label: node.id for node in nodes if node.type is GraphNodeType.FILE}
        for language, size in summary.language_bytes.items():
            language_id = stable_id("language", project_id, language)
            nodes.append(
                ProjectNode(
                    id=language_id,
                    type=GraphNodeType.LANGUAGE,
                    label=language,
                    metadata={"size_bytes": size},
                )
            )
            edges.append(
                ProjectEdge(source_id=root_id, target_id=language_id, type=GraphEdgeType.USES)
            )
        for capability in summary.capabilities:
            nodes.append(
                ProjectNode(
                    id=capability.id,
                    type=GraphNodeType.CAPABILITY,
                    label=capability.name,
                    metadata={
                        "kind": capability.kind,
                        "provenance": capability.provenance,
                        "confidence": capability.confidence,
                    },
                )
            )
            edges.append(
                ProjectEdge(
                    source_id=root_id,
                    target_id=capability.id,
                    type=GraphEdgeType.USES,
                    provenance=capability.provenance,
                    confidence=capability.confidence,
                    evidence_ids=capability.evidence_ids,
                )
            )
            for path in capability.paths:
                edges.append(
                    ProjectEdge(
                        source_id=file_ids[path],
                        target_id=capability.id,
                        type=GraphEdgeType.CONFIGURES,
                        provenance=capability.provenance,
                        confidence=capability.confidence,
                        evidence_ids=capability.evidence_ids,
                    )
                )
        return ProjectStateGraph(
            project_id=project_id,
            nodes=nodes,
            edges=edges,
        )
