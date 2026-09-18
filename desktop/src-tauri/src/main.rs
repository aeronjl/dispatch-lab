#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    fs::{self, File},
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent};

struct Backend {
    child: Child,
    origin: String,
    token: String,
}
#[derive(Clone, Default)]
struct Backends(Arc<Mutex<HashMap<String, Backend>>>);

fn python(payload: &Path) -> PathBuf {
    payload.join(if cfg!(windows) {
        "python/python.exe"
    } else {
        "python/bin/python3.12"
    })
}

fn payload(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let installed = app
        .path()
        .resource_dir()
        .map_err(|e| e.to_string())?
        .join("payload");
    if installed.join("source/desktop_entry.py").exists() {
        return Ok(installed);
    }
    if cfg!(debug_assertions) {
        return Ok(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../build/desktop/payload"));
    }
    Err(
        "The installed runtime is missing. Reinstall Dispatch Lab; your workspace is separate."
            .into(),
    )
}

fn runtime_command(payload: &Path, mode: &str) -> Command {
    let mut c = Command::new(python(payload));
    c.arg("-s")
        .arg(payload.join("source/desktop_entry.py"))
        .arg(mode)
        .current_dir(payload.join("source"))
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        .env("PYTHONNOUSERSITE", "1")
        .env("PYTHONUTF8", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONUNBUFFERED", "1")
        .env("GRADIO_ANALYTICS_ENABLED", "False")
        .env("HF_HUB_DISABLE_TELEMETRY", "1");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x08000000);
    }
    c
}

fn client() -> reqwest::blocking::Client {
    reqwest::blocking::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(2))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("local HTTP client")
}

fn stop(mut backend: Backend) {
    let _ = client()
        .post(format!("{}/desktop/stop", backend.origin))
        .header("x-dispatch-owner", &backend.token)
        .send();
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(10) {
        if matches!(backend.child.try_wait(), Ok(Some(_))) {
            return;
        }
        thread::sleep(Duration::from_millis(50));
    }
    let _ = backend.child.kill();
    let _ = backend.child.wait();
}

fn save_download(_: tauri::Webview, event: tauri::webview::DownloadEvent<'_>) -> bool {
    if let tauri::webview::DownloadEvent::Requested { destination, .. } = event {
        let filename = destination
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        if let Some(path) = rfd::FileDialog::new()
            .set_title("Save Dispatch Lab export")
            .set_file_name(filename)
            .save_file()
        {
            *destination = path;
        } else {
            return false;
        }
    }
    true
}

fn start(app: &tauri::AppHandle, archive: Option<PathBuf>, label: String) -> Result<(), String> {
    let resources = payload(app)?;
    let store = app.path().app_local_data_dir().map_err(|e| e.to_string())?;
    let logs = store.join("logs");
    fs::create_dir_all(&logs).map_err(|e| e.to_string())?;
    let allowed = Arc::new(Mutex::new(String::new()));
    let navigation_origin = allowed.clone();
    let popup_origin = allowed.clone();
    let popup_app = app.clone();
    let window = WebviewWindowBuilder::new(app, &label, WebviewUrl::App("index.html".into()))
        .title("Dispatch Lab")
        .inner_size(1440.0, 920.0)
        .min_inner_size(480.0, 560.0)
        .on_new_window(move |url, features| {
            if url.scheme() == "https" {
                let _ = open::that(url.as_str());
            } else if url.origin().ascii_serialization() == *popup_origin.lock().unwrap() {
                let origin = popup_origin.lock().unwrap().clone();
                if let Ok(window) = WebviewWindowBuilder::new(
                    &popup_app,
                    uuid::Uuid::new_v4().to_string(),
                    WebviewUrl::External("about:blank".parse().unwrap()),
                )
                .title("Dispatch Lab · Report")
                .window_features(features)
                .on_navigation(move |next| {
                    if next.as_str() == "about:blank"
                        || next.origin().ascii_serialization() == origin
                    {
                        return true;
                    }
                    if next.scheme() == "https" {
                        let _ = open::that(next.as_str());
                    }
                    false
                })
                .on_download(save_download)
                .build()
                {
                    return tauri::webview::NewWindowResponse::Create { window };
                }
            }
            tauri::webview::NewWindowResponse::Deny
        })
        .on_download(save_download)
        .on_navigation(move |url| {
            if (url.scheme() == "tauri" && url.host_str() == Some("localhost"))
                || (url.scheme() == "http" && url.host_str() == Some("tauri.localhost"))
            {
                return true;
            }
            if url.origin().ascii_serialization() == *navigation_origin.lock().unwrap() {
                return true;
            }
            if url.scheme() == "https" {
                let _ = open::that(url.as_str());
            }
            false
        })
        .build()
        .map_err(|e| e.to_string())?;
    let app = app.clone();
    thread::spawn(move || {
        let result = (|| -> Result<(), String> {
            // Reserve an ephemeral candidate; if another process wins the bind,
            // readiness proof fails and the next attempt chooses another port.
            for _ in 0..3 {
                let socket = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
                let port = socket.local_addr().map_err(|e| e.to_string())?.port();
                let origin = format!("http://127.0.0.1:{port}");
                let instance = uuid::Uuid::new_v4().to_string();
                let token = format!(
                    "{}{}",
                    uuid::Uuid::new_v4().simple(),
                    uuid::Uuid::new_v4().simple()
                );
                let proof = format!("{:x}", Sha256::digest(format!("{token}:{instance}")));
                let log = File::create(logs.join(format!("runtime-{instance}.log")))
                    .map_err(|e| e.to_string())?;
                let mut command = runtime_command(&resources, "serve");
                command
                    .args(["--port", &port.to_string()])
                    .arg("--workspace")
                    .arg(store.join("workspace"))
                    .env("DISPATCH_DESKTOP_TOKEN", &token)
                    .env("DISPATCH_DESKTOP_INSTANCE", &instance)
                    .stdin(Stdio::null())
                    .stdout(log.try_clone().map_err(|e| e.to_string())?)
                    .stderr(log);
                if let Some(ref file) = archive {
                    command.arg("--archive").arg(file);
                }
                drop(socket);
                let child = command
                    .spawn()
                    .map_err(|e| format!("Unable to start the bundled runtime: {e}"))?;
                app.state::<Backends>().0.lock().unwrap().insert(
                    label.clone(),
                    Backend {
                        child,
                        origin: origin.clone(),
                        token: token.clone(),
                    },
                );
                let began = Instant::now();
                while began.elapsed() < Duration::from_secs(90) {
                    if app.get_webview_window(&label).is_none() {
                        if let Some(backend) =
                            app.state::<Backends>().0.lock().unwrap().remove(&label)
                        {
                            stop(backend);
                        }
                        return Ok(());
                    }
                    let exited = {
                        let state = app.state::<Backends>();
                        let mut children = state.0.lock().unwrap();
                        match children.get_mut(&label) {
                            Some(backend) => backend
                                .child
                                .try_wait()
                                .map_err(|e| e.to_string())?
                                .is_some(),
                            None => return Ok(()),
                        }
                    };
                    if exited {
                        break;
                    }
                    let response = client()
                        .get(format!("{origin}/desktop/ready"))
                        .send()
                        .and_then(|r| r.json::<serde_json::Value>());
                    if let Ok(value) = response {
                        if value["proof"].as_str() == Some(&proof)
                            && value["instance"].as_str() == Some(&instance)
                        {
                            // URL is constructed solely from our loopback port and private ticket.
                            let url: tauri::Url = format!("{origin}/desktop/open?key={token}")
                                .parse()
                                .map_err(|e| format!("Invalid local URL: {e}"))?;
                            *allowed.lock().unwrap() = origin.clone();
                            window.navigate(url).map_err(|e| e.to_string())?;
                            return Ok(());
                        }
                    }
                    thread::sleep(Duration::from_millis(200));
                }
                if let Some(backend) = app.state::<Backends>().0.lock().unwrap().remove(&label) {
                    stop(backend);
                }
            }
            Err("The runtime did not become ready. Your saved workspace is unchanged. Open the runtime log folder from Help for details.".into())
        })();
        if let Err(error) = result {
            if let Some(backend) = app.state::<Backends>().0.lock().unwrap().remove(&label) {
                stop(backend);
            }
            let text = serde_json::to_string(&error).unwrap();
            let _ = window.eval(format!(
                "document.getElementById('status').textContent={text}"
            ));
        }
    });
    Ok(())
}

fn recording(app: &tauri::AppHandle) {
    let app = app.clone();
    thread::spawn(move || {
        if let Some(path) = rfd::FileDialog::new()
            .set_title("Open a saved Dispatch Lab recording")
            .add_filter("Dispatch Lab recordings", &["gz", "dispatch-run", "zip"])
            .pick_file()
        {
            if let Err(error) = start(&app, Some(path), uuid::Uuid::new_v4().to_string()) {
                rfd::MessageDialog::new()
                    .set_title("Could not open recording")
                    .set_description(error)
                    .show();
            }
        }
    });
}

fn main() {
    // A real stdio entry point for local MCP hosts; no desktop window is created.
    if std::env::args().nth(1).as_deref() == Some("--mcp") {
        let exe = std::env::current_exe().expect("application location");
        let base = exe.parent().unwrap();
        let resources = if cfg!(target_os = "macos") {
            base.join("../Resources/payload")
        } else {
            base.join("payload")
        };
        let status = runtime_command(&resources, "mcp")
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .status();
        std::process::exit(status.map(|s| s.code().unwrap_or(1)).unwrap_or(1));
    }
    let builder = tauri::Builder::default().manage(Backends::default())
        .plugin(tauri_plugin_single_instance::init(|app, args, _| {
            if let Some(path) = args.get(1).filter(|v| !v.starts_with('-')) {
                let _ = start(app, Some(path.into()), uuid::Uuid::new_v4().to_string());
            } else if let Some(window) = app.webview_windows().values().next() {
                let _ = window.show(); let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
            let open_item = MenuItem::with_id(app, "open", "Open recording…", true, Some("CmdOrCtrl+O"))?;
            let fresh = MenuItem::with_id(app, "workspace", "Open workspace", true, None::<&str>)?;
            let logs = MenuItem::with_id(app, "logs", "Runtime logs", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit Dispatch Lab", true, Some("CmdOrCtrl+Q"))?;
            let menu = Menu::with_items(app, &[
                &Submenu::with_items(app, "Dispatch Lab", true, &[&fresh, &open_item, &quit])?,
                &Submenu::with_items(app, "Edit", true, &[&PredefinedMenuItem::copy(app, None)?, &PredefinedMenuItem::paste(app, None)?, &PredefinedMenuItem::select_all(app, None)?])?,
                &Submenu::with_items(app, "Help", true, &[&logs])?
            ])?;
            app.set_menu(menu)?;
            let archive = std::env::args().nth(1).filter(|v| !v.starts_with('-')).map(PathBuf::from);
            start(app.handle(), archive, "main".into()).map_err(std::io::Error::other)?;
            Ok(())
        })
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => recording(app),
            "workspace" => { let _ = start(app, None, uuid::Uuid::new_v4().to_string()); },
            "logs" => { if let Ok(path) = app.path().app_local_data_dir() { let _ = open::that(path.join("logs")); } },
            "quit" => { for window in app.webview_windows().values() { let _ = window.close(); } },
            _ => {}
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let window = window.clone();
                thread::spawn(move || {
                    let label = window.label().to_string();
                    let backend = window.app_handle().state::<Backends>().0.lock().unwrap().remove(&label);
                    if let Some(backend) = backend {
                        let workers = client().get(format!("{}/desktop/status", backend.origin)).header("x-dispatch-owner", &backend.token)
                            .send().and_then(|r| r.json::<serde_json::Value>()).ok().and_then(|v| Some(v["workers"].as_u64()? + v["ui_requests"].as_u64()?));
                        if workers.unwrap_or(1) > 0 {
                            let answer = rfd::MessageDialog::new().set_title("Close Dispatch Lab?")
                                .set_description("This development build will interrupt active calculations. Completed checkpoints are retained; uncommitted work may need to run again.")
                                .set_buttons(rfd::MessageButtons::OkCancel).show();
                            if answer != rfd::MessageDialogResult::Ok {
                                window.app_handle().state::<Backends>().0.lock().unwrap().insert(label, backend);
                                return;
                            }
                        }
                        stop(backend);
                    }
                    let _ = window.destroy();
                });
            }
        });
    builder
        .build(tauri::generate_context!())
        .expect("Dispatch Lab desktop shell")
        .run(|app, event| {
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Opened { urls } = &event {
                for url in urls {
                    if let Ok(path) = url.to_file_path() {
                        let _ = start(app, Some(path), uuid::Uuid::new_v4().to_string());
                    }
                }
            }
            if let tauri::RunEvent::Exit = event {
                let backends: Vec<_> = app
                    .state::<Backends>()
                    .0
                    .lock()
                    .unwrap()
                    .drain()
                    .map(|(_, backend)| backend)
                    .collect();
                for backend in backends {
                    stop(backend);
                }
            }
        });
}
