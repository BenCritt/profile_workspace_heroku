import io, os, re, tempfile, zipfile, xml.etree.ElementTree as ET
from .mem_utils import trim_now

_XML_DECL = b'<?xml version="1.0" encoding="utf-8"?>\n'

def _safe_filename(text: str | None) -> str:
    if not text:
        return "unnamed"
    cleaned = re.sub(r"[^\w\-\.]", "_", text.strip())
    return cleaned or "unnamed"

def split_xml_to_zip(uploaded_file):
    """
    Stream-split a large XML without loading it all into memory.
    Returns (file_path, cleanup_fn) where file_path is a temp ZIP on disk.
    """
    # Force Django to give us a file-like obj (avoids large in-memory buffers)
    infile = uploaded_file.file if hasattr(uploaded_file, "file") else uploaded_file

    tmpf = tempfile.NamedTemporaryFile(prefix="xmlsplit_", suffix=".zip", delete=False)
    tmp_path = tmpf.name

    with zipfile.ZipFile(tmpf, "w", zipfile.ZIP_DEFLATED) as zf:
        # iterparse walks the tree incrementally; clear() frees nodes as we go
        context = ET.iterparse(infile, events=("end",))
        root = None
        for event, elem in context:
            if root is None:
                root = elem  # first element seen is the root
            # Write each immediate child of root as its own file
            if elem is not root and elem in root:
                first_child = next(iter(elem), None)
                file_id = _safe_filename(first_child.text if first_child is not None else None)
                xml_bytes = _XML_DECL + ET.tostring(elem, encoding="utf-8")
                zf.writestr(f"{file_id}.xml", xml_bytes)
                # free memory for processed element
                elem.clear()
        # free the root too
        if root is not None:
            root.clear()

    tmpf.close()
    trim_now()

    def _cleanup():
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return tmp_path, _cleanup
