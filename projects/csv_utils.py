from __future__ import annotations

import csv
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from django.http import FileResponse

# Base temp export directory (Heroku-friendly; also works locally)
_EXPORT_BASE_DIR = Path(tempfile.gettempdir()) / "bencritt_exports"

_SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename_component(value: str, *, default: str = "export") -> str:
    """
    Make a filename-safe component:
    - strips weird characters
    - avoids empty results
    """
    s = (value or "").strip()
    s = _SAFE_COMPONENT_RE.sub("_", s).strip("._-")
    return s or default


def _stringify_csv_value(v: Any) -> str:
    """
    Normalize values for CSV output.
    (Keep it simple + consistent across your apps.)
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return str(v)


def ensure_export_dir(subdir: str) -> Path:
    """
    Ensure /tmp/bencritt_exports/<subdir>/ exists and return it.
    """
    d = _EXPORT_BASE_DIR / safe_filename_component(subdir, default="exports")
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_rows_to_csv_file(
    rows: Sequence[Mapping[str, Any]],
    *,
    filename: str,
    columns: Sequence[str],
    header_map: Optional[Mapping[str, str]] = None,
    export_subdir: str = "exports",
    add_utf8_bom: bool = True,
) -> Dict[str, Any]:
    """
    Write rows to a CSV file on disk and return metadata:
      { "path": ..., "filename": ..., "created_at": ... }

    - rows: list of dicts
    - columns: column order (also controls which keys get output)
    - header_map: optional pretty names for header row
    """
    export_dir = ensure_export_dir(export_subdir)
    safe_name = safe_filename_component(filename, default="export.csv")
    if not safe_name.lower().endswith(".csv"):
        safe_name += ".csv"

    full_path = export_dir / safe_name

    # utf-8-sig writes a BOM, which helps Excel open UTF-8 correctly
    encoding = "utf-8-sig" if add_utf8_bom else "utf-8"

    with open(full_path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f)

        header = [
            (header_map.get(col, col) if header_map else col)
            for col in columns
        ]
        w.writerow(header)

        for r in rows:
            w.writerow([_stringify_csv_value(r.get(col, "")) for col in columns])

    return {"path": str(full_path), "filename": safe_name, "created_at": time.time()}


def cleanup_old_files(*, export_subdir: str, max_age_seconds: int = 1800) -> int:
    """
    Best-effort cleanup: delete files older than max_age_seconds in the export_subdir.
    Returns number of files deleted.
    """
    export_dir = ensure_export_dir(export_subdir)
    now = time.time()
    deleted = 0

    try:
        for p in export_dir.glob("*.csv"):
            try:
                age = now - p.stat().st_mtime
                if age >= max_age_seconds:
                    p.unlink(missing_ok=True)
                    deleted += 1
            except Exception:
                # Don't let cleanup ever break your request path
                continue
    except Exception:
        return deleted

    return deleted


def file_response_with_cleanup(
    *,
    path: str,
    download_filename: str,
    content_type: str = "text/csv",
) -> FileResponse:
    """
    Serve a file via FileResponse and delete it when the response is closed.

    Note: This is "best effort" cleanup. In practice it works well under WSGI.
    """
    f = open(path, "rb")

    resp = FileResponse(
        f,
        as_attachment=True,
        filename=download_filename,
        content_type=content_type,
    )

    original_close = resp.close
    already_deleted = {"done": False}

    def _close() -> None:
        if already_deleted["done"]:
            return original_close()
        already_deleted["done"] = True
        try:
            original_close()
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except Exception:
                pass

    resp.close = _close  # type: ignore[assignment]
    return resp
