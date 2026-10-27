"""
Perfil por jogo: tudo que é específico de um título fica em profiles/<jogo>.json
(glossário, descrição para o tradutor, mapeamento de personagens, formato).
O núcleo do pipeline não conhece nenhum jogo em particular.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


@dataclass
class Profile:
    nome: str
    formato: str
    idioma_origem: str = "en"
    descricao: str = ""
    glossario: dict[str, str] = field(default_factory=dict)
    personagens: dict[str, str] = field(default_factory=dict)

    def character_for(self, fala_id: str) -> str | None:
        leaf = fala_id.split(".")[-1]
        for padrao, nome in self.personagens.items():
            if padrao.startswith("_"):
                continue
            if re.search(padrao, leaf, re.IGNORECASE):
                return nome
        return None


def available() -> list[str]:
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def load(nome_ou_caminho: str | None) -> Profile:
    if not nome_ou_caminho:
        return Profile(nome="generico", formato="")
    p = Path(nome_ou_caminho)
    if not p.exists():
        p = PROFILES_DIR / f"{nome_ou_caminho}.json"
    if not p.exists():
        raise FileNotFoundError(f"perfil não encontrado: {nome_ou_caminho} (disponíveis: {available()})")
    data = json.loads(p.read_text(encoding="utf-8"))
    return Profile(
        nome=data.get("nome", p.stem),
        formato=data.get("formato", ""),
        idioma_origem=data.get("idioma_origem", "en"),
        descricao=data.get("descricao", ""),
        glossario=data.get("glossario", {}),
        personagens=data.get("personagens", {}),
    )
