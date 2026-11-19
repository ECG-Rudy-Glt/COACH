//! Coque de bureau COACH : une fenêtre qui lance le serveur COACH embarqué (sidecar Python figé avec PyInstaller)
//! sur 127.0.0.1, attend qu'il réponde, puis l'affiche.
//!
//! - Les pages locales de la coque (`src/`) servent d'assistant de premier lancement et d'écran Réglages (fournisseur d'IA).
//! - La clé du fournisseur d'IA vit dans le trousseau de l'OS (`keyring`), jamais dans un fichier ni dans les journaux ;
//!   elle n'est transmise au sidecar que par variable d'environnement, au lancement.
//! - Le serveur n'écoute que sur 127.0.0.1, sur un port libre choisi à chaque lancement. Il s'arrête avec la coque
//!   (arrêt explicite, et fermeture de son entrée standard si la coque meurt brutalement).
//! - Le contenu servi par le sidecar n'a accès à aucune API native ; ses liens externes s'ouvrent dans le navigateur.

use std::{
    fs,
    io::{Read, Write},
    net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use tauri::{
    menu::{AboutMetadataBuilder, MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder},
    AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder,
};
use tauri_plugin_dialog::{DialogExt, FilePath};
use tauri_plugin_opener::OpenerExt;

const WINDOW: &str = "main";
const KEYRING_SERVICE: &str = "COACH";
const DEFAULT_OLLAMA_URL: &str = "http://127.0.0.1:11434/v1";
const START_TIMEOUT: Duration = Duration::from_secs(120);
/// Fournisseurs proposés (identifiants du catalogue `data/llm_providers.yaml`) ; `bool` = clé obligatoire.
const PROVIDERS: &[(&str, bool)] = &[
    ("anthropic", true),
    ("openai", true),
    ("gemini", true),
    ("mistral", true),
    ("openrouter", true),
    ("ollama", false),
    ("none", false),
];
/// Seuls ces sites peuvent être ouverts depuis l'assistant (pages de création de clé et documentation).
const EXTERNAL_ALLOWED: &[&str] = &[
    "https://console.anthropic.com/",
    "https://platform.openai.com/",
    "https://aistudio.google.com/",
    "https://console.mistral.ai/",
    "https://openrouter.ai/",
    "https://ollama.com/",
    "https://github.com/ECG-Rudy-Glt/COACH",
];

#[derive(Serialize, Deserialize, Clone)]
struct Settings {
    provider: String,
    #[serde(default)]
    model: String,
    #[serde(default)]
    base_url: String,
    #[serde(default = "default_budget")]
    budget: f64,
}

fn default_budget() -> f64 {
    5.0
}

#[derive(Default)]
struct Shell {
    child: Mutex<Option<Child>>,
    port: Mutex<Option<u16>>,
}

fn data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn settings_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(data_dir(app)?.join("settings.json"))
}

fn load_settings(app: &AppHandle) -> Option<Settings> {
    let text = fs::read_to_string(settings_path(app).ok()?).ok()?;
    serde_json::from_str(&text).ok()
}

fn provider_needs_key(id: &str) -> Option<bool> {
    PROVIDERS.iter().find(|(p, _)| *p == id).map(|(_, k)| *k)
}

fn key_entry(provider: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYRING_SERVICE, &format!("llm-api-key:{provider}")).map_err(|e| e.to_string())
}

fn stored_key(provider: &str) -> Option<String> {
    key_entry(provider).ok()?.get_password().ok().filter(|k| !k.is_empty())
}

/// Clé de chiffrement des jetons Garmin (Fernet : 32 octets en base64 « url-safe » avec remplissage), créée au besoin.
fn garmin_secret() -> Option<String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, "garmin-secrets-key").ok()?;
    if let Ok(k) = entry.get_password() {
        if !k.is_empty() {
            return Some(k);
        }
    }
    let mut raw = [0u8; 32];
    getrandom::getrandom(&mut raw).ok()?;
    let key = base64_url(&raw);
    entry.set_password(&key).ok()?;
    Some(key)
}

fn base64_url(data: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut out = String::new();
    for chunk in data.chunks(3) {
        let n = (chunk[0] as u32) << 16 | (*chunk.get(1).unwrap_or(&0) as u32) << 8 | *chunk.get(2).unwrap_or(&0) as u32;
        for i in 0..4 {
            if i <= chunk.len() {
                out.push(ALPHABET[(n >> (18 - 6 * i) & 63) as usize] as char);
            } else {
                out.push('=');
            }
        }
    }
    out
}

fn sidecar_path() -> Result<PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let name = if cfg!(windows) { "coach-sidecar.exe" } else { "coach-sidecar" };
    Ok(exe.parent().ok_or("dossier de l'application introuvable")?.join(name))
}

fn quiet(cmd: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW : pas de console qui clignote
    }
    cmd
}

fn free_port() -> Result<u16, String> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).map_err(|e| e.to_string())?;
    Ok(listener.local_addr().map_err(|e| e.to_string())?.port())
}

/// GET /healthz sur 127.0.0.1 avec la seule bibliothèque standard.
fn healthy(port: u16) -> bool {
    let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(500)) else { return false };
    let _ = s.set_read_timeout(Some(Duration::from_secs(2)));
    let req = format!("GET /healthz HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
    if s.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut head = String::new();
    let _ = s.take(64).read_to_string(&mut head);
    head.starts_with("HTTP/1.0 200") || head.starts_with("HTTP/1.1 200")
}

fn stop_sidecar(app: &AppHandle) {
    let shell = app.state::<Shell>();
    *shell.port.lock().unwrap() = None;
    let taken = shell.child.lock().unwrap().take();
    if let Some(mut child) = taken {
        drop(child.stdin.take()); // le sidecar surveille ce tube : sa fermeture lui demande de s'arrêter
        std::thread::sleep(Duration::from_millis(300));
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Lance le sidecar avec les réglages enregistrés et attend /healthz. Retourne le port.
fn start_sidecar(app: &AppHandle) -> Result<u16, String> {
    stop_sidecar(app);
    let settings = load_settings(app).ok_or("Réglages absents : lancez l'assistant.")?;
    let dir = data_dir(app)?;
    let port = free_port()?;
    let log_dir = dir.join("logs");
    fs::create_dir_all(&log_dir).map_err(|e| e.to_string())?;
    let log = fs::File::create(log_dir.join("sidecar.log")).map_err(|e| e.to_string())?;
    let log2 = log.try_clone().map_err(|e| e.to_string())?;

    let mut cmd = Command::new(sidecar_path()?);
    cmd.args(["serve", "--port", &port.to_string(), "--data-dir"]).arg(&dir);
    // Ce que l'utilisateur a déjà dans son environnement ne doit pas se mélanger aux réglages de l'application.
    for var in [
        "LLM_API_KEY", "LLM_API_KEY_FILE", "LLM_PROVIDER", "LLM_MODEL", "LLM_MODEL_FAST", "LLM_BASE_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "GEMINI_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_API_KEY", "SECRETS_KEY", "SECRETS_KEY_FILE", "DB_HOST", "DATABASE_URL_FILE",
    ] {
        cmd.env_remove(var);
    }
    cmd.env("LLM_PROVIDER", &settings.provider)
        .env("LLM_MONTHLY_BUDGET_EUR", format!("{}", settings.budget));
    if provider_needs_key(&settings.provider).is_some() && settings.provider != "none" {
        if let Some(key) = stored_key(&settings.provider) {
            cmd.env("LLM_API_KEY", key);
        }
        if !settings.model.is_empty() {
            cmd.env("LLM_MODEL", &settings.model);
        }
        let base = if settings.base_url.is_empty() && settings.provider == "ollama" { DEFAULT_OLLAMA_URL } else { &settings.base_url };
        if !base.is_empty() {
            cmd.env("LLM_BASE_URL", base);
        }
    }
    if let Some(k) = garmin_secret() {
        cmd.env("SECRETS_KEY", k);
    }
    cmd.stdin(Stdio::piped()).stdout(Stdio::from(log)).stderr(Stdio::from(log2));
    quiet(&mut cmd);
    let mut child = cmd.spawn().map_err(|e| format!("Impossible de lancer le serveur embarqué : {e}"))?;

    let deadline = Instant::now() + START_TIMEOUT;
    loop {
        if healthy(port) {
            break;
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("Le serveur embarqué s'est arrêté au démarrage ({status}). Journal : {}", log_dir.join("sidecar.log").display()));
        }
        if Instant::now() > deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("Le serveur embarqué ne répond pas. Journal : {}", log_dir.join("sidecar.log").display()));
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    let shell = app.state::<Shell>();
    *shell.child.lock().unwrap() = Some(child);
    *shell.port.lock().unwrap() = Some(port);
    Ok(port)
}

fn local_url(query: &str) -> Url {
    let base = if cfg!(windows) { "http://tauri.localhost/index.html" } else { "tauri://localhost/index.html" };
    Url::parse(&format!("{base}{query}")).expect("URL locale valide")
}

fn is_local_page(url: &Url) -> bool {
    (url.scheme() == "tauri" && url.host_str() == Some("localhost")) || url.host_str() == Some("tauri.localhost")
}

#[derive(Serialize)]
struct State {
    configured: bool,
    settings: Option<Settings>,
    has_key: bool,
    running: bool,
    data_dir: String,
    version: String,
}

#[tauri::command]
fn get_state(app: AppHandle) -> State {
    let settings = load_settings(&app);
    let has_key = settings.as_ref().map_or(false, |s| stored_key(&s.provider).is_some());
    let running = app.state::<Shell>().port.lock().unwrap().is_some();
    State {
        configured: settings.is_some(),
        has_key,
        settings,
        running,
        data_dir: data_dir(&app).map(|d| d.display().to_string()).unwrap_or_default(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    }
}

/// Indique si une clé est déjà stockée pour ce fournisseur (jamais sa valeur).
#[tauri::command]
fn has_key(provider: String) -> bool {
    stored_key(&provider).is_some()
}

#[derive(Deserialize)]
struct SaveInput {
    provider: String,
    #[serde(default)]
    api_key: String,
    #[serde(default)]
    clear_key: bool,
    #[serde(default)]
    model: String,
    #[serde(default)]
    base_url: String,
    budget: f64,
}

fn clean_text(s: &str, max: usize) -> Result<String, String> {
    let t = s.trim();
    if t.chars().count() > max || t.chars().any(char::is_control) {
        return Err("Texte invalide.".into());
    }
    Ok(t.to_string())
}

/// Valide et enregistre les réglages ; la clé va dans le trousseau. Ne démarre rien : l'interface appelle ensuite `start_app`.
#[tauri::command]
fn save_settings(app: AppHandle, input: SaveInput) -> Result<(), String> {
    let needs_key = provider_needs_key(&input.provider).ok_or("Fournisseur inconnu.")?;
    if !(0.0..=10_000.0).contains(&input.budget) || !input.budget.is_finite() {
        return Err("Budget invalide.".into());
    }
    let model = clean_text(&input.model, 100)?;
    let base_url = clean_text(&input.base_url, 200)?;
    if !base_url.is_empty() {
        let u = Url::parse(&base_url).map_err(|_| "Adresse du serveur invalide.")?;
        if !matches!(u.scheme(), "http" | "https") || u.host_str().is_none() || !u.username().is_empty() || u.password().is_some() {
            return Err("Adresse du serveur invalide (http ou https, sans identifiants).".into());
        }
    }
    if input.clear_key {
        if let Ok(e) = key_entry(&input.provider) {
            let _ = e.delete_credential();
        }
    }
    let key = input.api_key.trim();
    if input.provider == "none" || !needs_key {
        // Rien à stocker : on ne touche pas à une éventuelle clé déjà enregistrée.
    } else if !key.is_empty() {
        if key.chars().any(|c| c.is_control() || c.is_whitespace()) || key.len() > 400 {
            return Err("La clé contient des caractères invalides (espace ou retour à la ligne collé par erreur ?).".into());
        }
        key_entry(&input.provider)?.set_password(key).map_err(|_| {
            "Le trousseau de l'ordinateur a refusé la clé. Sous Linux, un trousseau (GNOME Keyring, KWallet) doit être installé et déverrouillé.".to_string()
        })?;
    } else if stored_key(&input.provider).is_none() {
        return Err("Ce fournisseur demande une clé.".into());
    }
    let settings = Settings {
        provider: input.provider,
        model,
        base_url: if input.base_url.trim().is_empty() { String::new() } else { base_url },
        budget: input.budget,
    };
    let json = serde_json::to_string_pretty(&settings).map_err(|e| e.to_string())?;
    fs::write(settings_path(&app)?, json).map_err(|e| e.to_string())
}

/// Affiche COACH dans la fenêtre. `restart` relance le serveur embarqué (après un changement de réglages) ;
/// sinon un serveur déjà démarré est simplement réaffiché.
#[tauri::command]
async fn start_app(app: AppHandle, restart: Option<bool>) -> Result<(), String> {
    let running = *app.state::<Shell>().port.lock().unwrap();
    let port = match running {
        Some(p) if restart != Some(true) => p,
        _ => {
            let handle = app.clone();
            tauri::async_runtime::spawn_blocking(move || start_sidecar(&handle)).await.map_err(|e| e.to_string())??
        }
    };
    let win = app.get_webview_window(WINDOW).ok_or("fenêtre introuvable")?;
    let url = Url::parse(&format!("http://127.0.0.1:{port}/")).map_err(|e| e.to_string())?;
    win.navigate(url).map_err(|e| e.to_string())
}

#[tauri::command]
fn open_external(app: AppHandle, url: String) -> Result<(), String> {
    if !EXTERNAL_ALLOWED.iter().any(|p| url.starts_with(p)) {
        return Err("Adresse non autorisée.".into());
    }
    app.opener().open_url(url, None::<&str>).map_err(|e| e.to_string())
}

fn open_window(app: &AppHandle) -> tauri::Result<()> {
    let handle = app.clone();
    // Les liens target=_blank et window.open sont ramenés dans la fenêtre : le filtre de navigation décide ensuite
    // s'ils restent ici (le serveur embarqué) ou partent dans le navigateur.
    let init_script = r#"
      (function () {
        document.addEventListener('click', function (e) {
          var a = e.target && e.target.closest && e.target.closest('a[target="_blank"]');
          if (a && a.href) { e.preventDefault(); window.location.href = a.href; }
        }, true);
        window.open = function (u) { if (u) { window.location.href = String(u); } return null; };
      })();
    "#;
    WebviewWindowBuilder::new(app, WINDOW, WebviewUrl::App("index.html".into()))
        .title("COACH")
        .inner_size(1180.0, 820.0)
        .min_inner_size(380.0, 600.0)
        .initialization_script(init_script)
        .on_navigation(move |url| {
            if is_local_page(url) || matches!(url.scheme(), "about" | "blob" | "data") {
                return true;
            }
            let port = *handle.state::<Shell>().port.lock().unwrap();
            if url.scheme() == "http" && url.host_str() == Some("127.0.0.1") && port.is_some() && url.port() == port {
                return true;
            }
            // Autre site : navigateur par défaut (http/https/mailto uniquement), jamais dans la fenêtre.
            if matches!(url.scheme(), "http" | "https" | "mailto") {
                let _ = handle.opener().open_url(url.as_str(), None::<&str>);
            }
            false
        })
        .build()?;
    Ok(())
}

fn message(app: &AppHandle, text: &str) {
    app.dialog().message(text).title("COACH").show(|_| {});
}

fn backup_data(app: &AppHandle) {
    let Ok(dir) = data_dir(app) else { return };
    let db = dir.join("coach.db");
    if !db.is_file() {
        message(app, "Aucune donnée à sauvegarder pour l'instant. / Nothing to back up yet.");
        return;
    }
    let handle = app.clone();
    app.dialog().file().set_file_name("coach-backup.db").add_filter("SQLite", &["db"]).save_file(move |picked| {
        let Some(FilePath::Path(dest)) = picked else { return };
        let result = sidecar_path().and_then(|exe| {
            let mut cmd = Command::new(exe);
            cmd.arg("backup").arg("--db").arg(&db).arg("--dest").arg(&dest).stdin(Stdio::null());
            quiet(&mut cmd);
            cmd.output().map_err(|e| e.to_string())
        });
        match result {
            Ok(out) if out.status.success() => message(&handle, &format!("Sauvegarde créée / Backup created :\n{}", dest.display())),
            _ => message(&handle, "La sauvegarde a échoué. / The backup failed."),
        }
    });
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(win) = app.get_webview_window(WINDOW) {
                let _ = win.unminimize();
                let _ = win.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(Shell::default())
        .invoke_handler(tauri::generate_handler![get_state, has_key, save_settings, start_app, open_external])
        .setup(|app| {
            let settings = MenuItemBuilder::with_id("settings", "Réglages… / Settings…").accelerator("CmdOrCtrl+,").build(app)?;
            let open_data = MenuItemBuilder::with_id("open_data", "Ouvrir le dossier de données / Open data folder").build(app)?;
            let backup = MenuItemBuilder::with_id("backup", "Sauvegarder mes données… / Back up my data…").build(app)?;
            let reload = MenuItemBuilder::with_id("reload", "Recharger / Reload").accelerator("CmdOrCtrl+R").build(app)?;
            let about = PredefinedMenuItem::about(
                app,
                Some("À propos de COACH / About COACH"),
                Some(
                    AboutMetadataBuilder::new()
                        .name(Some("COACH"))
                        .version(Some(env!("CARGO_PKG_VERSION")))
                        .license(Some("AGPL-3.0-only"))
                        .website(Some("https://github.com/ECG-Rudy-Glt/COACH"))
                        .comments(Some("Self-hosted sports coach. Your data stays on this computer."))
                        .build(),
                ),
            )?;
            let app_menu = SubmenuBuilder::new(app, "COACH")
                .item(&settings)
                .item(&open_data)
                .item(&backup)
                .item(&reload)
                .separator()
                .item(&about)
                .separator()
                .quit()
                .build()?;
            let edit_menu = SubmenuBuilder::new(app, "Édition / Edit").undo().redo().separator().cut().copy().paste().select_all().build()?;
            let menu = MenuBuilder::new(app).items(&[&app_menu, &edit_menu]).build()?;
            app.set_menu(menu)?;
            app.on_menu_event(|app, event| match event.id().as_ref() {
                "settings" => {
                    if let Some(win) = app.get_webview_window(WINDOW) {
                        let _ = win.navigate(local_url("?settings=1"));
                    }
                }
                "open_data" => {
                    if let Ok(dir) = data_dir(app) {
                        let _ = app.opener().open_path(dir.display().to_string(), None::<&str>);
                    }
                }
                "backup" => backup_data(app),
                "reload" => {
                    if let Some(win) = app.get_webview_window(WINDOW) {
                        let _ = win.eval("window.location.reload()");
                    }
                }
                _ => {}
            });
            open_window(app.handle())?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("erreur au lancement de l'application COACH");
    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_sidecar(handle);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_url_est_une_cle_fernet() {
        // 32 octets -> 44 caractères avec remplissage, alphabet « url-safe ».
        let k = base64_url(&[0xfb; 32]);
        assert_eq!(k.len(), 44);
        assert!(k.ends_with('='));
        assert!(!k.contains('+') && !k.contains('/'));
        assert_eq!(base64_url(b"Man"), "TWFu");
        assert_eq!(base64_url(b"Ma"), "TWE=");
    }

    #[test]
    fn fournisseurs_connus() {
        assert_eq!(provider_needs_key("anthropic"), Some(true));
        assert_eq!(provider_needs_key("ollama"), Some(false));
        assert_eq!(provider_needs_key("none"), Some(false));
        assert_eq!(provider_needs_key("custom"), None);
    }

    #[test]
    fn texte_refuse_les_caracteres_de_controle() {
        assert!(clean_text("gpt-4o", 100).is_ok());
        assert!(clean_text("a\nb", 100).is_err());
        assert!(clean_text(&"x".repeat(101), 100).is_err());
    }
}
