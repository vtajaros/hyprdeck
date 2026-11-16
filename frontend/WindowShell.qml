import QtQuick
import QtQuick.Layouts
import Quickshell
import "theme"
import "services"
import "components"
import "pages"
import "../theme"

FloatingWindow {
    id: win

    title: AppInfo.windowTitle
    implicitWidth: 1000
    implicitHeight: 700
    minimumSize: Qt.size(Deck.minWindowWidth, Deck.minWindowHeight)
    color: Deck.bg
    visible: Deck.env("START_HIDDEN") !== "1"

    readonly property bool keepAlive: Deck.env("KEEP_ALIVE") === "1"
    property int debugOverrideWidth: 0
    property int debugOverrideHeight: 0
    readonly property int effectiveWinWidth: debugOverrideWidth > 0 ? debugOverrideWidth : win.width
    readonly property int effectiveWinHeight: debugOverrideHeight > 0 ? debugOverrideHeight : win.height
    readonly property string sidebarMode: ResponsiveLogic.sidebarModeForWindowWidth(win.effectiveWinWidth)
    readonly property bool compactRail: win.sidebarMode === "rail"
    readonly property int sidebarWidth: ResponsiveLogic.sidebarWidthForMode(win.sidebarMode)
    property string railTipText: ""
    property real railTipY: 0
    property int lastGrabSeq: 0
    property string lastGrabStatus: ""
    property alias rootSurfaceRef: rootSurface
    property alias editDialogRef: editDialog
    property alias confirmDialogRef: confirmDialog

    function _updateRailTip(hovered, label, sourceItem) {
        if (!win.compactRail || !hovered || !sourceItem) {
            if (!hovered && win.railTipText === label) {
                win.railTipText = "";
            }
            return;
        }
        var pt = sourceItem.mapToItem(rootSurface, 0, Math.round(sourceItem.height / 2));
        win.railTipY = Math.max(8, Math.min(rootSurface.height - 34, pt.y - 13));
        win.railTipText = label;
    }

    function activePageItem() {
        if (win.currentPage === "all") return allBindsPage;
        if (win.currentPage === "conflicts") return conflictsPage;
        if (win.currentPage === "disabled") return disabledPage;
        if (win.currentPage === "backups") return backupsPage;
        if (win.currentPage === "settings") return settingsPage;
        return allBindsPage;
    }

    function activeAuditTarget() {
        if (EditService.dialogOpen) return confirmDialog;
        if (editDialog.recorderRef && editDialog.recorderRef.opened) return editDialog.recorderRef.contentItem;
        if (EditService.editDialogOpen) return editDialog;
        return activePageItem();
    }
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
            Deck.refreshTheme();
        }
    }
    property string currentPage: Deck.env("PAGE") || "all" // "all" | "conflicts" | "disabled" | "backups" | "settings"

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
        width: win.effectiveWinWidth
        height: win.effectiveWinHeight
        color: Deck.bg
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
                width: win.sidebarWidth
                height: parent.height
                color: Deck.surface
                border.width: 0

                // 1px subtle divider on right
                Rectangle {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 1
                    color: Deck.alpha(Deck.muted, 0.15)
                }

                Column {
                    anchors.fill: parent
                    anchors.margins: win.compactRail ? Deck.space8 : Deck.space12
                    spacing: Deck.space16

                    // App Brand Header
                    Row {
                        spacing: 10
                        anchors.horizontalCenter: win.compactRail ? parent.horizontalCenter : undefined
                        anchors.left: win.compactRail ? undefined : parent.left
                        anchors.right: win.compactRail ? undefined : parent.right

                        Rectangle {
                            width: 32
                            height: 32
                            radius: 6
                            color: Deck.alpha(Deck.accent, 0.2)
                            border.width: 1
                            border.color: Deck.accent

                            Text {
                                anchors.centerIn: parent
                                text: ""
                                font.family: Deck.fontFamily
                                font.pixelSize: 16
                                color: Deck.accent
                            }
                        }

                        Column {
                            visible: !win.compactRail
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text {
                                text: "Keybind Studio"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                font.weight: Font.Bold
                                color: Deck.fg
                            }
                            Text {
                                text: "HyprDeck"
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: Deck.muted
                            }
                        }
                    }

                    // Navigation Items
                    Column {
                        width: parent.width
                        spacing: 4

                        SidebarItem {
                            width: parent.width
                            compactRail: win.compactRail
                            icon: ""
                            text: "All Keybindings"
                            active: win.currentPage === "all"
                            onClicked: win.currentPage = "all"
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                        }

                        SidebarItem {
                            width: parent.width
                            compactRail: win.compactRail
                            icon: ""
                            text: "Conflicts"
                            active: win.currentPage === "conflicts"
                            badge: String(KeybindData.conflicts ? KeybindData.conflicts.length : 0)
                            onClicked: win.currentPage = "conflicts"
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                        }

                        SidebarItem {
                            width: parent.width
                            compactRail: win.compactRail
                            icon: ""
                            text: "Disabled"
                            active: win.currentPage === "disabled"
                            badge: String(KeybindData.disabledBinds ? KeybindData.disabledBinds.length : 0)
                            onClicked: win.currentPage = "disabled"
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                        }

                        SidebarItem {
                            width: parent.width
                            compactRail: win.compactRail
                            icon: ""
                            text: "Backups"
                            active: win.currentPage === "backups"
                            badge: String(EditService.backups ? EditService.backups.length : 0)
                            onClicked: win.currentPage = "backups"
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                        }

                        SidebarItem {
                            width: parent.width
                            compactRail: win.compactRail
                            icon: ""
                            text: "Settings"
                            active: win.currentPage === "settings"
                            onClicked: win.currentPage = "settings"
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                        }
                    }
                }
            }

            // Right Main Content (with horizontal safety scroll <320px and wide cap ~1100px centered)
            Item {
                id: contentArea
                width: Math.max(0, parent.width - win.sidebarWidth)
                height: parent.height
                clip: true

                Flickable {
                    id: horizontalSafetyScroller
                    objectName: "horizontalSafetyScroller"
                    anchors.fill: parent
                    contentWidth: Math.max(width, 320)
                    contentHeight: height
                    interactive: contentWidth > width
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true

                    Item {
                        width: Math.min(horizontalSafetyScroller.contentWidth, 1100)
                        height: horizontalSafetyScroller.height
                        anchors.horizontalCenter: parent.horizontalCenter

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
            }
        }

        // Icon-rail hover tooltip
        Rectangle {
            visible: win.compactRail && win.railTipText.length > 0
            x: win.sidebarWidth + 8
            y: win.railTipY
            z: 95
            width: railTipLbl.implicitWidth + 18
            height: 26
            radius: 6
            color: Deck.elevated
            border.width: 1
            border.color: Deck.border

            Text {
                id: railTipLbl
                anchors.centerIn: parent
                text: win.railTipText
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.fg
            }
        }

        // Bottom Status Bar
        Rectangle {
            id: statusBar
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 28
            color: Deck.surface
            border.width: 0

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                color: Deck.alpha(Deck.muted, 0.15)
            }

            Text {
                objectName: "elideOk"
                anchors.left: parent.left
                anchors.leftMargin: Deck.space12
                anchors.right: statusHint.visible ? statusHint.left : parent.right
                anchors.rightMargin: Deck.space12
                anchors.verticalCenter: parent.verticalCenter
                elide: Text.ElideRight
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
                font.family: Deck.fontFamily
                font.pixelSize: 10
                color: Deck.muted
            }

            Text {
                id: statusHint
                visible: win.effectiveWinWidth >= 680
                anchors.right: parent.right
                anchors.rightMargin: Deck.space12
                anchors.verticalCenter: parent.verticalCenter
                text: "Ctrl+R to reload  •  Esc to clear"
                font.family: Deck.fontFamily
                font.pixelSize: 10
                color: Deck.alpha(Deck.muted, 0.7)
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
            color: Deck.elevated
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.5)
            visible: EditService.toastVisible
            z: 99

            Row {
                id: toastRow
                anchors.centerIn: parent
                spacing: 12

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: ""
                    font.family: Deck.fontFamily
                    font.pixelSize: 12
                    color: Deck.accent
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: EditService.toastMessage
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    font.weight: Font.DemiBold
                    color: Deck.fg
                }

                // Undo Button (when canUndo is true)
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: EditService.canUndo
                    height: 24
                    width: undoTxt.implicitWidth + 16
                    radius: 12
                    color: undoMa.containsMouse ? Deck.alpha(Deck.accent, 0.3) : Deck.alpha(Deck.accent, 0.15)
                    border.width: 1
                    border.color: Deck.alpha(Deck.accent, 0.5)

                    Text {
                        id: undoTxt
                        anchors.centerIn: parent
                        text: "Undo"
                        font.family: Deck.fontFamily
                        font.pixelSize: 11
                        font.weight: Font.Bold
                        color: Deck.accent
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
                    color: dismissMa.containsMouse ? Deck.alpha(Deck.muted, 0.25) : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.family: Deck.fontFamily
                        font.pixelSize: 10
                        color: Deck.muted
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
            id: editDialog
            anchors.fill: parent
            visible: EditService.editDialogOpen
            z: 90
        }

        // Confirmation Dialog Modal Overlay
        EditConfirmDialog {
            id: confirmDialog
            anchors.fill: parent
            visible: EditService.dialogOpen
            z: 100
        }
    }
}
