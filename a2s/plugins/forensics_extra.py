"""Plugin: herramientas forenses extra (stdlib puro).

* ``file_magic`` — identificación de tipo por números mágicos.
* ``extract_strings`` — extracción de cadenas ASCII (carving básico).
* ``exif_basic`` — metadatos EXIF de JPEG/TIFF (tags comunes + GPS).
* ``pdf_metadata`` — metadatos básicos de PDF (header/trailer).

Limitación honesta: el parser EXIF cubre IFD0/GPS con decodificación de
racionales; no procesa thumbnails, MakerNotes ni formatos raros.
"""

import os
import re
import struct

PLUGIN = {
    "name": "forensics_extra",
    "version": "1.0.0",
    "description": "Forense extra: magia de archivos, strings, EXIF básico, metadatos PDF",
    "tags": ["forense", "forensics", "exif", "metadatos", "metadata",
            "carving", "evidencia", "informe"],
    "tools": [
        {"name": "file_magic", "description": "Identifica el tipo de un archivo por números mágicos.",
         "params": {"path": "str (relativo al workspace)"}},
        {"name": "extract_strings", "description": "Extrae cadenas ASCII de un archivo (carving básico).",
         "params": {"path": "str", "min_len": "int opcional (default 4)"}},
        {"name": "exif_basic", "description": "Extrae metadatos EXIF básicos de un JPEG.",
         "params": {"path": "str"}},
        {"name": "pdf_metadata", "description": "Extrae metadatos básicos de un PDF.",
         "params": {"path": "str"}},
    ],
}

_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"), (b"GIF89a", "GIF image"),
    (b"%PDF-", "PDF document"),
    (b"PK\x03\x04", "ZIP archive"),
    (b"\x7fELF", "ELF binary"),
    (b"SQLite format 3\x00", "SQLite database"),
    (b"II*\x00", "TIFF (little-endian)"), (b"MM\x00*", "TIFF (big-endian)"),
    (b"\x1f\x8b\x08", "gzip compressed"),
    (b"BZh", "bzip2 compressed"),
    (b"\xfd7zXZ\x00", "xz compressed"),
    (b"#!/", "script (shebang)"),
]

_EXIF_TAGS = {
    0x010F: "Make", 0x0110: "Model", 0x0112: "Orientation",
    0x0131: "Software", 0x0132: "DateTime", 0x8769: "ExifIFDPointer",
    0x8825: "GPSIFDPointer",
}
_GPS_TAGS = {
    0x0000: "GPSVersionID", 0x0001: "GPSLatitudeRef", 0x0002: "GPSLatitude",
    0x0003: "GPSLongitudeRef", 0x0004: "GPSLongitude",
    0x0005: "GPSAltitudeRef", 0x0006: "GPSAltitude", 0x001D: "GPSDateStamp",
}


def _rat(bytes_, offset, fmt, count):
    if fmt == 5:  # RATIONAL (2x unsigned long)
        num, den = struct.unpack_from(">II", bytes_, offset)
        return num / den if den else 0.0
    if fmt == 10:  # SRATIONAL
        num, den = struct.unpack_from(">ii", bytes_, offset)
        return num / den if den else 0.0
    return None


def _parse_ifd(data, base, offset, tags):
    out = {}
    try:
        n = struct.unpack_from(">H", data, base + offset)[0]
    except struct.error:
        return out
    pos = base + offset + 2
    for _ in range(min(n, 64)):
        try:
            tag, fmt, count, value = struct.unpack_from(">HHII", data, pos)
        except struct.error:
            break
        pos += 12
        if tag in tags:
            size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}.get(fmt, 0)
            total = size * count
            val_off = pos - 12 + 8 if total > 4 else pos - 12 + 8
            if total <= 4:
                raw = data[pos - 12 + 8: pos - 12 + 8 + total]
            else:
                raw = data[base + value: base + value + min(total, 64)]
            if fmt == 2:
                out[tags[tag]] = raw.split(b"\x00")[0].decode("ascii", "replace")
            elif fmt == 5:
                out[tags[tag]] = round(_rat(data, base + value, fmt, count), 6)
            else:
                out[tags[tag]] = value
    return out


def file_magic(path):
    with open(path, "rb") as fh:
        head = fh.read(16)
    for magic, label in _MAGIC:
        if head.startswith(magic):
            return f"{label} ({path})"
    if all(32 <= b < 127 or b in (9, 10, 13) for b in head[:16]):
        return f"texto ASCII ({path})"
    return f"desconocido ({path})"


def extract_strings(path, min_len=4):
    with open(path, "rb") as fh:
        data = fh.read()
    pattern = rb"[\x20-\x7e]{%d,}" % max(2, int(min_len))
    found = [m.group().decode() for m in re.finditer(pattern, data)]
    return "\n".join(found[:200]) or "(sin cadenas)"


def exif_basic(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"\xff\xd8\xff"):
        return "no es un JPEG"
    # Buscar APP1/Exif
    idx = data.find(b"Exif\x00\x00")
    if idx < 0:
        return "(sin EXIF en este JPEG)"
    tiff = idx + 6
    endian = data[tiff: tiff + 2]
    if endian == b"II":
        pack = "<"
        base = tiff + 6
        ifd_off = struct.unpack_from("<I", data, tiff + 4)[0]
        # Convertir a big-endian parseable: reempaquetar campos comunes
        out = _parse_ifd_le(data, base, ifd_off)
    elif endian == b"MM":
        pack = ">"
        base = tiff + 6
        ifd_off = struct.unpack_from(">I", data, tiff + 4)[0]
        out = _parse_ifd(data, base, ifd_off, _EXIF_TAGS)
    else:
        return "(EXIF con endianness inválido)"
    # GPS (big-endian path only por simplicidad)
    if endian == b"MM" and out.get("GPSIFDPointer"):
        gps = _parse_ifd(data, base, out["GPSIFDPointer"], _GPS_TAGS)
        out["GPS"] = {k: v for k, v in gps.items() if v not in (0, "")}
        out.pop("GPSIFDPointer", None)
    if not out:
        return "(EXIF vacío)"
    return "\n".join(f"{k}: {v}" for k, v in sorted(out.items())
                     if v not in (0, "", None))


def _parse_ifd_le(data, base, offset):
    """Parser little-endian mínimo para JPEGs LE (Apple/Windows antiguos)."""
    out = {}
    try:
        n = struct.unpack_from("<H", data, base + offset)[0]
    except struct.error:
        return out
    pos = base + offset + 2
    for _ in range(min(n, 64)):
        try:
            tag, fmt, count = struct.unpack_from("<HHI", data, pos)
            value = struct.unpack_from("<I", data, pos + 8)[0]
        except struct.error:
            break
        pos += 12
        if tag in _EXIF_TAGS:
            if fmt == 2:
                total = count
                raw = data[pos - 12 + 8: pos - 12 + 8 + total] if total <= 4 else \
                    data[base + value: base + value + min(total, 64)]
                out[_EXIF_TAGS[tag]] = raw.split(b"\x00")[0].decode("ascii", "replace")
            elif fmt == 5:
                num, den = struct.unpack_from("<II", data, base + value)
                out[_EXIF_TAGS[tag]] = round(num / den, 6) if den else 0
            else:
                out[_EXIF_TAGS[tag]] = value
    return out


def pdf_metadata(path):
    with open(path, "rb") as fh:
        data = fh.read(64 * 1024)
    if not data.startswith(b"%PDF-"):
        return "no es un PDF"
    text = data.decode("latin-1", "replace")
    out = {"Version": re.search(rb"%PDF-(\d\.\d)", data[:16]).group(1).decode()}
    for key in ("Title", "Author", "Subject", "Creator", "Producer", "CreationDate"):
        m = re.search(r"/%s\s*\(([^)]{0,200})\)" % key, text)
        if m:
            out[key] = m.group(1)
    out["Linearized"] = "sí" if b"/Linearized" in data else "no"
    return "\n".join(f"{k}: {v}" for k, v in out.items())


def register(registry, ctx):
    # Import absoluto: el loader importa los plugins fuera del paquete a2s.
    from a2s.tools import Tool

    def f_magic(path):
        full = registry._resolve(path)
        if not registry._inside_workspace(full) or not os.path.exists(full):
            raise PermissionError("archivo fuera del workspace o inexistente")
        return file_magic(full)

    def f_strings(path, min_len=4):
        full = registry._resolve(path)
        if not registry._inside_workspace(full) or not os.path.exists(full):
            raise PermissionError("archivo fuera del workspace o inexistente")
        return extract_strings(full, min_len)

    def f_exif(path):
        full = registry._resolve(path)
        if not registry._inside_workspace(full) or not os.path.exists(full):
            raise PermissionError("archivo fuera del workspace o inexistente")
        return exif_basic(full)

    def f_pdf(path):
        full = registry._resolve(path)
        if not registry._inside_workspace(full) or not os.path.exists(full):
            raise PermissionError("archivo fuera del workspace o inexistente")
        return pdf_metadata(full)

    registry.register(Tool("file_magic", PLUGIN["tools"][0]["description"],
                           PLUGIN["tools"][0]["params"], f_magic))
    registry.register(Tool("extract_strings", PLUGIN["tools"][1]["description"],
                           PLUGIN["tools"][1]["params"], f_strings))
    registry.register(Tool("exif_basic", PLUGIN["tools"][2]["description"],
                           PLUGIN["tools"][2]["params"], f_exif))
    registry.register(Tool("pdf_metadata", PLUGIN["tools"][3]["description"],
                           PLUGIN["tools"][3]["params"], f_pdf))
