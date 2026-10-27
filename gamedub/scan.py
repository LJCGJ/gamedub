"""
Descoberta de áudio na pasta do jogo.

Varre a pasta instalada, reconhece pacotes pelos plugins de formato e
conta as falas de cada um. O perfil do jogo pode restringir a busca
(`caminhos` e `filtro_arquivo`) para não abrir milhares de pacotes de
textura/mapa que não têm voz.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .formats import registry
from .profile import Profile


@dataclass
class Found:
    path: Path
    formato: str
    falas: int
    erro: str = ""


def discover(game_dir: str | Path, profile: Profile, formato: str | None = None,
             progress=print) -> list[Found]:
    game_dir = Path(game_dir)
    if not game_dir.is_dir():
        raise SystemExit(f"pasta não encontrada: {game_dir}")

    plugins = {registry.get(formato)} if formato else {registry.get(n) for n in registry.names()}
    if profile.formato and not formato:
        plugins = {registry.get(profile.formato)}
    ext_map = {ext: p for p in plugins for ext in p.extensions}

    raizes = [game_dir / c for c in profile.caminhos] if profile.caminhos else [game_dir]
    raizes = [r for r in raizes if r.exists()] or [game_dir]
    filtro = re.compile(profile.filtro_arquivo, re.IGNORECASE) if profile.filtro_arquivo else None

    candidatos = []
    for raiz in raizes:
        for p in sorted(raiz.rglob("*")):
            if p.is_file() and p.suffix.lower() in ext_map:
                if filtro and not filtro.search(p.name):
                    continue
                candidatos.append(p)

    progress(f"{len(candidatos)} pacotes candidatos em {len(raizes)} pasta(s)")
    found = []
    for i, p in enumerate(candidatos, 1):
        plugin = ext_map[p.suffix.lower()]
        try:
            n = plugin.count_voices(p)
            found.append(Found(p, plugin.name, n))
        except Exception as e:  # noqa: BLE001
            found.append(Found(p, plugin.name, 0, erro=str(e)[:80]))
        if i % 20 == 0:
            progress(f"  {i}/{len(candidatos)}")
    return found


def report(found: list[Found], game_dir: Path) -> str:
    com_voz = [f for f in found if f.falas > 0]
    erros = [f for f in found if f.erro]
    linhas = [f"{len(com_voz)} pacotes com voz, {sum(f.falas for f in com_voz)} falas no total"]
    for f in sorted(com_voz, key=lambda x: -x.falas):
        linhas.append(f"  {f.falas:6d}  {f.path.relative_to(game_dir)}")
    if erros:
        linhas.append(f"{len(erros)} pacotes não puderam ser lidos (primeiros 5):")
        for f in erros[:5]:
            linhas.append(f"  {f.path.relative_to(game_dir)}: {f.erro}")
    return "\n".join(linhas)
