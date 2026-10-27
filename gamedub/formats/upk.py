"""
Leitor/escritor mínimo de pacotes Unreal Engine 3 (.upk) para extrair e
reinjetar SoundNodeWave.

Alvo inicial: Borderlands 1 PC (package version 584, licensee 57).
Suporta pacotes comprimidos em LZO (chunks) e descomprimidos.

Layout de referência (UE3, versão >= 475):

  header
    u32  magic            0x9E2A83C1
    u16  version, u16 licensee
    u32  header_size
    str  folder_name
    u32  package_flags
    u32  name_count, u32 name_offset
    u32  export_count, u32 export_offset
    u32  import_count, u32 import_offset
    u32  depends_offset
    guid[16], generations[], engine_ver, cooker_ver
    u32  compression_flags
    chunks[] { u32 uncomp_off, u32 uncomp_size, u32 comp_off, u32 comp_size }

  chunk comprimido
    u32 magic, u32 block_size, u32 comp_size, u32 uncomp_size
    blocks[] { u32 comp_size, u32 uncomp_size }   (até somar uncomp_size)
    dados LZO de cada bloco, em sequência

Tudo aqui foi escrito a partir da documentação pública do formato e ainda
precisa ser validado contra um .upk real do jogo.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

UE3_MAGIC = 0x9E2A83C1


class Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def u8(self):  return self._unpack("<B", 1)
    def u16(self): return self._unpack("<H", 2)
    def i32(self): return self._unpack("<i", 4)
    def u32(self): return self._unpack("<I", 4)
    def i64(self): return self._unpack("<q", 8)
    def u64(self): return self._unpack("<Q", 8)

    def _unpack(self, fmt, size):
        (v,) = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return v

    def bytes(self, n):
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def fstring(self) -> str:
        n = self.i32()
        if n == 0:
            return ""
        if n < 0:                       # UTF-16
            raw = self.bytes(-n * 2)
            return raw.decode("utf-16-le").rstrip("\x00")
        raw = self.bytes(n)
        return raw.decode("latin-1").rstrip("\x00")


@dataclass
class Export:
    index: int
    class_ref: int
    super_ref: int
    outer_ref: int
    name: str
    serial_size: int
    serial_offset: int
    # posição absoluta do campo serial_offset dentro do arquivo descomprimido,
    # necessária se um dia for preciso reescrever offsets
    offset_field_pos: int = 0


@dataclass
class Package:
    path: Path
    version: int
    licensee: int
    data: bytes                      # conteúdo já descomprimido
    names: list[str] = field(default_factory=list)
    imports: list[tuple[str, str, int, str]] = field(default_factory=list)
    exports: list[Export] = field(default_factory=list)
    compressed: bool = False

    # ----- resolução de referências --------------------------------------
    def ref_name(self, ref: int) -> str:
        """ref > 0 → export, ref < 0 → import, 0 → None (convenção UE3)."""
        if ref > 0:
            return self.exports[ref - 1].name
        if ref < 0:
            return self.imports[-ref - 1][3]
        return "None"

    def class_name(self, exp: Export) -> str:
        return self.ref_name(exp.class_ref)

    def full_name(self, exp: Export) -> str:
        parts = [exp.name]
        outer = exp.outer_ref
        guard = 0
        while outer > 0 and guard < 32:
            o = self.exports[outer - 1]
            parts.append(o.name)
            outer = o.outer_ref
            guard += 1
        return ".".join(reversed(parts))

    def export_bytes(self, exp: Export) -> bytes:
        return self.data[exp.serial_offset:exp.serial_offset + exp.serial_size]

    def sound_waves(self) -> list[Export]:
        return [e for e in self.exports if self.class_name(e) == "SoundNodeWave"]


# --------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------

def _read_header_and_chunks(raw: bytes):
    r = Reader(raw)
    if r.u32() != UE3_MAGIC:
        raise ValueError("não é um pacote UE3 (magic inválido)")
    version = r.u16()
    licensee = r.u16()
    header_size = r.u32() if version >= 249 else 0
    folder = r.fstring() if version >= 269 else ""
    package_flags = r.u32()
    name_count, name_offset = r.u32(), r.u32()
    export_count, export_offset = r.u32(), r.u32()
    import_count, import_offset = r.u32(), r.u32()
    depends_offset = r.u32() if version >= 415 else 0
    if version >= 584:                 # ImportExportGuidsOffset, ImportGuidsCount, ExportGuidsCount, ThumbnailTableOffset
        r.u32(); r.u32(); r.u32(); r.u32()
    r.bytes(16)                        # GUID
    gen_count = r.u32()
    for _ in range(gen_count):
        r.u32(); r.u32(); r.u32()      # export count, name count, net object count
    r.u32()                            # engine version
    r.u32()                            # cooker version
    compression_flags = r.u32() if version >= 334 else 0
    chunks = []
    if version >= 334:
        n = r.u32()
        for _ in range(n):
            chunks.append((r.u32(), r.u32(), r.u32(), r.u32()))
    tables = dict(
        version=version, licensee=licensee, header_size=header_size,
        name_count=name_count, name_offset=name_offset,
        export_count=export_count, export_offset=export_offset,
        import_count=import_count, import_offset=import_offset,
        compression_flags=compression_flags,
    )
    return tables, chunks


def _decompress_chunks(raw: bytes, chunks) -> bytes:
    import lzo  # python-lzo

    total = max(u_off + u_size for u_off, u_size, _, _ in chunks)
    out = bytearray(max(total, len(raw)))
    # tudo antes do primeiro chunk (o header) fica como está
    first = min(c[0] for c in chunks)
    out[:first] = raw[:first]

    for u_off, u_size, c_off, c_size in chunks:
        r = Reader(raw, c_off)
        if r.u32() != UE3_MAGIC:
            raise ValueError(f"chunk em {c_off:#x} sem magic")
        block_size = r.u32()
        comp_total = r.u32()
        uncomp_total = r.u32()
        blocks = []
        acc = 0
        while acc < uncomp_total:
            cs, us = r.u32(), r.u32()
            blocks.append((cs, us))
            acc += us
        cursor = u_off
        for cs, us in blocks:
            blob = r.bytes(cs)
            dec = lzo.decompress(blob, False, us)
            out[cursor:cursor + us] = dec
            cursor += us
    return bytes(out)


def load(path: str | Path) -> Package:
    path = Path(path)
    raw = path.read_bytes()
    tables, chunks = _read_header_and_chunks(raw)
    compressed = bool(chunks)
    data = _decompress_chunks(raw, chunks) if compressed else raw

    pkg = Package(path=path, version=tables["version"], licensee=tables["licensee"],
                  data=data, compressed=compressed)

    # --- tabela de nomes
    r = Reader(data, tables["name_offset"])
    for _ in range(tables["name_count"]):
        s = r.fstring()
        if pkg.version >= 141:
            r.u64()                    # flags
        pkg.names.append(s)

    def fname(rd: Reader) -> str:
        idx = rd.i32()
        num = rd.i32()
        base = pkg.names[idx] if 0 <= idx < len(pkg.names) else f"<name {idx}>"
        return f"{base}_{num - 1}" if num > 0 else base

    # --- imports
    r = Reader(data, tables["import_offset"])
    for _ in range(tables["import_count"]):
        cls_pkg = fname(r)
        cls = fname(r)
        outer = r.i32()
        name = fname(r)
        pkg.imports.append((cls_pkg, cls, outer, name))

    # --- exports
    r = Reader(data, tables["export_offset"])
    for i in range(tables["export_count"]):
        class_ref = r.i32()
        super_ref = r.i32()
        outer_ref = r.i32()
        name = fname(r)
        archetype = r.i32()
        if pkg.version >= 195:
            r.u64()                    # object flags
        serial_size = r.u32()
        off_pos = r.pos
        serial_offset = r.u32()
        if pkg.version >= 247:
            r.u32()                    # export flags
        if pkg.version >= 322:
            n = r.u32()                # net object count
            r.bytes(4 * n)
        r.bytes(16)                    # guid
        if pkg.version >= 475:
            r.u32()                    # package flags
        pkg.exports.append(Export(i + 1, class_ref, super_ref, outer_ref, name,
                                  serial_size, serial_offset, off_pos))
    return pkg


# --------------------------------------------------------------------------
# SoundNodeWave → Ogg
# --------------------------------------------------------------------------

@dataclass
class OggSlot:
    export: Export
    data_start: int   # offset absoluto do primeiro byte "OggS" no pacote descomprimido
    size: int         # tamanho declarado no bulk header


def find_ogg(pkg: Package, exp: Export) -> OggSlot | None:
    """
    Localiza o bloco Ogg dentro de um SoundNodeWave.

    O UE3 grava cada bulk data como:
        u32 flags, u32 element_count, u32 size_on_disk, u32 offset_in_file, <bytes>
    Procuramos o magic "OggS" dentro do export e conferimos se os 4 bytes
    imediatamente anteriores batem com o offset absoluto — isso confirma
    que achamos o início real do bulk e não um "OggS" interno.
    """
    blob = pkg.export_bytes(exp)
    start = 0
    while True:
        i = blob.find(b"OggS", start)
        if i < 0:
            return None
        abs_pos = exp.serial_offset + i
        if i >= 16:
            size_on_disk, offset_in_file = struct.unpack_from("<II", blob, i - 8)
            if offset_in_file == abs_pos and 0 < size_on_disk <= len(blob) - i:
                return OggSlot(exp, abs_pos, size_on_disk)
        start = i + 4


def extract_all(pkg: Package, out_dir: str | Path) -> list[tuple[Export, Path, int]]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for exp in pkg.sound_waves():
        slot = find_ogg(pkg, exp)
        if slot is None:
            continue
        name = pkg.full_name(exp).replace("/", "_")
        dest = out_dir / f"{name}.ogg"
        dest.write_bytes(pkg.data[slot.data_start:slot.data_start + slot.size])
        results.append((exp, dest, slot.size))
    return results


# --------------------------------------------------------------------------
# Reinjeção (mesmo tamanho)
# --------------------------------------------------------------------------

def inject_same_size(pkg: Package, replacements: dict[str, bytes]) -> bytes:
    """
    replacements: {full_name_do_export: novo_ogg}
    Cada novo Ogg precisa ter tamanho <= original; o restante é zerado.
    Devolve os bytes do pacote *descomprimido* com os blocos substituídos.
    """
    buf = bytearray(pkg.data)
    for exp in pkg.sound_waves():
        key = pkg.full_name(exp)
        if key not in replacements:
            continue
        slot = find_ogg(pkg, exp)
        if slot is None:
            raise ValueError(f"{key}: Ogg original não localizado")
        new = replacements[key]
        if len(new) > slot.size:
            raise ValueError(f"{key}: novo Ogg tem {len(new)} bytes, limite {slot.size}")
        buf[slot.data_start:slot.data_start + slot.size] = new + b"\x00" * (slot.size - len(new))
    return bytes(buf)


def write_uncompressed(pkg: Package, new_data: bytes, dest: str | Path):
    """
    Grava o pacote descomprimido zerando a tabela de chunks e o
    compression_flags. O UE3 aceita pacotes sem compressão, então para a
    prova de conceito evitamos recomprimir.
    """
    buf = bytearray(new_data)
    tables, chunks = _read_header_and_chunks(pkg.path.read_bytes())
    if chunks:
        # reescreve compression_flags = 0 e chunk count = 0 no header
        r = Reader(bytes(buf))
        r.u32(); r.u16(); r.u16()
        if pkg.version >= 249: r.u32()
        if pkg.version >= 269: r.fstring()
        r.u32(); r.u32(); r.u32(); r.u32(); r.u32(); r.u32(); r.u32()
        if pkg.version >= 415: r.u32()
        if pkg.version >= 584: r.u32(); r.u32(); r.u32(); r.u32()
        r.bytes(16)
        n = r.u32()
        r.bytes(12 * n)
        r.u32(); r.u32()
        flags_pos = r.pos
        struct.pack_into("<I", buf, flags_pos, 0)
        struct.pack_into("<I", buf, flags_pos + 4, 0)
        # os registros de chunk ficam como lixo após o header; o UE3 não os lê
        # quando count == 0. Se o jogo reclamar, trocar por remoção + rebase.
    Path(dest).write_bytes(bytes(buf))
