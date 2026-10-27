"""Transcrição em lote com faster-whisper."""
from __future__ import annotations

from pathlib import Path

from . import catalog


def run(work: str | Path, model_size: str = "medium", device: str = "auto",
        only_missing: bool = True):
    from faster_whisper import WhisperModel

    compute = "float16" if device != "cpu" else "int8"
    model = WhisperModel(model_size, device=device, compute_type=compute)

    falas = catalog.load(work)
    for i, fala in enumerate(falas, 1):
        if only_missing and fala.texto_en:
            continue
        if not fala.arquivo or not Path(fala.arquivo).exists():
            fala.status = "erro:arquivo ausente"
            continue
        segments, _ = model.transcribe(fala.arquivo, language="en",
                                       beam_size=5, vad_filter=False)
        fala.texto_en = " ".join(s.text.strip() for s in segments).strip()
        fala.status = "transcrito" if fala.texto_en else "erro:sem fala"
        if i % 25 == 0:
            catalog.save(work, falas)
            print(f"  {i}/{len(falas)}")
    catalog.save(work, falas)
    print(f"transcritas: {sum(1 for f in falas if f.texto_en)}/{len(falas)}")
