import QtQuick
import Quickshell
import Quickshell.Io
import "theme"
import "services"

ShellRoot {
    id: root

    readonly property string mode: (Quickshell.env("HKS_MODE") || "window").toLowerCase()

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
    }

    Loader {
        id: shellLoader
        source: root.mode === "popup" ? "PopupShell.qml" : (root.mode === "recorder-test" ? "dev/RecorderHarness.qml" : "WindowShell.qml")
    }
}
