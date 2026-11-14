pragma Singleton
import QtQuick
import Quickshell

Singleton {
    id: root

    readonly property string appDisplayName: "System Settings"
    readonly property string windowTitle: "System Settings"
    readonly property string subtitle: "Hyprland"
    readonly property string quickshellDir: "settings"
    readonly property string ipcTarget: "settings"
}
