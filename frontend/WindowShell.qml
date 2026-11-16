import QtQuick
import QtQuick.Layouts
import Quickshell
import "theme"
import "services"
import "components"
import "pages"

FloatingWindow {
    id: win

    title: "Hyprland Keybind Studio"
    implicitWidth: 1000
    implicitHeight: 700
    color: HKS.bg
    visible: Quickshell.env("HKS_START_HIDDEN") !== "1"

    readonly property bool keepAlive: Quickshell.env("HKS_KEEP_ALIVE") === "1"
    // True while openWindow() is mid-pulse, so the `closed` signal emitted by our
    // own hide step is not mistaken for a compositor-initiated close.
    property bool reopening: false

    // Compositor-initiated close (Super+X / Alt+F4 / xdg_toplevel.close): the
    // backing window is gone, but Quickshell's internal "wants visible" flag is
    // left set, which makes a later `visible = true` a silent no-op. Writing
    // visible=false here resets that flag. (`closed` verified live on 0.3.2.)
    onClosed: {
        if (win.reopening) {
            return;
        }
        if (win.keepAlive) {
            win.visible = false;
        }
    }
    onVisibleChanged: {
        if (win.visible) {
            HKS.refreshTheme();
        }
    }
    property string currentPage: Quickshell.env("HKS_PAGE") || "all" // "all" | "conflicts" | "disabled" | "backups" | "settings"

    Timer {
        id: reopenTimer
        interval: 16
        repeat: false
        onTriggered: {
            win.visible = true;
            win.reopening = false;
        }
    }

    // Always pulse (hide, then show 16ms later) regardless of the reported
    // `visible` state: it re-maps on the active workspace, raises focus, and
    // clears a stuck internal visibility flag.
    function openWindow() {
        win.reopening = true;
        win.visible = false;
        reopenTimer.restart();
        if (!KeybindData.loading) {
            KeybindData.reload();
        }
    }

    function closeWindow() {
        reopenTimer.stop();
        win.reopening = false;
        if (keepAlive) {
            win.visible = false;
        } else {
            Qt.quit();
        }
    }

    // Truth comes from the backing window, not the (possibly stale) `visible`.
    function toggleWindow() {
        if (win.backingWindowVisible) {
            win.closeWindow();
        } else {
            win.openWindow();
        }
    }

    CloseGuard {
        id: closeGuard
        recorderActive: RecorderService.active
        editDialogOpen: EditService.editDialogOpen
        dialogOpen: EditService.dialogOpen
        focusItem: rootSurface.Window.activeFocusItem
    }

    Component.onCompleted: {
        EditService.loadBackups();
        RecorderService.heal();
    }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: !EditService.editDialogOpen && !EditService.dialogOpen && !RecorderService.active
        onActivated: EditService.requestAdd()
    }

    Rectangle {
        id: rootSurface
        anchors.fill: parent
        color: HKS.bg
        focus: true

        // App-wide Escape: only reached when no page/dialog accepted it first
        // (pages keep their own handling), and never from a text input.
        Keys.onEscapePressed: function(event) {
            if (closeGuard.escapeAllowed) {
                win.closeWindow();
                event.accepted = true;
            } else {
                event.accepted = false;
            }
        }

        // Main layout: Sidebar (left) + Content Area (right)
        Row {
            anchors.fill: parent
            anchors.bottomMargin: statusBar.height

            // Left Sidebar
            Rectangle {
                width: 210
                height: parent.height
                color: HKS.surface
                border.width: 0

                // Close [X] (no compositor titlebar: QT_WAYLAND_DISABLE_WINDOWDECORATION=1)
                Rectangle {
                    id: closeButton
                    z: 5
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: HKS.space12
                    anchors.rightMargin: HKS.space8
                    width: 24
                    height: 24
                    radius: 6
                    opacity: closeGuard.closeAllowed ? 1.0 : 0.35
                    color: closeMa.containsMouse && closeGuard.closeAllowed
                        ? HKS.alpha(HKS.critical, 0.25) : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.family: HKS.fontFamily
                        font.pixelSize: 11
                        color: closeMa.containsMouse && closeGuard.closeAllowed ? HKS.critical : HKS.muted
                    }

                    MouseArea {
                        id: closeMa
                        anchors.fill: parent
                        enabled: closeGuard.closeAllowed
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: win.closeWindow()
                    }
                }

                // 1px subtle divider on right
                Rectangle {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 1
                    color: HKS.alpha(HKS.muted, 0.15)
                }

                Column {
                    anchors.fill: parent
                    anchors.margins: HKS.space12
                    spacing: HKS.space16

                    // App Brand Header
                    Row {
                        spacing: 10
                        anchors.left: parent.left
                        anchors.right: parent.right

                        Rectangle {
                            width: 32
                            height: 32
                            radius: 6
                            color: HKS.alpha(HKS.accent, 0.2)
                            border.width: 1
                            border.color: HKS.accent

                            Text {
                                anchors.centerIn: parent
                                text: ""
                                font.family: HKS.fontFamily
                                font.pixelSize: 16
                                color: HKS.accent
                            }
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text {
                                text: "Keybind Studio"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                font.weight: Font.Bold
                                color: HKS.fg
                            }
                            Text {
                                text: "Hyprland (HKS)"
                                font.family: HKS.fontFamily
                                font.pixelSize: 10
                                color: HKS.muted
                            }
                        }
                    }

                    // Navigation Items
                    Column {
                        width: parent.width
                        spacing: 4

                        SidebarItem {
                            width: parent.width
                            icon: ""
                            text: "All Keybindings"
                            active: win.currentPage === "all"
                            onClicked: win.currentPage = "all"
                        }

                        SidebarItem {
                            width: parent.width
                            icon: ""
                            text: "Conflicts"
                            active: win.currentPage === "conflicts"
                            badge: String(KeybindData.conflicts ? KeybindData.conflicts.length : 0)
                            onClicked: win.currentPage = "conflicts"
                        }

                        SidebarItem {
                            width: parent.width
                            icon: ""
                            text: "Disabled"
                            active: win.currentPage === "disabled"
                            badge: String(KeybindData.disabledBinds ? KeybindData.disabledBinds.length : 0)
                            onClicked: win.currentPage = "disabled"
                        }

                        SidebarItem {
                            width: parent.width
                            icon: ""
                            text: "Backups"
                            active: win.currentPage === "backups"
                            badge: String(EditService.backups ? EditService.backups.length : 0)
                            onClicked: win.currentPage = "backups"
                        }

                        SidebarItem {
                            width: parent.width
                            icon: ""
                            text: "Settings"
                            active: win.currentPage === "settings"
                            onClicked: win.currentPage = "settings"
                        }
                    }
                }
            }

            // Right Main Content
            Item {
                width: parent.width - 210
                height: parent.height

                AllKeybindings {
                    id: allBindsPage
                    anchors.fill: parent
                    visible: win.currentPage === "all"
                    onRequestClose: {
                        if (closeGuard.closeAllowed) {
                            win.closeWindow();
                        }
                    }
                }

                Conflicts {
                    id: conflictsPage
                    anchors.fill: parent
                    visible: win.currentPage === "conflicts"
                    onRequestShowInList: function(query) {
                        allBindsPage.showSearch(query);
                        win.currentPage = "all";
                    }
                    onRequestClose: {
                        win.currentPage = "all";
                    }
                }

                Disabled {
                    id: disabledPage
                    anchors.fill: parent
                    visible: win.currentPage === "disabled"
                }

                Backups {
                    id: backupsPage
                    anchors.fill: parent
                    visible: win.currentPage === "backups"
                }

                Settings {
                    id: settingsPage
                    anchors.fill: parent
                    visible: win.currentPage === "settings"
                }
            }
        }

        // Bottom Status Bar
        Rectangle {
            id: statusBar
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 28
            color: HKS.surface
            border.width: 0

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                color: HKS.alpha(HKS.muted, 0.15)
            }

            Row {
                anchors.left: parent.left
                anchors.leftMargin: HKS.space12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12

                Text {
                    text: {
                        var env = KeybindData.environment || {};
                        var st = KeybindData.stats || {};
                        var lang = env.language ? ("Language: " + env.language) : "";
                        var ep = env.entrypoint ? ("Entry: " + env.entrypoint.split("/").pop()) : "";
                        var hv = env.hyprland_version ? ("Hyprland: " + env.hyprland_version) : "";
                        var cnt = "Binds: " + KeybindData.binds.length;
                        var sbTime = (st.sandbox && st.sandbox.elapsed_ms !== undefined)
                            ? ("Elapsed: " + st.sandbox.elapsed_ms.toFixed(1) + "ms")
                            : "";
                        return [lang, ep, hv, cnt, sbTime].filter(Boolean).join("  •  ");
                    }
                    font.family: HKS.fontFamily
                    font.pixelSize: 10
                    color: HKS.muted
                }
            }

            Text {
                anchors.right: parent.right
                anchors.rightMargin: HKS.space12
                anchors.verticalCenter: parent.verticalCenter
                text: "Ctrl+R to reload  •  Esc to clear"
                font.family: HKS.fontFamily
                font.pixelSize: 10
                color: HKS.alpha(HKS.muted, 0.7)
            }
        }

        // Floating Toast Notification
        Rectangle {
            id: toastBox
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: statusBar.top
            anchors.bottomMargin: 16
            height: 38
            width: toastRow.implicitWidth + 28
            radius: 19
            color: HKS.elevated
            border.width: 1
            border.color: HKS.alpha(HKS.accent, 0.5)
            visible: EditService.toastVisible
            z: 99

            Row {
                id: toastRow
                anchors.centerIn: parent
                spacing: 12

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: ""
                    font.family: HKS.fontFamily
                    font.pixelSize: 12
                    color: HKS.accent
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: EditService.toastMessage
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    font.weight: Font.DemiBold
                    color: HKS.fg
                }

                // Undo Button (when canUndo is true)
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: EditService.canUndo
                    height: 24
                    width: undoTxt.implicitWidth + 16
                    radius: 12
                    color: undoMa.containsMouse ? HKS.alpha(HKS.accent, 0.3) : HKS.alpha(HKS.accent, 0.15)
                    border.width: 1
                    border.color: HKS.alpha(HKS.accent, 0.5)

                    Text {
                        id: undoTxt
                        anchors.centerIn: parent
                        text: "Undo"
                        font.family: HKS.fontFamily
                        font.pixelSize: 11
                        font.weight: Font.Bold
                        color: HKS.accent
                    }

                    MouseArea {
                        id: undoMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: EditService.requestRestoreLatest()
                    }
                }

                // Dismiss Button
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 20
                    height: 20
                    radius: 10
                    color: dismissMa.containsMouse ? HKS.alpha(HKS.muted, 0.25) : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.family: HKS.fontFamily
                        font.pixelSize: 10
                        color: HKS.muted
                    }

                    MouseArea {
                        id: dismissMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: EditService.hideToast()
                    }
                }
            }
        }

        // Keybind Edit Dialog Modal Overlay
        KeybindEditDialog {
            anchors.fill: parent
            visible: EditService.editDialogOpen
            z: 90
        }

        // Confirmation Dialog Modal Overlay
        EditConfirmDialog {
            anchors.fill: parent
            visible: EditService.dialogOpen
            z: 100
        }
    }
}
