import io
import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ParseError

from .mem_utils import trim_now

_XML_DECL = b'<?xml version="1.0" encoding="utf-8"?>\n'

# Common non-ASCII hyphens that sometimes sneak into "utf-8"
_BAD_HYPHENS = [
    b"\xe2\x80\x90",  # U+2010 hyphen
    b"\xe2\x80\x91",  # U+2011 non-breaking hyphen
    b"\xe2\x80\x92",  # U+2012 figure dash
    b"\xe2\x80\x93",  # U+2013 en dash
    b"\xe2\x80\x94",  # U+2014 em dash
    b"\xe2\x88\x92",  # U+2212 minus sign
]

_ENCODING_ERR_SNIPPET = "encoding specified in xml declaration is incorrect"


def _safe_filename(text: str | None) -> str:
    if not text:
        return "unnamed"
    cleaned = re.sub(r"[^\w\-\.]", "_", text.strip())
    return cleaned or "unnamed"


def _normalize_prolog_chunk(head: bytes) -> bytes:
    """
    Normalize weird enc labels in the XML declaration found in the first few KB.
    - Replace smart hyphens in 'utf-8' with ASCII '-'
    - Normalize 'utf8'/'UTF8'/'utf_8' to 'utf-8'
    Only touches the first <?xml ... ?> if present; otherwise returns head unchanged.
    """
    if b"<?xml" not in head:
        return head

    # Limit normalization to the prolog (up to '?>') if present
    prolog_end = head.find(b"?>")
    search_end = prolog_end + 2 if prolog_end != -1 else min(len(head), 4096)
    prolog = head[:search_end]
    rest = head[search_end:]

    # Replace weird hyphens globally in the prolog
    for bad in _BAD_HYPHENS:
        prolog = prolog.replace(bad, b"-")

    # Normalize common utf8 variants to utf-8 (case-insensitive)
    prolog = re.sub(
        br'(?i)(encoding\s*=\s*["\'])utf_?8(["\'])',
        br"\1utf-8\2",
        prolog,
        count=1,
    )
    # Handle cases like encoding="utf–8" after hyphen normalization (defense in depth)
    prolog = re.sub(
        br'(?i)(encoding\s*=\s*["\'])utf-8(["\'])',
        br"\1utf-8\2",
        prolog,
        count=1,
    )

    return prolog + rest


def _make_normalized_copy(src_file) -> str:
    """
    Create a temp file that is a byte-for-byte copy of src_file,
    except the first few KB are normalized for the XML declaration.
    Returns the temp file path.
    """
    try:
        src_file.seek(0)
    except Exception:
        pass

    tmpf = tempfile.NamedTemporaryFile(prefix="xmlnorm_", suffix=".xml", delete=False)
    tmp_path = tmpf.name

    # Read a small head, normalize, write, then stream-copy the remainder
    head = src_file.read(4096)
    fixed_head = _normalize_prolog_chunk(head)
    tmpf.write(fixed_head)

    # Copy the rest without loading into memory
    chunk = src_file.read(64 * 1024)
    while chunk:
        tmpf.write(chunk)
        chunk = src_file.read(64 * 1024)

    tmpf.flush()
    tmpf.close()

    # Rewind original for any potential re-reads elsewhere
    try:
        src_file.seek(0)
    except Exception:
        pass

    return tmp_path


def split_xml_to_zip(uploaded_file):
    """
    Stream-split a large XML without loading it all into memory.
    Robust to bad encoding labels in the XML declaration.

    Returns (zip_path, cleanup_fn) where zip_path is a temp ZIP on disk.
    """
    # Normalize Django UploadedFile to a binary file-like
    infile = uploaded_file.file if hasattr(uploaded_file, "file") else uploaded_file
    try:
        infile.seek(0)
    except Exception:
        pass

    tmp_zip = tempfile.NamedTemporaryFile(prefix="xmlsplit_", suffix=".zip", delete=False)
    zip_path = tmp_zip.name
    tmp_zip.close()

    # We'll track an optional normalized-copy path to remove it later
    normalized_path = None

    def _parse_and_write(stream_source):
        """
        stream_source can be the file object or a path (str) for iterparse.
        """
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # iterparse reads incrementally; we only keep minimal nodes in memory
            context = ET.iterparse(stream_source, events=("end",))
            root = None
            for event, elem in context:
                if root is None:
                    root = elem
                # Write each immediate child of root as a separate XML
                if elem is not root and elem in root:
                    first_child = next(iter(elem), None)
                    file_id = _safe_filename(
                        first_child.text if first_child is not None else None
                    )
                    xml_bytes = _XML_DECL + ET.tostring(elem, encoding="utf-8")
                    zf.writestr(f"{file_id}.xml", xml_bytes)
                    elem.clear()
            if root is not None:
                root.clear()

    # First attempt: parse as-is
    try:
        _parse_and_write(infile)
    except ParseError as e:
        msg = str(e).lower()
        if _ENCODING_ERR_SNIPPET in msg:
            # Fallback: normalize prolog to fix bad 'encoding' label (e.g., utf–8)
            normalized_path = _make_normalized_copy(infile)
            _parse_and_write(normalized_path)  # may still raise if truly invalid
        else:
            # Different XML error; re-raise for the view to surface
            raise
    finally:
        trim_now()  # encourage glibc to return memory after heavy parse

    def _cleanup():
        # Remove the output ZIP
        try:
            os.remove(zip_path)
        except OSError:
            pass
        # Remove any normalized temp copy
        if normalized_path:
            try:
                os.remove(normalized_path)
            except OSError:
                pass
        trim_now()

    return zip_path, _cleanup
