#!/usr/bin/env python3
"""GameDub — linha de comando.

O perfil do jogo (profiles/<jogo>.json) é escolhido no `extract` e fica
gravado em work/fonte.json; as demais etapas o leem de lá.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gamedub import catalog, profile as profiles
from gamedub.formats import registry


def _fonte(work: Path) -> dict:
    return json.loads((work / "fonte.json").read_text(encoding="utf-8"))


def _profile_for(work: Path) -> profiles.Profile:
    return profiles.load(_fonte(work).get("perfil"))


def cmd_profiles(_a):
    for p in profiles.available():
        print(" ", p)


def cmd_info(a):
    fmt = registry.get(a.formato or registry.guess(a.pacote))
    print(fmt.describe(a.pacote))


def cmd_extract(a):
    prof = profiles.load(a.perfil)
    fmt = registry.get(a.formato or prof.formato or registry.guess(a.pacote))
    work = Path(a.work)
    entries = fmt.extract(a.pacote, work / "orig")
    falas = []
    for fid, path, size in entries:
        personagem = prof.character_for(fid) or catalog.guess_character(fid)
        falas.append(catalog.Fala(id=fid, personagem=personagem, arquivo=str(path),
                                  tamanho=size, duracao_s=catalog.duration_seconds(path)))
    catalog.save(work, falas)
    (work / "fonte.json").write_text(json.dumps({
        "pacote": str(Path(a.pacote).resolve()),
        "formato": fmt.name,
        "perfil": a.perfil,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(falas)} falas extraídas → {work/'falas.csv'}")


def cmd_transcribe(a):
    from gamedub import transcribe
    prof = _profile_for(Path(a.work))
    transcribe.run(a.work, model_size=a.modelo, device=a.device, language=prof.idioma_origem)


def cmd_translate(a):
    from gamedub import translate
    prof = _profile_for(Path(a.work))
    translate.run(a.work, prof, backend=a.backend, model=a.modelo, glossario_extra=a.glossario)


def cmd_synth(a):
    from gamedub import synth
    synth.run(a.work, device=a.device)


def cmd_inject(a):
    work = Path(a.work)
    fonte = _fonte(work)
    fmt = registry.get(fonte["formato"])
    falas = catalog.load(work)
    rep = {f.id: Path(f.audio_pt).read_bytes() for f in falas if f.audio_pt}
    if a.apenas:
        rep = {k: v for k, v in rep.items() if a.apenas in k}
    fmt.inject(fonte["pacote"], rep, a.out)
    print(f"{len(rep)} falas injetadas → {a.out}")


def main():
    p = argparse.ArgumentParser(prog="gamedub")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("profiles", help="lista perfis de jogo"); s.set_defaults(fn=cmd_profiles)

    s = sub.add_parser("info", help="inspeciona um pacote"); s.add_argument("pacote")
    s.add_argument("--formato", choices=registry.names()); s.set_defaults(fn=cmd_info)

    s = sub.add_parser("extract"); s.add_argument("pacote"); s.add_argument("work")
    s.add_argument("--perfil", help="nome em profiles/ (ex.: borderlands1)")
    s.add_argument("--formato", choices=registry.names())
    s.set_defaults(fn=cmd_extract)

    s = sub.add_parser("transcribe"); s.add_argument("work")
    s.add_argument("--modelo", default="medium"); s.add_argument("--device", default="auto")
    s.set_defaults(fn=cmd_transcribe)

    s = sub.add_parser("translate"); s.add_argument("work")
    s.add_argument("--backend", choices=["anthropic", "ollama"], default="anthropic")
    s.add_argument("--modelo"); s.add_argument("--glossario", help="JSON extra que sobrescreve o do perfil")
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
