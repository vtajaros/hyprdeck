import QtQuick
import Quickshell
import Quickshell.Io
import "theme"
import "services"

ShellRoot {
    id: root

    readonly property string mode: (Quickshell.env("HKS_MODE") || "window").toLowerCase()
    readonly property bool debugEnabled: Quickshell.env("HKS_SETTINGS_DEBUG") === "1"

    IpcHandler {
        target: "hks"
        function open() {
            if (shellLoader.item && typeof shellLoader.item.openWindow === "function") {
                shellLoader.item.openWindow();
            }
        }
        function toggle() {
            if (shellLoader.item && typeof shellLoader.item.toggleWindow === "function") {
                shellLoader.item.toggleWindow();
            } else {
                Qt.quit();
            }
        }
        function close() {
            if (shellLoader.item && typeof shellLoader.item.closeWindow === "function") {
                shellLoader.item.closeWindow();
            } else {
                Qt.quit();
            }
        }
        function reload() {
            KeybindData.reload();
        }
        function openAdd() {
            if (shellLoader.item && typeof shellLoader.item.openWindow === "function") {
                shellLoader.item.openWindow();
            }
            EditService.requestAdd();
        }
        function openEditFirst() {
            if (KeybindData.binds && KeybindData.binds.length > 0) {
                EditService.requestEdit(KeybindData.binds[0]);
            }
        }
        function debugThemeState(): string {
            if (!root.debugEnabled) {
                return JSON.stringify({ ok: false, error: "debug mode disabled" });
            }
            return JSON.stringify({
                ok: true,
                themeMode: HKS.themeMode,
                colorsPath: HKS.colorsPath,
                visible: shellLoader.item ? !!shellLoader.item.visible : false,
                bg: String(HKS.bg),
                surface: String(HKS.surface),
                accent: String(HKS.accent),
                fg: String(HKS.fg)
            });
        }
    }

    Loader {
        id: shellLoader
        source: root.mode === "popup" ? "PopupShell.qml" : (root.mode === "recorder-test" ? "dev/RecorderHarness.qml" : "WindowShell.qml")
    }
}
