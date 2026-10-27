"""
falas.csv — a tabela única que todas as etapas leem e gravam.

Colunas:
  pacote      caminho do pacote de origem, relativo à pasta do jogo
  id          nome completo do export (ex.: Arid_P.TheWorld.PersistentLevel.Claptrap_Intro_01)
  personagem  derivado do id; editável à mão
  arquivo     caminho do .ogg original extraído
  duracao_s   duração do áudio original
  tamanho     bytes do Ogg original (limite para reinjeção)
  texto_en    transcrição (Whisper)
  texto_pt    tradução (revisável)
  audio_pt    caminho do .ogg gerado em PT-BR
  status      extraido | transcrito | traduzido | sintetizado | erro:<msg>
"""
from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass, asdict, fields
from pathlib import Path

COLUNAS = ["pacote", "id", "personagem", "arquivo", "duracao_s", "tamanho",
           "texto_en", "texto_pt", "audio_pt", "status"]


@dataclass
class Fala:
    id: str
    pacote: str = ""
    personagem: str = ""
    arquivo: str = ""
    duracao_s: float = 0.0
    tamanho: int = 0
    texto_en: str = ""
    texto_pt: str = ""
    audio_pt: str = ""
    status: str = "extraido"


def csv_path(work: str | Path) -> Path:
    return Path(work) / "falas.csv"


def load(work) -> list[Fala]:
    p = csv_path(work)
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        r["duracao_s"] = float(r.get("duracao_s") or 0)
        r["tamanho"] = int(r.get("tamanho") or 0)
        out.append(Fala(**{k: r.get(k, "") for k in COLUNAS}))
    return out


def save(work, falas: list[Fala]):
    p = csv_path(work)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        for fl in falas:
            w.writerow(asdict(fl))


def guess_character(export_name: str) -> str:
    """
    Nos pacotes do BL1 o nome do objeto costuma carregar o personagem:
    'Claptrap_Greeting_03', 'Moxxi_Round_Start_01', 'Marcus_Bus_Intro'...
    Pegamos o primeiro token antes de número/underscore.
    """
    leaf = export_name.split(".")[-1]
    m = re.match(r"([A-Za-z]+)", leaf)
    return m.group(1) if m else "Desconhecido"


def duration_seconds(path: str | Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0
