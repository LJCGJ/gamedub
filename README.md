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

## Uso

Aponte para a **pasta do jogo instalado**; o software descobre os pacotes
de voz sozinho a partir do perfil.

```bash
# 1. descobre quais pacotes têm voz (não altera nada)
python cli.py scan "C:\Program Files (x86)\Steam\steamapps\common\Borderlands" --perfil borderlands1

# 2. extrai todas as falas (ou --limite 1 para testar só o maior pacote)
python cli.py extract "C:\...\Borderlands" work\bl1 --perfil borderlands1

# 3. transcreve (faster-whisper)
python cli.py transcribe work\bl1

# 4. traduz com o glossário do perfil
python cli.py translate work\bl1

# 5. sintetiza em PT-BR, encaixando na duração original
python cli.py synth work\bl1

# 6. gera os pacotes traduzidos numa pasta espelho (os originais não são tocados)
python cli.py inject work\bl1 --out saida\bl1
```

Depois é copiar o conteúdo de `saida\bl1` por cima da pasta do jogo,
guardando backup dos originais. Cada etapa lê e grava `work\bl1\falas.csv`,
então dá pra revisar a tradução à mão entre `translate` e `synth`.

`extract` e `info` também aceitam um único pacote em vez da pasta.

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
