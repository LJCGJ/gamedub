"""
Síntese PT-BR com clonagem de voz (XTTS v2) e encaixe na duração original.

Para cada personagem, a referência de voz é o .ogg original mais longo
daquele personagem (ou um arquivo escolhido à mão em vozes/<personagem>.wav).
O resultado é reencodado em Ogg Vorbis com bitrate reduzido até caber no
tamanho do bloco original.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from . import catalog

BITRATES = ["96k", "80k", "64k", "48k", "40k", "32k", "24k"]


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _reference_for(personagem: str, falas: list[catalog.Fala], vozes_dir: Path) -> Path:
    manual = vozes_dir / f"{personagem}.wav"
    if manual.exists():
        return manual
    candidatas = [f for f in falas if f.personagem == personagem and f.arquivo]
    if not candidatas:
        raise RuntimeError(f"sem referência de voz para {personagem}")
    melhor = max(candidatas, key=lambda f: f.duracao_s)
    vozes_dir.mkdir(parents=True, exist_ok=True)
    wav = vozes_dir / f"{personagem}_auto.wav"
    if not wav.exists():
        _ffmpeg("-i", melhor.arquivo, "-ac", "1", "-ar", "22050", str(wav))
    return wav


def _fit(wav_in: Path, alvo_s: float, limite_bytes: int, dest_ogg: Path) -> bool:
    """Ajusta tempo (atempo) e bitrate até caber em duração e tamanho."""
    dur = catalog.duration_seconds(wav_in)
    ratio = dur / alvo_s if alvo_s > 0 else 1.0
    filtro = []
    if ratio > 1.02:                       # mais longa que a original → acelera
        ratio = min(ratio, 1.6)            # acima disso fica ininteligível; melhor encurtar o texto
        # atempo aceita 0.5–2.0 por estágio
        filtro = ["-filter:a", f"atempo={ratio:.3f}"]
    for br in BITRATES:
        _ffmpeg("-i", str(wav_in), *filtro, "-c:a", "libvorbis", "-b:a", br,
                "-ar", "22050", "-ac", "1", str(dest_ogg))
        if dest_ogg.stat().st_size <= limite_bytes:
            return True
    return False


def run(work: str | Path, only_missing: bool = True, device: str = "cuda"):
    from TTS.api import TTS  # Coqui

    work = Path(work)
    out_dir = work / "pt"
    out_dir.mkdir(exist_ok=True)
    vozes_dir = work / "vozes"

    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    falas = catalog.load(work)

    for i, fala in enumerate(falas, 1):
        if not fala.texto_pt or (only_missing and fala.audio_pt):
            continue
        try:
            ref = _reference_for(fala.personagem, falas, vozes_dir)
            with tempfile.TemporaryDirectory() as td:
                wav = Path(td) / "fala.wav"
                tts.tts_to_file(text=fala.texto_pt, speaker_wav=str(ref),
                                language="pt", file_path=str(wav))
                dest = out_dir / (Path(fala.arquivo).stem + ".ogg")
                ok = _fit(wav, fala.duracao_s, fala.tamanho, dest)
            if ok:
                fala.audio_pt = str(dest)
                fala.status = "sintetizado"
            else:
                fala.status = "erro:nao coube no tamanho original"
        except Exception as e:  # noqa: BLE001
            fala.status = f"erro:synth {e}"
        if i % 10 == 0:
            catalog.save(work, falas)
            print(f"  {i}/{len(falas)}")
    catalog.save(work, falas)
    print("sintetizadas:", sum(1 for f in falas if f.audio_pt))
