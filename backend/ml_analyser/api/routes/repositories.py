"""Explicit repository intake into managed copies; no repository code execution."""

import tarfile

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import Field

from ml_analyser.agent.models import StrictModel
from ml_analyser.core.config import get_request_settings
from ml_analyser.tools.import_repository import decode_upload, github_archive, save_files

router = APIRouter(prefix="/repositories", tags=["repositories"])


class SourceFile(StrictModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=2800000)


class FolderImport(StrictModel):
    files: list[SourceFile] = Field(min_length=1, max_length=1000)


class GitHubImport(StrictModel):
    url: str = Field(min_length=1, max_length=300)


class ImportResult(StrictModel):
    project_path: str
    files: int
    skipped: int
    message: str = "Source copy imported. No project code has been executed."


def persist_import(files: list[tuple[str, bytes]]) -> ImportResult:
    path, count, skipped = save_files(get_request_settings().workspace_root, files)
    return ImportResult(project_path=path, files=count, skipped=skipped)


@router.post("/folder", response_model=ImportResult, status_code=201)
def import_folder(request: FolderImport) -> ImportResult:
    try:
        return persist_import([(item.path, decode_upload(item.content)) for item in request.files])
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/github", response_model=ImportResult, status_code=201)
def import_github(request: GitHubImport) -> ImportResult:
    try:
        return persist_import(github_archive(request.url))
    except (ValueError, OSError, EOFError, tarfile.TarError, httpx.HTTPError) as error:
        raise HTTPException(422, "Import failed: " + str(error)) from error
