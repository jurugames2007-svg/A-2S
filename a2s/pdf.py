"""Motor PDF mínimo en stdlib (A4, Helvetica, WinAnsi)."""

from __future__ import annotations

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN = 52.0
USABLE = PAGE_W - 2 * MARGIN
_W = {"F1": 0.505, "F2": 0.545, "F3": 0.52, "F4": 0.60}


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class MiniPDF:
    def __init__(self, title: str) -> None:
        self.title = title
        self.pages: list[list[str]] = [[]]
        self.y = PAGE_H - MARGIN
        self.footer = title[:90]

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN

    def _space(self, need: float) -> None:
        if self.y - need < MARGIN + 26:
            self._new_page()

    def _emit_line(self, x: float, font: str, size: float, text: str) -> None:
        raw = f"BT /{font} {size:.1f} Tf {x:.1f} {self.y:.1f} Td ({_esc(text)}) Tj ET"
        self.pages[-1].append(raw.encode("cp1252", errors="replace").decode("latin-1"))
        self.y -= size * 1.32

    def _wrap(self, text: str, font: str, size: float, width: float) -> list[str]:
        lines, cur = [], ""
        limit = max(10, int(width / (_W[font] * size)))
        for word in text.split():
            cand = f"{cur} {word}".strip()
            if len(cand) <= limit:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines or [""]

    def h1(self, text: str) -> None:
        self._new_page()
        self._space(40)
        self._emit_line(MARGIN, "F2", 17, text)
        self.y -= 6
        self.rule()
        self.y -= 8

    def h2(self, text: str) -> None:
        self._space(34)
        self.y -= 6
        self._emit_line(MARGIN, "F2", 12.5, text)
        self.y -= 3

    def h3(self, text: str) -> None:
        self._space(26)
        self._emit_line(MARGIN, "F2", 10.5, text)
        self.y -= 1

    def para(self, text: str, size: float = 9.3, indent: float = 0.0,
             font: str = "F1") -> None:
        for ln in self._wrap(text, font, size, USABLE - indent):
            self._space(size * 1.32)
            self._emit_line(MARGIN + indent, font, size, ln)
        self.y -= 3.5

    def bullet(self, text: str, size: float = 9.3, mark: str = "-") -> None:
        for i, ln in enumerate(self._wrap(text, "F1", size, USABLE - 14)):
            self._space(size * 1.32)
            self._emit_line(MARGIN + (0 if i else 0), "F1", size,
                            (f"{mark} " if i == 0 else "  ") + ln)
        self.y -= 2.2

    def kv(self, key: str, value: str) -> None:
        self._space(12)
        self._emit_line(MARGIN, "F2", 9.0, key)
        self._emit_line(MARGIN + 150, "F1", 9.0, value)
        self.y -= 1.5

    def rule(self, light: bool = True) -> None:
        gray = "0.55" if light else "0.1"
        w = "0.5" if light else "1.2"
        self.pages[-1].append(f"{gray} G {w} w {MARGIN} {self.y:.1f} m "
                              f"{PAGE_W - MARGIN} {self.y:.1f} l S 0 G")

    def spacer(self, h: float = 6.0) -> None:
        self.y -= h

    def cover(self, title: str, subtitle: str = "", note: str = "") -> None:
        self.spacer(160)
        self.para(title, size=26, font="F2")
        if subtitle:
            self.para(subtitle, size=12, font="F3")
        self.spacer(16)
        if note:
            self.para(note, size=10)

    def save(self, path: str) -> int:
        objs: list[bytes] = [b""]
        n_pages = len(self.pages)

        def add(data: bytes) -> int:
            objs.append(data)
            return len(objs) - 1

        font_ids = {}
        for name, base in [("F1", "Helvetica"), ("F2", "Helvetica-Bold"),
                           ("F3", "Helvetica-Oblique"), ("F4", "Courier")]:
            fid = add(f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
                      f"/Encoding /WinAnsiEncoding >>".encode())
            font_ids[name] = fid
        res = "<< /Font << " + " ".join(
            f"/{k} {v} 0 R" for k, v in font_ids.items()) + " >> >>"

        content_ids: list[int] = []
        for i, ops in enumerate(self.pages):
            footer = (f"BT /F3 7.5 Tf {MARGIN} 34 Td ({_esc(self.footer)}) Tj ET "
                      f"BT /F1 8 Tf {PAGE_W - MARGIN - 30} 34 Td "
                      f"({_esc(f'{i + 1} / {n_pages}')}) Tj ET")
            stream = ("\n".join(ops) + "\n" + footer).encode("cp1252", errors="replace")
            cid = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
                      + stream + b"\nendstream")
            content_ids.append(cid)
        pages_id_placeholder = len(objs) + n_pages
        page_obj_ids = []
        for cid in content_ids:
            pid = add((f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
                       f"/MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources {res} "
                       f"/Contents {cid} 0 R >>").encode())
            page_obj_ids.append(pid)
        kids = " ".join(f"{p} 0 R" for p in page_obj_ids)
        pages_id = add(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
        assert pages_id == pages_id_placeholder, (pages_id, pages_id_placeholder)
        cat_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
        add(f"<< /Title ({_esc(self.title)}) /Producer (A2S MiniPDF stdlib) >>".encode())

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0] * (len(objs))
        for idx in range(1, len(objs)):
            offsets[idx] = len(out)
            out += f"{idx} 0 obj\n".encode() + objs[idx] + b"\nendobj\n"
        xref_pos = len(out)
        out += f"xref\n0 {len(objs)}\n".encode()
        out += b"0000000000 65535 f \n"
        for idx in range(1, len(objs)):
            out += f"{offsets[idx]:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {len(objs)} /Root {cat_id} 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF\n").encode()
        with open(path, "wb") as fh:
            fh.write(bytes(out))
        return n_pages
