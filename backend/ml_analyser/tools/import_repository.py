"""Import selected source files without executing Git hooks or project code."""

import base64
import gzip
import io
import re
import shutil
import tarfile
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx

from ml_analyser.tools.repository import DEFAULT_IGNORED_DIRECTORIES

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 1000
MAX_FILE_BYTES = 2 * 1024 * 1024
IGNORED = DEFAULT_IGNORED_DIRECTORIES | {".aws", ".ssh", ".azure", "artifacts", ".next"}


def validated_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 300
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or re.search(r'[\x00-\x1f:<>"|?*]', value)
    ):
        raise ValueError(
            "File paths must be relative and cannot contain traversal or special names."
        )
    for part in path.parts:
        if part.endswith((" ", ".")) or re.fullmatch(
            r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part
        ):
            raise ValueError("Unsupported file name.")
    return path


def excluded(path: PurePosixPath) -> bool:
    parts = [part.casefold() for part in path.parts]
    name = parts[-1]
    return (
        any(part in IGNORED for part in parts)
        or name.startswith(".env")
        or any(word in name for word in ("secret", "credential"))
        or name in {"id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc"}
        or path.suffix.casefold() in {".pem", ".key", ".p12", ".pfx", ".pyc", ".db", ".log"}
    )


def save_files(root: Path, files: list[tuple[str, bytes]]) -> tuple[str, int, int]:
    if not files or len(files) > MAX_FILES:
        raise ValueError("Choose between 1 and 1,000 source files.")
    cleaned: list[tuple[PurePosixPath, bytes]] = []
    seen: set[str] = set()
    total, skipped = 0, 0
    for name, data in files:
        path = validated_path(name)
        if excluded(path):
            skipped += 1
            continue
        if path.as_posix().casefold() in seen:
            raise ValueError("Duplicate file paths are not permitted.")
        seen.add(path.as_posix().casefold())
        total += len(data)
        if len(data) > MAX_FILE_BYTES or total > MAX_BYTES:
            raise ValueError("Import limit: 2 MB per file and 20 MB total.")
        cleaned.append((path, data))
    if not cleaned:
        raise ValueError("No source files remain after excluding secrets and generated files.")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    target = root / ("imported-" + uuid.uuid4().hex)
    target.mkdir()
    try:
        for path, data in cleaned:
            output = target.joinpath(*path.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
    except OSError:
        if target.resolve().is_relative_to(root):
            shutil.rmtree(target)
        raise
    return target.name, len(cleaned), skipped


def decode_upload(content: str) -> bytes:
    try:
        return base64.b64decode(content, validate=True)
    except ValueError as error:
        raise ValueError("Invalid file encoding.") from error


def github_archive(url: str) -> list[tuple[str, bytes]]:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+/?", parsed.path)
    ):
        raise ValueError("Use a public repository URL: https://github.com/owner/repository")
    owner, repo = parsed.path.strip("/").removesuffix(".git").split("/")
    if repo in {".", ".."}:
        raise ValueError("Invalid repository name.")
    archive = bytearray()
    with (
        httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client,
        client.stream("GET", f"https://codeload.github.com/{owner}/{repo}/tar.gz/HEAD") as response,
    ):
        if response.status_code != 200:
            raise ValueError(
                "Repository unavailable. Use a public GitHub URL or choose a local folder."
            )
        for chunk in response.iter_bytes(65536):
            archive.extend(chunk)
            if len(archive) > MAX_BYTES:
                raise ValueError("Repository archive exceeds the 20 MB import limit.")
    # Bound decompression before parsing tar metadata; never extract links or special files.
    with gzip.GzipFile(fileobj=io.BytesIO(archive)) as compressed:
        expanded = compressed.read(MAX_BYTES + 1)
    if len(expanded) > MAX_BYTES:
        raise ValueError("Expanded repository archive exceeds the 20 MB import limit.")
    files: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as tar:
        for index, item in enumerate(tar):
            if index > 5000:
                raise ValueError("Repository archive has too many entries.")
            path = validated_path(item.name.rstrip("/"))
            if item.isdir():
                continue
            if not item.isfile() or len(path.parts) < 2:
                raise ValueError("Repository archives cannot include links or special files.")
            relative = PurePosixPath(*path.parts[1:])
            if excluded(relative):
                continue
            if item.size > MAX_FILE_BYTES or len(files) >= MAX_FILES:
                raise ValueError("Repository exceeds the 1,000-file or 2 MB per-file limit.")
            stream = tar.extractfile(item)
            if stream is not None:
                files.append((relative.as_posix(), stream.read(MAX_FILE_BYTES + 1)))
    return files
