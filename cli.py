#!/usr/bin/env python3
"""GameDub — linha de comando."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gamedub import catalog
from gamedub.formats import upk


def cmd_info(a):
    pkg = upk.load(a.pacote)
    waves = pkg.sound_waves()
    print(f"versão {pkg.version}/{pkg.licensee}  comprimido={pkg.compressed}")
    print(f"nomes={len(pkg.names)} imports={len(pkg.imports)} exports={len(pkg.exports)}")
    print(f"SoundNodeWave: {len(waves)}")
    classes = {}
    for e in pkg.exports:
        classes[pkg.class_name(e)] = classes.get(pkg.class_name(e), 0) + 1
    for cls, n in sorted(classes.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {n:5d}  {cls}")
    for e in waves[:10]:
        slot = upk.find_ogg(pkg, e)
        print(f"  {pkg.full_name(e)}  size={e.serial_size}  ogg={slot.size if slot else '-'}")


def cmd_extract(a):
    pkg = upk.load(a.pacote)
    work = Path(a.work)
    res = upk.extract_all(pkg, work / "orig")
    falas = []
    for exp, path, size in res:
        fid = pkg.full_name(exp)
        falas.append(catalog.Fala(id=fid, personagem=catalog.guess_character(fid),
                                  arquivo=str(path), tamanho=size,
                                  duracao_s=catalog.duration_seconds(path)))
    catalog.save(work, falas)
    (work / "fonte.json").write_text(json.dumps({"pacote": str(Path(a.pacote).resolve())}),
                                     encoding="utf-8")
    print(f"{len(falas)} falas extraídas de {len(pkg.sound_waves())} SoundNodeWave → {work/'falas.csv'}")


def cmd_transcribe(a):
    from gamedub import transcribe
    transcribe.run(a.work, model_size=a.modelo, device=a.device)


def cmd_translate(a):
    from gamedub import translate
    translate.run(a.work, backend=a.backend, model=a.modelo, glossario_path=a.glossario)


def cmd_synth(a):
    from gamedub import synth
    synth.run(a.work, device=a.device)


def cmd_inject(a):
    work = Path(a.work)
    fonte = json.loads((work / "fonte.json").read_text(encoding="utf-8"))["pacote"]
    pkg = upk.load(fonte)
    falas = catalog.load(work)
    rep = {f.id: Path(f.audio_pt).read_bytes() for f in falas if f.audio_pt}
    if a.apenas:
        rep = {k: v for k, v in rep.items() if a.apenas in k}
    data = upk.inject_same_size(pkg, rep)
    upk.write_uncompressed(pkg, data, a.out)
    print(f"{len(rep)} falas injetadas → {a.out}")


def main():
    p = argparse.ArgumentParser(prog="gamedub")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("info", help="inspeciona um .upk"); s.add_argument("pacote"); s.set_defaults(fn=cmd_info)

    s = sub.add_parser("extract"); s.add_argument("pacote"); s.add_argument("work"); s.set_defaults(fn=cmd_extract)

    s = sub.add_parser("transcribe"); s.add_argument("work")
    s.add_argument("--modelo", default="medium"); s.add_argument("--device", default="auto")
    s.set_defaults(fn=cmd_transcribe)

    s = sub.add_parser("translate"); s.add_argument("work")
    s.add_argument("--backend", choices=["anthropic", "ollama"], default="anthropic")
    s.add_argument("--modelo"); s.add_argument("--glossario")
    s.set_defaults(fn=cmd_translate)

    s = sub.add_parser("synth"); s.add_argument("work"); s.add_argument("--device", default="cuda")
    s.set_defaults(fn=cmd_synth)

    s = sub.add_parser("inject"); s.add_argument("work"); s.add_argument("--out", required=True)
    s.add_argument("--apenas", help="injeta só falas cujo id contém este texto (ex.: Claptrap)")
    s.set_defaults(fn=cmd_inject)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
