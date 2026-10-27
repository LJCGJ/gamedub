"""
Tradução EN → PT-BR com glossário fixo e contexto de personagem.

Backends:
  anthropic  — usa ANTHROPIC_API_KEY (melhor qualidade para humor/gíria)
  ollama     — servidor local (http://localhost:11434), gratuito
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import catalog

GLOSSARIO_PADRAO = {
    # mantidos em inglês (nomes próprios do universo)
    "Claptrap": "Claptrap", "Pandora": "Pandora", "Vault": "Vault",
    "Crimson Lance": "Crimson Lance", "Hyperion": "Hyperion",
    "Dahl": "Dahl", "Atlas": "Atlas", "Fyrestone": "Fyrestone",
    "Skag": "Skag", "Rakk": "Rakk", "Psycho": "Psycho",
    "Marcus": "Marcus", "Moxxi": "Moxxi", "Scooter": "Scooter",
    "Tannis": "Tannis", "Zed": "Zed", "Angel": "Angel",
    "Catch-A-Ride": "Catch-A-Ride", "Eridian": "Eridiano",
    "Bandit": "bandido", "Vault Hunter": "Caçador da Vault",
}

SYSTEM = """Você é tradutor de localização de jogos para português do Brasil.
Traduza falas do jogo Borderlands (FPS de humor ácido, violento e irreverente).
Regras:
- Mantenha o tom: gírias, xingamentos e piadas devem soar naturais em PT-BR.
- A fala será dublada e precisa caber no mesmo tempo da original: prefira
  frases curtas, nunca mais longas que o inglês.
- Use o glossário à risca. Não traduza nomes próprios que o glossário mantém.
- Responda SOMENTE com um JSON: {"id": "texto traduzido", ...}.
"""


def _prompt(lote: list[catalog.Fala], glossario: dict) -> str:
    itens = [{"id": f.id, "personagem": f.personagem, "en": f.texto_en} for f in lote]
    return ("Glossário: " + json.dumps(glossario, ensure_ascii=False) +
            "\n\nFalas:\n" + json.dumps(itens, ensure_ascii=False, indent=1))


def _anthropic(prompt: str, model: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=4096, system=SYSTEM,
                                 messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text


def _ollama(prompt: str, model: str) -> str:
    import requests
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": model, "stream": False, "format": "json",
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["message"]["content"]


def _parse(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1]
    return json.loads(text)


def run(work: str | Path, backend: str = "anthropic", model: str | None = None,
        batch: int = 20, glossario_path: str | None = None, only_missing=True):
    glossario = dict(GLOSSARIO_PADRAO)
    if glossario_path:
        glossario.update(json.loads(Path(glossario_path).read_text(encoding="utf-8")))

    model = model or ("claude-sonnet-5-5" if backend == "anthropic" else "qwen2.5:14b")
    call = _anthropic if backend == "anthropic" else _ollama

    falas = catalog.load(work)
    fila = [f for f in falas if f.texto_en and (not only_missing or not f.texto_pt)]
    por_id = {f.id: f for f in falas}

    for i in range(0, len(fila), batch):
        lote = fila[i:i + batch]
        try:
            resp = _parse(call(_prompt(lote, glossario), model))
        except Exception as e:  # noqa: BLE001
            for f in lote:
                f.status = f"erro:traducao {e}"
            continue
        for fid, pt in resp.items():
            if fid in por_id and isinstance(pt, str):
                por_id[fid].texto_pt = pt.strip()
                por_id[fid].status = "traduzido"
        catalog.save(work, falas)
        print(f"  {min(i + batch, len(fila))}/{len(fila)}")
    catalog.save(work, falas)
