"""Explicit repository intake into managed copies; no repository code execution."""

import tarfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from ml_analyser.adapters.registry import default_registry
from ml_analyser.agent.models import AdapterReadiness, SavedRepository, StrictModel
from ml_analyser.core.config import get_request_settings
from ml_analyser.core.workspace import resolve_project_path
from ml_analyser.persistence import SQLiteRunStore
from ml_analyser.tools.import_repository import decode_upload, github_archive, save_files
from ml_analyser.tools.repository import RepositoryInventoryTool

router = APIRouter(prefix="/repositories", tags=["repositories"])


class SourceFile(StrictModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=2800000)


class FolderImport(StrictModel):
    files: list[SourceFile] = Field(min_length=1, max_length=1000)
    display_name: str = Field(default="Local repository", min_length=1, max_length=120)


class GitHubImport(StrictModel):
    url: str = Field(min_length=1, max_length=300)


class ImportResult(StrictModel):
    project_path: str
    files: int
    skipped: int
    display_name: str
    message: str = "Source copy imported. No project code has been executed."


class BenchmarkProject(StrictModel):
    project_path: str
    display_name: str


class ProjectDetails(StrictModel):
    project_path: str
    adapters: list[AdapterReadiness]
    executed: bool = False
    benchmark_projects: list[BenchmarkProject] = Field(default_factory=list)


def persist_import(
    files: list[tuple[str, bytes]],
    *,
    display_name: str,
    source_url: str | None = None,
) -> ImportResult:
    settings = get_request_settings()
    path, count, skipped = save_files(settings.workspace_root, files)
    SQLiteRunStore(settings.state_database).save_repository(
        SavedRepository(
            project_path=path,
            display_name=display_name,
            origin="github" if source_url else "folder",
            source_url=source_url,
            imported_at=datetime.now(UTC).isoformat(),
        )
    )
    return ImportResult(project_path=path, files=count, skipped=skipped, display_name=display_name)


@router.get("", response_model=list[SavedRepository])
def saved_repositories() -> list[SavedRepository]:
    settings = get_request_settings()
    root = settings.workspace_root
    if not root.is_dir():
        return []
    records = {
        item.project_path: item
        for item in SQLiteRunStore(settings.state_database).list_repositories()
    }
    projects = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if path.name.startswith(".") or path.is_symlink() or not path.is_dir():
            continue
        projects.append(
            records.get(path.name)
            or SavedRepository(
                project_path=path.name,
                display_name=path.name,
            )
        )
        if len(projects) == 100:
            break
    return projects


@router.get("/details", response_model=ProjectDetails)
def project_details(project_path: str = Query(min_length=1, max_length=500)) -> ProjectDetails:
    try:
        root = resolve_project_path(get_request_settings().workspace_root, project_path)
        registry = default_registry()
        inventory = RepositoryInventoryTool(max_files=1000).inspect(str(root))
        declared = sorted(
            {
                Path(item.path).parent.as_posix()
                for item in inventory.files
                if Path(item.path).name in registry.manifest_names
                and Path(item.path).parent != Path(".")
            }
        )[:12]
        projects = []
        for relative in declared:
            nested_path = project_path.rstrip("/") + "/" + relative
            if len(nested_path) > 500:
                continue
            nested = resolve_project_path(get_request_settings().workspace_root, nested_path)
            readiness = registry.describe(nested)
            if any(
                item.status in {"supported_and_executable", "preview_only"} for item in readiness
            ):
                projects.append(BenchmarkProject(project_path=nested_path, display_name=relative))
        return ProjectDetails(
            project_path=project_path, adapters=registry.describe(root), benchmark_projects=projects
        )
    except FileNotFoundError as error:
        raise HTTPException(404, "Project no longer exists. Import it again.") from error
    except (OSError, ValueError) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/folder", response_model=ImportResult, status_code=201)
def import_folder(request: FolderImport) -> ImportResult:
    try:
        return persist_import(
            [(item.path, decode_upload(item.content)) for item in request.files],
            display_name=request.display_name,
        )
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/github", response_model=ImportResult, status_code=201)
def import_github(request: GitHubImport) -> ImportResult:
    try:
        return persist_import(
            github_archive(request.url),
            display_name=Path(request.url.rstrip("/")).name.removesuffix(".git"),
            source_url=request.url,
        )
    except (ValueError, OSError, EOFError, tarfile.TarError, httpx.HTTPError) as error:
        raise HTTPException(422, "Import failed: " + str(error)) from error
