# projects/xml_splitter_utils.py
from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED


@dataclass
class ZipBuildResult:
    """Paths so the view can stream the zip, then clean everything."""
    zip_path: str
    work_dir: str   # directory holding temp xml and intermediates


def _copy_uploaded_to_tmp(uploaded_file) -> Tuple[str, str]:
    """
    Persist Django UploadedFile to disk using chunks() to avoid RAM spikes.
    Returns (tmp_dir, xml_path).
    """
    tmp_dir = tempfile.mkdtemp(prefix="xmlsplit_")
    xml_path = os.path.join(tmp_dir, "source.xml")
    with open(xml_path, "wb") as out:
        for chunk in uploaded_file.chunks():
            out.write(chunk)
    return tmp_dir, xml_path


# --- Robust encoding normalizer (fixes bogus XML prologs/BOMs) ----------------

_BOMS = {
    b"\x00\x00\xfe\xff": "utf-32-be",
    b"\xff\xfe\x00\x00": "utf-32-le",
    b"\xfe\xff": "utf-16-be",
    b"\xff\xfe": "utf-16-le",
    b"\xef\xbb\xbf": "utf-8-sig",
}

_XML_DECL_RE = re.compile(r'^\s*<\?xml[^>]*\?>', re.I | re.S)
_XML_ENC_RE  = re.compile(r'encoding=["\']([^"\']+)["\']', re.I)

def _detect_bom_encoding(head: bytes) -> Optional[str]:
    for sig, enc in sorted(_BOMS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if head.startswith(sig):
            return enc
    return None

def _guess_textual_encoding(head: bytes) -> str:
    # Heuristic when no BOM: assume UTF-8 unless there are many NULs.
    sample = head[:2048]
    nul_ratio = sample.count(b"\x00") / max(1, len(sample))
    return "utf-8" if nul_ratio <= 0.10 else "utf-8"

def _normalize_xml_to_utf8(src_path: str) -> str:
    """
    Ensure file is valid UTF-8 XML with a correct prolog:
        <?xml version="1.0" encoding="UTF-8"?>
    Returns path to normalized file (or the original if already OK).
    """
    with open(src_path, "rb") as f:
        head = f.read(4096)

    enc = _detect_bom_encoding(head) or _guess_textual_encoding(head)

    try:
        head_text = head.decode(enc, errors="replace")
    except LookupError:
        enc = "utf-8"
        head_text = head.decode(enc, errors="replace")

    decl_match = _XML_DECL_RE.search(head_text)
    declared = None
    if decl_match:
        enc_match = _XML_ENC_RE.search(decl_match.group(0))
        if enc_match:
            declared = enc_match.group(1).strip().lower()

    if (enc in ("utf-8", "utf-8-sig")) and (declared is None or declared == "utf-8"):
        return src_path  # already fine

    norm_path = os.path.join(os.path.dirname(src_path), "source_norm.xml")
    with open(src_path, "rb") as fin, open(norm_path, "w", encoding="utf-8", newline="") as fout:
        reader = io.TextIOWrapper(fin, encoding=enc, errors="replace", newline="")
        first = reader.read(4096)
        first = _XML_DECL_RE.sub("", first, count=1)  # drop old prolog
        fout.write('<?xml version="1.0" encoding="UTF-8"?>')
        fout.write(first)
        shutil.copyfileobj(reader, fout)
    return norm_path

# -----------------------------------------------------------------------------


def _register_namespaces(ns_pairs: List[Tuple[str, str]]) -> None:
    """
    Preserve original namespace prefixes in output by registering them globally.
    Safe to call repeatedly with the same pairs.
    """
    for prefix, uri in ns_pairs:
        try:
            # Empty prefix means default namespace
            ET.register_namespace(prefix or "", uri)
        except Exception:
            # Ignore duplicates or odd registrations
            pass


def _write_chunk_as_xml(
    root_tag: str,
    root_attrib: dict,
    items: List[ET.Element],
    out_path: str,
    ns_pairs: List[Tuple[str, str]],
) -> None:
    """
    Write a new XML file reusing the original root tag/attributes and the given items.
    """
    _register_namespaces(ns_pairs)
    root_copy = ET.Element(root_tag, root_attrib)
    for el in items:  # move elements (no deep copy)
        root_copy.append(el)
    tree = ET.ElementTree(root_copy)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def split_xml_to_zip(uploaded_file, items_per_file: int = 1000) -> ZipBuildResult:
    """
    Split a large XML into smaller XMLs by repeated top-level child under the root.
    Builds a ZIP on disk and returns its path + a working dir for cleanup.

    Memory profile:
      - Source persisted to disk
      - Normalize to UTF-8 if the prolog/bytes disagree
      - iterparse with detaching and selective clearing
      - Parts written to disk
      - ZIP assembled on disk
    """
    # Defensive cast and guard
    try:
        items_per_file = int(items_per_file)
    except Exception:
        items_per_file = 1000
    if items_per_file <= 0:
        raise ValueError("items_per_file must be >= 1")

    work_dir, xml_path = _copy_uploaded_to_tmp(uploaded_file)
    xml_path = _normalize_xml_to_utf8(xml_path)

    # Determine final zip name based on upload filename (replace extension with .zip)
    orig = getattr(uploaded_file, "name", "output")
    base = os.path.splitext(os.path.basename(orig))[0]
    zip_path = os.path.join(work_dir, f"{base}.zip")

    parts_dir = os.path.join(work_dir, "parts")
    os.makedirs(parts_dir, exist_ok=True)

    # Parse streaming; capture namespaces to preserve prefixes
    context = ET.iterparse(xml_path, events=("start", "end", "start-ns"))
    ns_pairs: List[Tuple[str, str]] = []
    seen_ns: Dict[Tuple[str, str], bool] = {}

    root: Optional[ET.Element] = None
    root_tag: Optional[str] = None
    root_attrib: dict = {}
    record_tag: Optional[str] = None

    depth = 0
    batch: List[ET.Element] = []
    part_index = 0

    for event, elem in context:
        if event == "start-ns":
            # elem is a (prefix, uri) tuple for this event
            prefix, uri = elem  # type: ignore
            key = (prefix or "", uri)
            if key not in seen_ns:
                seen_ns[key] = True
                ns_pairs.append(key)
            continue  # not a node start/end

        if event == "start":
            depth += 1
            if root is None:
                root = elem
                root_tag = root.tag
                root_attrib = dict(root.attrib)
            elif depth == 2 and record_tag is None:
                # First direct child under the root defines the record unit (e.g., "Order")
                record_tag = elem.tag

        elif event == "end":
            is_record = bool(record_tag and root and elem.tag == record_tag and depth == 2)

            if is_record:
                # Completed one direct child (record)
                batch.append(elem)
                try:
                    root.remove(elem)  # detach from live tree to keep memory flat
                except Exception:
                    pass

                if len(batch) >= items_per_file:
                    out_name = f"part_{part_index:04d}.xml"
                    out_path = os.path.join(parts_dir, out_name)
                    _write_chunk_as_xml(root_tag, root_attrib, batch, out_path, ns_pairs)
                    # Now clear the elements we just wrote
                    for el in batch:
                        el.clear()
                    batch.clear()
                    part_index += 1

                # DO NOT clear `elem` here; it’s in the batch and will be cleared after writing
            else:
                # Clear non-record elements aggressively (keep parsing memory bounded)
                if root is not None and elem is not root:
                    elem.clear()

            depth -= 1

    # Remainder
    if batch:
        out_name = f"part_{part_index:04d}.xml"
        out_path = os.path.join(parts_dir, out_name)
        _write_chunk_as_xml(root_tag, root_attrib, batch, out_path, ns_pairs)
        for el in batch:
            el.clear()
        batch.clear()

    # Build the zip on disk
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED, compresslevel=6) as zf:
        for fname in sorted(os.listdir(parts_dir)):
            if fname.lower().endswith(".xml"):
                zf.write(os.path.join(parts_dir, fname), arcname=fname)

    # Drop the parts to keep only the finished zip in work_dir
    try:
        shutil.rmtree(parts_dir, ignore_errors=True)
    except Exception:
        pass

    return ZipBuildResult(zip_path=zip_path, work_dir=work_dir)
