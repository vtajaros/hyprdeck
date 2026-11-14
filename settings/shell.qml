import QtQuick
import Quickshell
import Quickshell.Io
import "services"

ShellRoot {
    id: root

    IpcHandler {
        target: AppInfo.ipcTarget

        function open() {
            winLoader.item.openWindow();
        }

        function toggle() {
            winLoader.item.toggleWindow();
        }

        function close() {
            winLoader.item.closeWindow(false);
        }

        function reload() {
            SettingsService.reload();
        }

        function navigate(page: string) {
            winLoader.item.navigate(page);
        }
    }

    Loader {
        id: winLoader
        source: "WindowShell.qml"
    }
}
