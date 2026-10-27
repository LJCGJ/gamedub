"""
Registro de plugins de formato. Cada plugin implementa:

    name: str
    extensions: tuple[str, ...]
    describe(pacote) -> str
    extract(pacote, out_dir) -> list[(id, caminho_audio, tamanho_max)]
    inject(pacote, {id: bytes}, destino) -> None

Para adicionar um jogo/engine novo basta criar um módulo em formats/
com essa interface e registrá-lo em PLUGINS.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FormatPlugin(Protocol):
    name: str
    extensions: tuple[str, ...]

    def describe(self, pacote: str | Path) -> str: ...
    def extract(self, pacote: str | Path, out_dir: str | Path) -> list[tuple[str, Path, int]]: ...
    def inject(self, pacote: str | Path, replacements: dict[str, bytes], dest: str | Path) -> None: ...


def _plugins() -> dict[str, FormatPlugin]:
    from . import upk_plugin
    return {upk_plugin.PLUGIN.name: upk_plugin.PLUGIN}
    # próximos: wwise (.bnk/.wem), fmod (.fsb/.bank), ue4 (.pak), unity (.assets)


def names() -> list[str]:
    return sorted(_plugins())


def get(name: str) -> FormatPlugin:
    try:
        return _plugins()[name]
    except KeyError:
        raise SystemExit(f"formato desconhecido: {name!r} (disponíveis: {names()})")


def guess(pacote: str | Path) -> str:
    ext = Path(pacote).suffix.lower()
    for plugin in _plugins().values():
        if ext in plugin.extensions:
            return plugin.name
    raise SystemExit(f"não sei o formato de {Path(pacote).name}; use --formato")
