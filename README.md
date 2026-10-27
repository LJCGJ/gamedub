# GameDub — dublagem offline de jogos com IA

Pipeline para traduzir e dublar as falas de um jogo a partir dos arquivos
de áudio do próprio jogo, devolvendo-os no formato original.

Fluxo:

```
.upk ──extract──▶ .ogg + falas.csv ──transcribe──▶ texto_en
      ◀──inject──  .ogg (PT-BR)  ◀──synth────────  texto_pt ◀──translate──┘
```

O núcleo (transcrever → traduzir → sintetizar) não conhece nenhum jogo.
O que é específico fica em dois lugares:

- **`profiles/<jogo>.json`** — glossário, descrição do tom para o
  tradutor, regex de `id da fala → personagem`, formato do pacote.
  É o que a comunidade preenche para cada jogo novo, sem mexer em código.
- **`gamedub/formats/<engine>_plugin.py`** — como ler e reescrever o
  pacote daquela engine. Interface em `formats/registry.py`
  (`describe`, `extract`, `inject`).

Primeiro alvo: **Borderlands 1 (PC, Unreal Engine 3)** — perfil
`borderlands1`, plugin `upk`. Próximos plugins, por cobertura de jogos:
Wwise (`.bnk/.wem`: Borderlands 2/3 e a maioria dos AAA), FMOD
(`.fsb/.bank`), UE4/5 (`.pak`), Unity (`.assets`).

## Requisitos

- Python 3.10+
- ffmpeg no PATH
- GPU NVIDIA recomendada (Whisper e XTTS rodam em CPU, mas muito mais lento)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Uso (prova de conceito com um pacote)

```bash
# 0. inspeciona o pacote (formato detectado pela extensão, ou --formato)
python cli.py info "C:\...\Borderlands\WillowGame\CookedPC\Maps\Arid\Arid_P_INT.upk"

# 1. extrai as falas usando o perfil do jogo
python cli.py extract "C:\...\Arid_P_INT.upk" work\arid --perfil borderlands1

# 2. transcreve (faster-whisper)
python cli.py transcribe work\arid

# 3. traduz com glossário
python cli.py translate work\arid

# 4. sintetiza em PT-BR, encaixando na duração original
python cli.py synth work\arid

# 5. gera o pacote traduzido (não altera o original)
python cli.py inject work\arid --out "C:\...\Arid_P_BRA.upk"
```

Cada etapa lê e grava `work\arid\falas.csv`, então dá pra revisar a
tradução à mão entre `translate` e `synth`.

## Estado

| Etapa | Estado |
|---|---|
| Leitura do `.upk` (header, nomes, exports, descompressão LZO) | implementado, **não validado** com arquivo real |
| Extração de `SoundNodeWave` → `.ogg` | implementado (heurística `OggS` + bulk header), não validado |
| Transcrição (faster-whisper) | pronto |
| Tradução (Anthropic API ou Ollama local, com glossário) | pronto |
| Síntese (XTTS v2, ajuste de duração via ffmpeg) | pronto |
| Reinjeção (mesmo tamanho, padding) | implementado, experimental |

Primeira validação pendente: rodar `extract` em um `.upk` real do BL1.

## Decisões de reinjeção

O UE3 lê o Ogg inline no export. A PoC mantém o tamanho do bloco:
o Ogg novo é codificado com bitrate menor até caber e o restante é
preenchido com zeros. Se o jogo rejeitar o padding, o plano B é
reescrever o export com novo tamanho e recalcular os offsets dos
exports seguintes (`formats/upk.py` já expõe a tabela para isso).
