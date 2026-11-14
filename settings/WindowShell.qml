import QtQuick
import Quickshell
import "theme"
import "shared_components"
import "components"
import "pages"
import "services"

FloatingWindow {
    id: win

    title: AppInfo.windowTitle
    implicitWidth: 1040
    implicitHeight: 720
    color: HKS.bg
    visible: Quickshell.env("HKS_START_HIDDEN") !== "1"

    readonly property bool keepAlive: Quickshell.env("HKS_KEEP_ALIVE") === "1"
    property bool reopening: false
    property bool unsavedPromptOpen: false
    property string currentPage: Quickshell.env("HKS_SETTINGS_PAGE") || "appearance"

    onClosed: {
        if (win.reopening) {
            return;
        }
        if (SettingsService.hasUnsavedChanges) {
            SettingsService.discard();
        }
        win.unsavedPromptOpen = false;
        if (win.keepAlive) {
            win.visible = false;
        }
    }

    Timer {
        id: reopenTimer
        interval: 16
        repeat: false
        onTriggered: {
            win.visible = true;
            win.reopening = false;
        }
    }

    function openWindow() {
        win.reopening = true;
        win.visible = false;
        reopenTimer.restart();
        if (!SettingsService.loading && !SettingsService.hasUnsavedChanges) {
            SettingsService.reload();
        }
    }

    function _performClose() {
        reopenTimer.stop();
        win.reopening = false;
        win.unsavedPromptOpen = false;
        if (win.keepAlive) {
            win.visible = false;
        } else {
            Qt.quit();
        }
    }

    function closeWindow(force) {
        if (!force && SettingsService.hasUnsavedChanges) {
            win.unsavedPromptOpen = true;
            return;
        }
        if (SettingsService.hasUnsavedChanges) {
            SettingsService.discard();
        }
        _performClose();
    }

    function toggleWindow() {
        if (win.backingWindowVisible) {
            win.closeWindow(false);
        } else {
            win.openWindow();
        }
    }

    function navigate(pageId) {
        if (pageId) {
            win.currentPage = String(pageId);
        }
    }

    CloseGuard {
        id: closeGuard
        recorderActive: false
        editDialogOpen: false
        dialogOpen: win.unsavedPromptOpen
        focusItem: rootSurface.Window.activeFocusItem
    }

    Component.onCompleted: {
        SettingsService.reload();
    }

    readonly property var placeholderPages: [
        { id: "display", icon: "󰍹", title: "Display", summary: "Monitor resolution, refresh rate, scale, VRR, and arrangement." },
        { id: "input", icon: "󰌌", title: "Input", summary: "Mouse sensitivity, touchpad gestures, and keyboard repeat rate." },
        { id: "audio", icon: "󰕾", title: "Audio", summary: "Output sinks, input sources, and per-device volume." },
        { id: "bluetooth", icon: "󰂯", title: "Bluetooth", summary: "Adapter power, pairing, and connected devices." },
        { id: "network", icon: "󰖩", title: "Network", summary: "Wi-Fi networks, Ethernet links, and DNS status." },
        { id: "power", icon: "󰁹", title: "Power", summary: "Idle timeouts, sleep behavior, and battery profiles." },
        { id: "sysinfo", icon: "󰋼", title: "System info", summary: "OS, kernel, Hyprland version, and hardware overview." }
    ]

    function currentPlaceholder() {
        for (var i = 0; i < placeholderPages.length; i++) {
            if (placeholderPages[i].id === win.currentPage) return placeholderPages[i];
        }
        return null;
    }

    Rectangle {
        id: rootSurface
        anchors.fill: parent
        color: HKS.bg
        focus: true

        Keys.onEscapePressed: function(event) {
            if (win.unsavedPromptOpen) {
                win.unsavedPromptOpen = false;
                event.accepted = true;
                return;
            }
            if (closeGuard.escapeAllowed) {
                win.closeWindow(false);
                event.accepted = true;
            } else {
                event.accepted = false;
            }
        }

        Row {
            anchors.fill: parent
            anchors.bottomMargin: unsavedBar.visible ? unsavedBar.height : 0

            // Sidebar
            Rectangle {
                width: 230
                height: parent.height
                color: HKS.surface

                // Close [X]
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
                        font.pixelSize: 12
                        color: closeMa.containsMouse && closeGuard.closeAllowed ? HKS.critical : HKS.muted
                    }

                    MouseArea {
                        id: closeMa
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: closeGuard.closeAllowed
                        cursorShape: closeGuard.closeAllowed ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: win.closeWindow(false)
                    }
                }

                Column {
                    anchors.fill: parent
                    anchors.margins: HKS.space12
                    spacing: HKS.space12

                    // Brand Header
                    Row {
                        spacing: 10
                        anchors.left: parent.left
                        anchors.leftMargin: 4
                        topPadding: 4
                        bottomPadding: 4

                        Rectangle {
                            width: 30
                            height: 30
                            radius: 8
                            color: HKS.alpha(HKS.accent, 0.15)
                            border.width: 1
                            border.color: HKS.accent
                            Text {
                                anchors.centerIn: parent
                                text: ""
                                font.family: HKS.fontFamily
                                font.pixelSize: 14
                                color: HKS.accent
                            }
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            Text {
                                text: AppInfo.appDisplayName
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                font.weight: Font.Bold
                                color: HKS.fg
                            }
                            Text {
                                text: AppInfo.subtitle
                                font.family: HKS.fontFamily
                                font.pixelSize: 10
                                color: HKS.muted
                            }
                        }
                    }

                    SearchField {
                        id: globalSearch
                        width: parent.width
                        height: 34
                        placeholder: "Search settings..."
                    }

                    Column {
                        width: parent.width
                        spacing: 4

                        SidebarItem {
                            width: parent.width
                            icon: "󰃟"
                            text: "Appearance"
                            active: win.currentPage === "appearance" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "appearance";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰖲"
                            text: "Desktop behavior"
                            active: win.currentPage === "desktop" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "desktop";
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: HKS.alpha(HKS.muted, 0.15)
                        }

                        Repeater {
                            model: win.placeholderPages
                            delegate: SidebarItem {
                                required property var modelData
                                width: parent.width
                                icon: modelData.icon
                                text: modelData.title
                                badge: "soon"
                                disabled: true
                                active: win.currentPage === modelData.id
                            }
                        }
                    }
                }
            }

            // Main Content
            Item {
                width: parent.width - 230
                height: parent.height

                OptionsPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length > 0 || win.currentPage === "appearance" || win.currentPage === "desktop"
                    section: win.currentPage === "desktop" ? "desktop" : "appearance"
                    pageTitle: win.currentPage === "desktop" ? "Desktop behavior" : "Appearance"
                    searchQuery: globalSearch.text
                }

                PlaceholderPage {
                    readonly property var ph: win.currentPlaceholder()
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && ph !== null
                    title: ph ? ph.title : ""
                    icon: ph ? ph.icon : ""
                    summary: ph ? ph.summary : ""
                }
            }
        }

        // Unsaved-changes bottom bar
        Rectangle {
            id: unsavedBar
            visible: SettingsService.hasUnsavedChanges || SettingsService.statusMessage.length > 0
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 48
            color: HKS.surface
            border.width: 1
            border.color: HKS.alpha(HKS.accent, 0.35)

            Row {
                anchors.fill: parent
                anchors.leftMargin: HKS.space16
                anchors.rightMargin: HKS.space16
                spacing: HKS.space12

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - actionsRow.width - HKS.space12
                    text: SettingsService.hasUnsavedChanges
                        ? "You have unsaved changes (live preview active)."
                        : SettingsService.statusMessage
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: SettingsService.hasUnsavedChanges ? HKS.warning : HKS.accent
                }

                Row {
                    id: actionsRow
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: HKS.space8
                    visible: SettingsService.hasUnsavedChanges

                    ActionButton {
                        text: "Discard"
                        compact: true
                        enabled: !SettingsService.busy
                        onClicked: SettingsService.discard()
                    }

                    ActionButton {
                        text: SettingsService.busy ? "Saving..." : "Save"
                        variant: "accent"
                        compact: true
                        enabled: !SettingsService.busy && SettingsService.includeInstalled
                        onClicked: SettingsService.save()
                    }
                }
            }
        }

        // Unsaved changes close confirmation modal
        Rectangle {
            anchors.fill: parent
            visible: win.unsavedPromptOpen
            color: HKS.alpha(HKS.bg, 0.72)
            z: 20

            MouseArea { anchors.fill: parent }

            Rectangle {
                anchors.centerIn: parent
                width: 420
                height: promptCol.implicitHeight + 36
                radius: HKS.radius
                color: HKS.surface
                border.width: 1
                border.color: HKS.accent

                Column {
                    id: promptCol
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12

                    Text {
                        text: "Unsaved Changes"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeLarge
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Text {
                        width: parent.width
                        text: "Discard live preview changes and close, or keep editing?"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                        wrapMode: Text.WordWrap
                    }

                    Row {
                        anchors.right: parent.right
                        spacing: 8

                        ActionButton {
                            text: "Keep Editing"
                            compact: true
                            onClicked: win.unsavedPromptOpen = false
                        }

                        ActionButton {
                            text: "Discard & Close"
                            variant: "danger"
                            compact: true
                            onClicked: win.closeWindow(true)
                        }
                    }
                }
            }
        }
    }
}
