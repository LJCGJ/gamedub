"""Plugin de formato: pacotes Unreal Engine 3 (.upk / .u / .umap)."""
from __future__ import annotations

from pathlib import Path

from . import upk


class UpkPlugin:
    name = "upk"
    extensions = (".upk", ".u", ".umap")

    def describe(self, pacote) -> str:
        pkg = upk.load(pacote)
        waves = pkg.sound_waves()
        linhas = [
            f"UE3 versão {pkg.version}/{pkg.licensee}  comprimido={pkg.compressed}",
            f"nomes={len(pkg.names)} imports={len(pkg.imports)} exports={len(pkg.exports)}",
            f"SoundNodeWave: {len(waves)}",
        ]
        classes: dict[str, int] = {}
        for e in pkg.exports:
            c = pkg.class_name(e)
            classes[c] = classes.get(c, 0) + 1
        for cls, n in sorted(classes.items(), key=lambda kv: -kv[1])[:15]:
            linhas.append(f"  {n:5d}  {cls}")
        for e in waves[:10]:
            slot = upk.find_ogg(pkg, e)
            linhas.append(f"  {pkg.full_name(e)}  serial={e.serial_size}  ogg={slot.size if slot else '-'}")
        return "\n".join(linhas)

    def count_voices(self, pacote) -> int:
        return len(upk.load(pacote).sound_waves())

    def extract(self, pacote, out_dir) -> list[tuple[str, Path, int]]:
        pkg = upk.load(pacote)
        return [(pkg.full_name(exp), path, size)
                for exp, path, size in upk.extract_all(pkg, out_dir)]

    def inject(self, pacote, replacements, dest) -> None:
        pkg = upk.load(pacote)
        data = upk.inject_same_size(pkg, replacements)
        upk.write_uncompressed(pkg, data, dest)


PLUGIN = UpkPlugin()
