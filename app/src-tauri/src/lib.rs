//! GameDub — backend Tauri.
//!
//! Responsabilidades do Rust:
//!   - abrir uma pasta `work/` e ler/gravar o `falas.csv`
//!   - rodar o `cli.py` (Python) como processo filho e repassar o progresso
//!     para a tela por eventos
//! O pipeline de IA continua em Python; aqui só orquestração e edição.

use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use tauri::{AppHandle, Emitter};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Fala {
    pub pacote: String,
    pub id: String,
    pub personagem: String,
    pub arquivo: String,
    pub duracao_s: f64,
    pub tamanho: u64,
    pub texto_en: String,
    pub texto_pt: String,
    pub audio_pt: String,
    pub status: String,
}

#[derive(Debug, Serialize)]
pub struct Projeto {
    pub work: String,
    pub fonte: serde_json::Value,
    pub falas: Vec<Fala>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Progresso {
    pub etapa: String,
    pub linha: String,
    pub terminou: bool,
    pub ok: bool,
}

fn csv_path(work: &str) -> PathBuf {
    Path::new(work).join("falas.csv")
}

fn ler_falas(work: &str) -> Result<Vec<Fala>, String> {
    let path = csv_path(work);
    let mut rdr = csv::ReaderBuilder::new()
        .flexible(true)
        .from_path(&path)
        .map_err(|e| format!("não abri {}: {e}", path.display()))?;
    let mut falas = Vec::new();
    for rec in rdr.deserialize::<Fala>() {
        falas.push(rec.map_err(|e| format!("linha inválida em falas.csv: {e}"))?);
    }
    Ok(falas)
}

fn gravar_falas(work: &str, falas: &[Fala]) -> Result<(), String> {
    let path = csv_path(work);
    let tmp = path.with_extension("csv.tmp");
    {
        let mut w = csv::Writer::from_path(&tmp).map_err(|e| e.to_string())?;
        for f in falas {
            w.serialize(f).map_err(|e| e.to_string())?;
        }
        w.flush().map_err(|e| e.to_string())?;
    }
    std::fs::rename(&tmp, &path).map_err(|e| e.to_string())
}

/// Raiz do projeto Python (onde está o cli.py): app/../ em desenvolvimento,
/// ou a pasta do executável quando empacotado junto.
fn raiz_python() -> PathBuf {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()));
    let candidatos: Vec<PathBuf> = [
        Some(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")),
        exe_dir.clone(),
        exe_dir.and_then(|d| d.parent().map(|p| p.to_path_buf())),
    ]
    .into_iter()
    .flatten()
    .collect();
    for c in &candidatos {
        if c.join("cli.py").exists() {
            return c.clone();
        }
    }
    candidatos[0].clone()
}

fn python_exe(raiz: &Path) -> PathBuf {
    for rel in [".venv/Scripts/python.exe", ".venv/bin/python"] {
        let p = raiz.join(rel);
        if p.exists() {
            return p;
        }
    }
    PathBuf::from("python")
}

// ---------------------------------------------------------------- comandos

#[tauri::command]
fn abrir_projeto(work: String) -> Result<Projeto, String> {
    let fonte_path = Path::new(&work).join("fonte.json");
    let fonte = std::fs::read_to_string(&fonte_path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or(serde_json::Value::Null);
    let falas = if csv_path(&work).exists() {
        ler_falas(&work)?
    } else {
        Vec::new()
    };
    Ok(Projeto { work, fonte, falas })
}

#[tauri::command]
fn salvar_fala(
    work: String,
    id: String,
    texto_pt: String,
    personagem: String,
) -> Result<(), String> {
    let mut falas = ler_falas(&work)?;
    let f = falas
        .iter_mut()
        .find(|f| f.id == id)
        .ok_or_else(|| format!("fala {id} não encontrada"))?;
    f.texto_pt = texto_pt;
    f.personagem = personagem;
    if f.status == "transcrito" && !f.texto_pt.is_empty() {
        f.status = "traduzido".into();
    }
    gravar_falas(&work, &falas)
}

#[tauri::command]
fn limpar_audio_pt(work: String, id: String) -> Result<(), String> {
    // marca a fala para ser sintetizada de novo no próximo `synth`
    let mut falas = ler_falas(&work)?;
    if let Some(f) = falas.iter_mut().find(|f| f.id == id) {
        f.audio_pt.clear();
        f.status = "traduzido".into();
    }
    gravar_falas(&work, &falas)
}

#[tauri::command]
fn listar_perfis() -> Result<Vec<String>, String> {
    let dir = raiz_python().join("profiles");
    let mut nomes = Vec::new();
    for e in std::fs::read_dir(&dir).map_err(|e| format!("{}: {e}", dir.display()))? {
        let p = e.map_err(|e| e.to_string())?.path();
        if p.extension().map(|x| x == "json").unwrap_or(false) {
            if let Some(stem) = p.file_stem() {
                nomes.push(stem.to_string_lossy().to_string());
            }
        }
    }
    nomes.sort();
    Ok(nomes)
}

/// Roda `python cli.py <args>` e emite cada linha de saída como evento
/// "progresso". Bloqueia a thread do comando até o processo terminar;
/// como o Tauri roda comandos `async` fora da thread principal, a tela
/// continua responsiva.
#[tauri::command]
async fn rodar_etapa(app: AppHandle, etapa: String, args: Vec<String>) -> Result<bool, String> {
    let raiz = raiz_python();
    let py = python_exe(&raiz);
    let mut cmd = Command::new(&py);
    cmd.arg("cli.py")
        .arg(&etapa)
        .args(&args)
        .current_dir(&raiz)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("não consegui rodar {}: {e}", py.display()))?;

    let stdout = child.stdout.take().unwrap();
    let stderr = child.stderr.take().unwrap();
    let app2 = app.clone();
    let etapa2 = etapa.clone();
    let t_err = std::thread::spawn(move || {
        for linha in BufReader::new(stderr).lines().map_while(Result::ok) {
            let _ = app2.emit(
                "progresso",
                Progresso {
                    etapa: etapa2.clone(),
                    linha,
                    terminou: false,
                    ok: true,
                },
            );
        }
    });
    for linha in BufReader::new(stdout).lines().map_while(Result::ok) {
        let _ = app.emit(
            "progresso",
            Progresso {
                etapa: etapa.clone(),
                linha,
                terminou: false,
                ok: true,
            },
        );
    }
    let _ = t_err.join();
    let status = child.wait().map_err(|e| e.to_string())?;
    let ok = status.success();
    let _ = app.emit(
        "progresso",
        Progresso {
            etapa: etapa.clone(),
            linha: format!("[{etapa}] {}", if ok { "concluído" } else { "falhou" }),
            terminou: true,
            ok,
        },
    );
    Ok(ok)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            abrir_projeto,
            salvar_fala,
            limpar_audio_pt,
            listar_perfis,
            rodar_etapa
        ])
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o GameDub");
}
