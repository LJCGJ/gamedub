"""
Monta um .upk sintético (versão 584, sem compressão) com um SoundNodeWave
contendo um Ogg fictício, e verifica load → find_ogg → inject → reload.
Não substitui a validação com um arquivo real do jogo.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gamedub.formats import upk  # noqa: E402


def fstr(s: str) -> bytes:
    b = s.encode("latin-1") + b"\x00"
    return struct.pack("<i", len(b)) + b


def build(tmp: Path) -> Path:
    names = ["None", "Core", "Class", "SoundNodeWave", "Engine", "Claptrap_Hi_01", "Pacote"]
    name_table = b"".join(fstr(n) + struct.pack("<Q", 0) for n in names)

    # imports: Core.Class (classe), Engine.SoundNodeWave (classe do export)
    def nm(i): return struct.pack("<ii", i, 0)
    imports = (nm(1) + nm(2) + struct.pack("<i", 0) + nm(4) +   # Engine (package)
               nm(1) + nm(2) + struct.pack("<i", -1) + nm(3))   # SoundNodeWave, outer=Engine
    ogg = b"OggS" + bytes(range(60))
    # export serial: propriedades "None" + bulk header + ogg
    def export_blob(abs_off):
        props = nm(0)                              # tag None encerra a lista
        bulk = struct.pack("<IIII", 0, len(ogg), len(ogg), abs_off + len(props) + 16)
        return props + bulk + ogg

    # layout: header | names | imports | exports | serial
    header_fixed = (struct.pack("<IHHI", upk.UE3_MAGIC, 584, 57, 0) + fstr("") +
                    struct.pack("<I", 0))
    # placeholders para offsets, calculamos depois
    def header(name_off, exp_off, imp_off):
        h = (struct.pack("<IHHI", upk.UE3_MAGIC, 584, 57, 0) + fstr("") +
             struct.pack("<I", 0) +
             struct.pack("<II", len(names), name_off) +
             struct.pack("<II", 1, exp_off) +
             struct.pack("<II", 2, imp_off) +
             struct.pack("<I", 0) +            # depends
             struct.pack("<IIII", 0, 0, 0, 0) +  # guids/thumbnails (>=584)
             b"\x00" * 16 + struct.pack("<I", 0) +  # guid, generations=0
             struct.pack("<II", 0, 0) +        # engine, cooker
             struct.pack("<I", 0) +            # compression flags
             struct.pack("<I", 0))             # chunk count
        return h

    hlen = len(header(0, 0, 0))
    name_off = hlen
    imp_off = name_off + len(name_table)
    exp_off = imp_off + len(imports)
    exp_len = 4 * 3 + 8 + 4 + 8 + 4 + 4 + 4 + 4 + 16 + 4
    serial_off = exp_off + exp_len
    blob = export_blob(serial_off)
    export = (struct.pack("<iii", -2, 0, 0) + nm(5) + struct.pack("<i", 0) +
              struct.pack("<Q", 0) + struct.pack("<II", len(blob), serial_off) +
              struct.pack("<I", 0) + struct.pack("<I", 0) + b"\x00" * 16 + struct.pack("<I", 0))
    assert len(export) == exp_len
    data = header(name_off, exp_off, imp_off) + name_table + imports + export + blob
    p = tmp / "fake_INT.upk"
    p.write_bytes(data)
    return p, ogg


def test_roundtrip(tmp_path):
    p, ogg = build(tmp_path)
    pkg = upk.load(p)
    assert pkg.version == 584 and not pkg.compressed
    waves = pkg.sound_waves()
    assert len(waves) == 1 and waves[0].name == "Claptrap_Hi_01"
    slot = upk.find_ogg(pkg, waves[0])
    assert slot and pkg.data[slot.data_start:slot.data_start + slot.size] == ogg

    novo = b"OggS" + b"\x11" * 20
    out = upk.inject_same_size(pkg, {pkg.full_name(waves[0]): novo})
    upk.write_uncompressed(pkg, out, tmp_path / "fake_BRA.upk")
    pkg2 = upk.load(tmp_path / "fake_BRA.upk")
    slot2 = upk.find_ogg(pkg2, pkg2.sound_waves()[0])
    got = pkg2.data[slot2.data_start:slot2.data_start + slot2.size]
    assert got.startswith(novo) and len(got) == len(ogg)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_roundtrip(Path(td))
        print("ok")
