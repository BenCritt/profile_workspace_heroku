# projects/xml_splitter_utils.py

import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ParseError

from .mem_utils import trim_now

_XML_DECL = b'<?xml version="1.0" encoding="utf-8"?>\n'

# Non-ASCII hyphens that sometimes sneak into "utf-8"
_BAD_HYPHENS = [
    b"\xe2\x80\x90",  # U+2010 hyphen
    b"\xe2\x80\x91",  # U+2011 non-breaking hyphen
    b"\xe2\x80\x92",  # U+2012 figure dash
    b"\xe2\x80\x93",  # U+2013 en dash
    b"\xe2\x80\x94",  # U+2014 em dash
    b"\xe2\x88\x92",  # U+2212 minus sign
]

# Curly quotes that sometimes wrap the encoding value
_BAD_DQUOTES = [b"\xe2\x80\x9c", b"\xe2\x80\x9d"]  # U+201C/U+201D
_BAD_SQUOTES = [b"\xe2\x80\x98", b"\xe2\x80\x99"]  # U+2018/U+2019

_ENCODING_ERR_SNIPPET = "encoding specified in xml declaration is incorrect"


def _safe_filename(text: str | None) -> str:
    if not text:
        return "unnamed"
    cleaned = re.sub(r"[^\w\-\.]", "_", text.strip())
    return cleaned or "unnamed"


def _normalize_prolog_chunk(head: bytes) -> bytes:
    """
    Normalize weird enc labels & punctuation in the XML declaration (first ~4 KiB):
      - Replace smart quotes with ASCII quotes
      - Replace smart hyphens with ASCII '-'
      - Normalize utf8/UTF8/utf_8 → utf-8 (case-insensitive)
    """
    if b"<?xml" not in head:
        return head

    prolog_end = head.find(b"?>")
    search_end = prolog_end + 2 if prolog_end != -1 else min(len(head), 4096)
    prolog = head[:search_end]
    rest = head[search_end:]

    # Replace curly quotes
    for q in _BAD_DQUOTES:
        prolog = prolog.replace(q, b'"')
    for q in _BAD_SQUOTES:
        prolog = prolog.replace(q, b"'")

    # Replace weird hyphens
    for bad in _BAD_HYPHENS:
        prolog = prolog.replace(bad, b"-")

    # Normalize common utf8 variants to utf-8 (case-insensitive)
    prolog = re.sub(
        br'(?i)(encoding\s*=\s*["\'])utf_?8(["\'])',
        br"\1utf-8\2",
        prolog,
        count=1,
    )

    return prolog + rest


def _force_clean_prolog(head: bytes) -> bytes:
    """
    Hard-replace any existing XML declaration with a canonical utf-8 declaration.
    If no declaration found, just prefix one.
    """
    if b"<?xml" in head:
        end = head.find(b"?>")
        if end != -1:
            return _XML_DECL + head[end + 2 :]
    # No declaration found — prepend one
    return _XML_DECL + head


def _make_rewritten_copy(src_file, rewriter) -> str:
    """
    Create a temp file that is a byte-for-byte copy of src_file,
    except the first few KB are rewritten by `rewriter(head_bytes)`.
    Returns the temp file path.
    """
    try:
        src_file.seek(0)
    except Exception:
        pass

    tmpf = tempfile.NamedTemporaryFile(prefix="xmlnorm_", suffix=".xml", delete=False)
    tmp_path = tmpf.name

    head = src_file.read(4096)
    fixed_head = rewriter(head)
    tmpf.write(fixed_head)

    # Stream-copy the remainder
    chunk = src_file.read(64 * 1024)
    while chunk:
        tmpf.write(chunk)
        chunk = src_file.read(64 * 1024)

    tmpf.flush()
    tmpf.close()

    try:
        src_file.seek(0)
    except Exception:
        pass

    return tmp_path


def split_xml_to_zip(uploaded_file):
    """
    Stream-split a large XML without loading it all into memory.
    Robust to bad encoding labels/quotes in the XML declaration.

    Returns (zip_path, cleanup_fn) where zip_path is a temp ZIP on disk.
    """
    infile = uploaded_file.file if hasattr(uploaded_file, "file") else uploaded_file
    try:
        infile.seek(0)
    except Exception:
        pass

    tmp_zip = tempfile.NamedTemporaryFile(prefix="xmlsplit_", suffix=".zip", delete=False)
    zip_path = tmp_zip.name
    tmp_zip.close()

    normalized_path = None
    forced_decl_path = None

    def _parse_and_write(stream_source):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            context = ET.iterparse(stream_source, events=("end",))
            root = None
            for _event, elem in context:
                if root is None:
                    root = elem
                if elem is not root and elem in root:
                    first_child = next(iter(elem), None)
                    file_id = _safe_filename(first_child.text if first_child is not None else None)
                    xml_bytes = _XML_DECL + ET.tostring(elem, encoding="utf-8")
                    zf.writestr(f"{file_id}.xml", xml_bytes)
                    elem.clear()
            if root is not None:
                root.clear()

    try:
        # 1) Try as-is
        _parse_and_write(infile)
    except ParseError as e1:
        msg1 = str(e1).lower()
        if _ENCODING_ERR_SNIPPET in msg1:
            # 2) Try normalized prolog (smart quotes/hyphens; utf8→utf-8)
            normalized_path = _make_rewritten_copy(infile, _normalize_prolog_chunk)
            try:
                _parse_and_write(normalized_path)
            except ParseError as e2:
                msg2 = str(e2).lower()
                if _ENCODING_ERR_SNIPPET in msg2:
                    # 3) Final fallback: hard-replace the whole declaration
                    forced_decl_path = _make_rewritten_copy(infile, _force_clean_prolog)
                    _parse_and_write(forced_decl_path)
                else:
                    raise
        else:
            raise
    finally:
        trim_now()

    def _cleanup():
        # remove output ZIP
        try:
            os.remove(zip_path)
        except OSError:
            pass
        # remove any temp normalized copies
        for p in (normalized_path, forced_decl_path):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass
        trim_now()

    return zip_path, _cleanup
