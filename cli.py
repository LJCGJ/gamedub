#!/usr/bin/env python3
"""GameDub — linha de comando.

Fluxo normal: apontar para a PASTA DO JOGO. O `scan` descobre os pacotes
com voz; o `extract` extrai todos eles; `transcribe`/`translate`/`synth`
trabalham no falas.csv; o `inject` gera os pacotes traduzidos em uma
pasta espelho, pronta para copiar por cima do jogo (guarde backup).

O perfil do jogo (profiles/<jogo>.json) é escolhido no `extract` e fica
gravado em work/fonte.json; as demais etapas o leem de lá.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gamedub import catalog, profile as profiles, scan
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


def cmd_scan(a):
    prof = profiles.load(a.perfil)
    found = scan.discover(a.jogo, prof, a.formato)
    print(scan.report(found, Path(a.jogo)))


def cmd_extract(a):
    prof = profiles.load(a.perfil)
    alvo = Path(a.jogo)
    work = Path(a.work)

    if alvo.is_file():                      # um pacote só
        game_dir = alvo.parent
        pacotes = [(alvo, registry.get(a.formato or prof.formato or registry.guess(alvo)))]
    else:                                   # pasta do jogo
        game_dir = alvo
        found = [f for f in scan.discover(alvo, prof, a.formato) if f.falas > 0]
        if a.limite:
            found = sorted(found, key=lambda f: -f.falas)[:a.limite]
        pacotes = [(f.path, registry.get(f.formato)) for f in found]
        if not pacotes:
            raise SystemExit("nenhum pacote com voz encontrado — confira o perfil (caminhos/filtro_arquivo)")

    falas = []
    for pacote, fmt in pacotes:
        rel = pacote.relative_to(game_dir).as_posix()
        out = work / "orig" / Path(rel).with_suffix("")
        entries = fmt.extract(pacote, out)
        for fid, path, size in entries:
            personagem = prof.character_for(fid) or catalog.guess_character(fid)
            falas.append(catalog.Fala(id=fid, pacote=rel, personagem=personagem,
                                      arquivo=str(path), tamanho=size,
                                      duracao_s=catalog.duration_seconds(path)))
        print(f"  {len(entries):5d} falas  {rel}")

    catalog.save(work, falas)
    (work / "fonte.json").write_text(json.dumps({
        "jogo_dir": str(game_dir.resolve()),
        "perfil": a.perfil,
        "pacotes": {pacote.relative_to(game_dir).as_posix(): fmt.name for pacote, fmt in pacotes},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(falas)} falas de {len(pacotes)} pacote(s) → {work/'falas.csv'}")


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
    game_dir = Path(fonte["jogo_dir"])
    out_dir = Path(a.out)
    falas = [f for f in catalog.load(work) if f.audio_pt]
    if a.apenas:
        falas = [f for f in falas if a.apenas in f.id]

    por_pacote: dict[str, dict[str, bytes]] = {}
    for f in falas:
        por_pacote.setdefault(f.pacote, {})[f.id] = Path(f.audio_pt).read_bytes()

    total = 0
    for rel, rep in por_pacote.items():
        fmt = registry.get(fonte["pacotes"][rel])
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        fmt.inject(game_dir / rel, rep, dest)
        total += len(rep)
        print(f"  {len(rep):5d} falas  {rel}")
    print(f"{total} falas injetadas em {len(por_pacote)} pacote(s) → {out_dir}")
    print("Copie o conteúdo dessa pasta por cima da pasta do jogo (faça backup dos originais).")


def main():
    p = argparse.ArgumentParser(prog="gamedub")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("profiles", help="lista perfis de jogo"); s.set_defaults(fn=cmd_profiles)

    s = sub.add_parser("info", help="inspeciona um pacote"); s.add_argument("pacote")
    s.add_argument("--formato", choices=registry.names()); s.set_defaults(fn=cmd_info)

    s = sub.add_parser("scan", help="descobre os pacotes com voz na pasta do jogo")
    s.add_argument("jogo", help="pasta do jogo instalado")
    s.add_argument("--perfil"); s.add_argument("--formato", choices=registry.names())
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("extract", help="extrai as falas da pasta do jogo (ou de um pacote)")
    s.add_argument("jogo", help="pasta do jogo instalado, ou um pacote específico")
    s.add_argument("work")
    s.add_argument("--perfil", help="nome em profiles/ (ex.: borderlands1)")
    s.add_argument("--formato", choices=registry.names())
    s.add_argument("--limite", type=int, help="só os N pacotes com mais falas (útil para testar)")
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

    s = sub.add_parser("inject", help="gera os pacotes traduzidos em uma pasta espelho")
    s.add_argument("work"); s.add_argument("--out", required=True, help="pasta de saída (espelha a do jogo)")
    s.add_argument("--apenas", help="injeta só falas cujo id contém este texto (ex.: Claptrap)")
    s.set_defaults(fn=cmd_inject)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
