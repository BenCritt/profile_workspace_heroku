from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import List, Tuple, Optional
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


def _write_chunk_as_xml(root_tag: str, root_attrib: dict, items: List[ET.Element], out_path: str) -> None:
    """
    Write a new XML file reusing the original root tag/attributes and the given items.
    """
    root_copy = ET.Element(root_tag, root_attrib)
    # Move the elements (no deep copy) to avoid holding duplicates in memory.
    for el in items:
        root_copy.append(el)
    tree = ET.ElementTree(root_copy)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def split_xml_to_zip(uploaded_file, items_per_file: int = 1000) -> ZipBuildResult:
    """
    Split a large XML into smaller XMLs by repeated top-level child under the root.
    Builds a ZIP on disk and returns its path + a working dir for cleanup.

    Memory profile:
      - Source persisted to disk
      - iterparse with element removal from root
      - Parts written to disk
      - ZIP assembled on disk
    """
    if items_per_file <= 0:
        raise ValueError("items_per_file must be >= 1")

    work_dir, xml_path = _copy_uploaded_to_tmp(uploaded_file)

    # Determine final zip name based on upload filename (replace extension with .zip)
    orig = getattr(uploaded_file, "name", "output")
    base = os.path.splitext(os.path.basename(orig))[0]
    zip_path = os.path.join(work_dir, f"{base}.zip")

    parts_dir = os.path.join(work_dir, "parts")
    os.makedirs(parts_dir, exist_ok=True)

    # Parse streaming with depth tracking so we can detect direct children of the root.
    context = ET.iterparse(xml_path, events=("start", "end"))
    root: Optional[ET.Element] = None
    root_tag: Optional[str] = None
    root_attrib: dict = {}
    record_tag: Optional[str] = None

    depth = 0
    batch: List[ET.Element] = []
    part_index = 0

    for event, elem in context:
        if event == "start":
            depth += 1
            if root is None:
                # First element is the root
                root = elem
                root_tag = root.tag
                root_attrib = dict(root.attrib)
            elif depth == 2 and record_tag is None:
                # First direct child under the root defines the record unit
                record_tag = elem.tag

        elif event == "end":
            if record_tag and root and elem.tag == record_tag and depth == 2:
                # Completed one direct child (record) — detach from root and queue it
                batch.append(elem)
                try:
                    root.remove(elem)  # element is a direct child
                except Exception:
                    pass

                if len(batch) >= items_per_file:
                    out_name = f"part_{part_index:04d}.xml"
                    out_path = os.path.join(parts_dir, out_name)
                    _write_chunk_as_xml(root_tag, root_attrib, batch, out_path)
                    # Clear elements after writing
                    for el in batch:
                        el.clear()
                    batch.clear()
                    part_index += 1

            # Clear closed elements (other than root) to limit tree growth
            if root is not None and elem is not root:
                elem.clear()

            depth -= 1

    # Remainder
    if batch:
        out_name = f"part_{part_index:04d}.xml"
        out_path = os.path.join(parts_dir, out_name)
        _write_chunk_as_xml(root_tag, root_attrib, batch, out_path)
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
