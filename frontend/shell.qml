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
        function close() {
            Qt.quit();
        }
        function reload() {
            KeybindData.reload();
        }
    }

    Loader {
        id: shellLoader
        source: root.mode === "popup" ? "PopupShell.qml" : "WindowShell.qml"
    }
}
