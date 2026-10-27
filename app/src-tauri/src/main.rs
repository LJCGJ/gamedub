// Evita abrir console no Windows em release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    gamedub_app_lib::run()
}
