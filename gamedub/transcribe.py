"""
Transcrição em lote com faster-whisper.

- O modelo fica em models/whisper/ dentro do projeto (uso offline depois
  do primeiro download; `python cli.py models` baixa antes).
- Retoma de onde parou: falas com texto já preenchido são puladas, e o
  falas.csv é salvo a cada lote, então dá pra interromper com Ctrl+C.
- GPU (cuda) se houver; cai para CPU com int8 automaticamente.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import catalog

MODELS_DIR = Path(__file__).resolve().parent.parent / "models" / "whisper"
NOMES = {"turbo": "deepdml/faster-whisper-large-v3-turbo-ct2"}   # apelido → repositório HF


def _repo(model_size: str) -> str:
    return NOMES.get(model_size, model_size)


def download(model_size: str = "medium") -> Path:
    from faster_whisper.utils import download_model
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return Path(download_model(_repo(model_size), output_dir=None, cache_dir=str(MODELS_DIR)))


def _load_model(model_size: str, device: str):
    from faster_whisper import WhisperModel
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:  # noqa: BLE001
            device = "cpu"
    compute = "float16" if device == "cuda" else "int8"
    print(f"modelo {model_size} em {device} ({compute})")
    return WhisperModel(_repo(model_size), device=device, compute_type=compute,
                        download_root=str(MODELS_DIR))


def decode_audio(path: str, sr: int = 16000):
    """Decodifica qualquer formato via ffmpeg para float32 mono 16 kHz.
    Evita depender do PyAV, cuja versão costuma brigar com o faster-whisper."""
    import subprocess
    import numpy as np
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path,
         "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def transcribe_file(model, path: str, language: str) -> str:
    audio = decode_audio(path)
    if len(audio) < 1600:                       # < 0,1 s: não há fala
        return ""
    segments, _info = model.transcribe(audio, language=language, beam_size=5,
                                       vad_filter=False, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments).strip()


def run(work: str | Path, model_size: str = "medium", device: str = "auto",
        only_missing: bool = True, language: str = "en", save_every: int = 25):
    falas = catalog.load(work)
    fila = [f for f in falas if not (only_missing and f.texto_en)]
    if not fila:
        print("nada a transcrever (todas as falas já têm texto; use --refazer para repetir)")
        return
    model = _load_model(model_size, device)
    print(f"{len(fila)} falas para transcrever ({len(falas) - len(fila)} já prontas)")

    t0 = time.time()
    feitas = 0
    try:
        for fala in fila:
            if not fala.arquivo or not Path(fala.arquivo).exists():
                fala.status = "erro:arquivo ausente"
                continue
            try:
                fala.texto_en = transcribe_file(model, fala.arquivo, language)
                fala.status = "transcrito" if fala.texto_en else "erro:sem fala"
            except Exception as e:  # noqa: BLE001
                fala.status = f"erro:transcricao {str(e)[:60]}"
            feitas += 1
            if feitas % save_every == 0:
                catalog.save(work, falas)
                media = (time.time() - t0) / feitas
                restante = media * (len(fila) - feitas)
                print(f"  {feitas}/{len(fila)}  ~{restante/60:.0f} min restantes")
    except KeyboardInterrupt:
        print("\ninterrompido; progresso salvo — rode de novo para continuar")
    finally:
        catalog.save(work, falas)

    ok = sum(1 for f in falas if f.texto_en)
    print(f"transcritas: {ok}/{len(falas)} em {(time.time()-t0)/60:.1f} min")
