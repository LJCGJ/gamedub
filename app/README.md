# GameDub — interface (Tauri)

Editor de revisão: abre a pasta `work/` de um projeto, lista as falas por
pacote e personagem, toca o áudio original e o dublado, deixa editar a
tradução e dispara as etapas do pipeline Python com o progresso ao vivo.

## Pré-requisitos (Windows)

- Rust (`rustup`) e o Tauri CLI: `cargo install tauri-cli --version "^2"`
- WebView2 (já vem no Windows 10/11)
- O pipeline Python configurado na raiz do repositório (`.venv` criado)

## Rodar em desenvolvimento

```
cd app\src-tauri
cargo tauri dev
```

A primeira compilação demora alguns minutos (baixa e compila o Tauri);
as seguintes são rápidas.

## Gerar o instalador

```
cargo tauri build
```

Sai em `app\src-tauri\target\release\bundle\nsis\`. O executável procura
o `cli.py` na raiz do repositório (ou ao lado dele, quando distribuído
junto com a pasta Python).

## Estrutura

- `src-tauri/src/lib.rs` — comandos: `abrir_projeto`, `salvar_fala`,
  `limpar_audio_pt`, `listar_perfis`, `rodar_etapa` (roda `python cli.py`
  e emite o evento `progresso` linha a linha)
- `src/` — tela em HTML/CSS/JS puro, sem build step
