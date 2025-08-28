import io, re, zipfile, xml.etree.ElementTree as ET

_XML_DECL = b'<?xml version="1.0" encoding="utf-8"?>\n'

def _safe_filename(text: str | None) -> str:
    """
    Sanitise the ID value so it is safe for a filename.
    Returns 'unnamed' if the value is missing or blank.
    """
    if not text:                     # catches None and empty string
        return "unnamed"
    cleaned = re.sub(r"[^\w\-\.]", "_", text.strip())
    return cleaned or "unnamed"

def split_xml_to_zip(uploaded_file) -> io.BytesIO:
    raw = uploaded_file.read()
    xml_text = re.sub(
        rb'encoding="[^"]+"', b'encoding="utf-8"', raw, count=1, flags=re.I
    ).decode("utf-8", "replace")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        # Bad XML – e.g. missing tag, unescaped ampersand, etc.
        raise ValueError("The uploaded file is not well‑formed XML.") from exc

    if not list(root):
        # Root exists but contains no child objects
        raise ValueError("The XML contains no <Order>, <Product>, or similar objects.")

    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zf:
        for obj in root:
            first_child = next(iter(obj), None)
            file_id = _safe_filename(first_child.text if first_child is not None else None)
            xml_bytes = _XML_DECL + ET.tostring(obj, encoding="utf-8")
            zf.writestr(f"{file_id}.xml", xml_bytes)

    zip_io.seek(0)
    return zip_io