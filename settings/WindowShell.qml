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
    property alias inputPageRef: inputPage

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
    onVisibleChanged: {
        if (win.visible) {
            HKS.refreshTheme();
            if (!KeyboardService.loading && !KeyboardService.busy) {
                KeyboardService.reload();
            }
        } else {
            BluetoothService.stopScanIfActive();
        }
    }
    onCurrentPageChanged: {
        if (win.currentPage !== "bluetooth") {
            BluetoothService.stopScanIfActive();
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
        if (!DisplayService.loading && !DisplayService.hasDraftChanges && !DisplayService.countdownActive) {
            DisplayService.reload();
        }
        if (!InputService.loading && !InputService.hasDraftChanges && !InputService.countdownActive) {
            InputService.reload();
        }
        if (!AudioService.loading && !AudioService.busy) {
            AudioService.reload(true);
        }
        if (!BluetoothService.loading && !BluetoothService.busy) {
            BluetoothService.reload(true);
        }
        if (!NetworkService.loading && !NetworkService.busy) {
            NetworkService.reload(true);
        }
        if (!ThemesService.loading && !ThemesService.busy) {
            ThemesService.reload(true);
        }
        if (!PowerService.loading && !PowerService.busy) {
            PowerService.reload(true);
        }
        if (!KeyboardService.loading && !KeyboardService.busy) {
            KeyboardService.reload();
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
        dialogOpen: win.unsavedPromptOpen || DisplayService.countdownActive || InputService.countdownActive || BluetoothService.confirmOpen || NetworkService.confirmOpen || PowerService.confirmOpen
        focusItem: rootSurface.Window.activeFocusItem
    }

    Component.onCompleted: {
        SettingsService.reload();
        DisplayService.reload();
        InputService.reload();
        AudioService.reload(false);
        BluetoothService.reload(false);
        NetworkService.reload(false);
        ThemesService.reload(false);
        PowerService.reload(false);
        SystemService.reload();
        KeyboardService.reload();
    }

    Binding {
        target: AudioService
        property: "pollingEnabled"
        value: win.visible && win.currentPage === "audio"
    }

    Binding {
        target: BluetoothService
        property: "pollingEnabled"
        value: win.visible && win.currentPage === "bluetooth"
    }

    Binding {
        target: NetworkService
        property: "pollingEnabled"
        value: win.visible && win.currentPage === "network"
    }

    Binding {
        target: ThemesService
        property: "pollingEnabled"
        value: win.visible && win.currentPage === "themes"
    }

    Binding {
        target: PowerService
        property: "pollingEnabled"
        value: win.visible && win.currentPage === "power"
    }

    readonly property var placeholderPages: []

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

                        SidebarItem {
                            width: parent.width
                            icon: "󰍹"
                            text: "Display"
                            active: win.currentPage === "display" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "display";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰌌"
                            text: "Input"
                            active: win.currentPage === "input" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "input";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰕾"
                            text: "Audio"
                            active: win.currentPage === "audio" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "audio";
                                AudioService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰂯"
                            text: "Bluetooth"
                            active: win.currentPage === "bluetooth" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "bluetooth";
                                BluetoothService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰖩"
                            text: "Network"
                            active: win.currentPage === "network" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "network";
                                NetworkService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰏘"
                            text: "Themes"
                            active: win.currentPage === "themes" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "themes";
                                ThemesService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰁹"
                            text: "Power"
                            active: win.currentPage === "power" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "power";
                                PowerService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰋼"
                            text: "System info"
                            active: win.currentPage === "sysinfo" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "sysinfo";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰌌"
                            text: "Keyboard shortcuts"
                            active: win.currentPage === "keyboard" && globalSearch.text.trim().length === 0
                            onClicked: {
                                globalSearch.text = "";
                                win.currentPage = "keyboard";
                                KeyboardService.reload();
                            }
                        }

                        Rectangle {
                            visible: win.placeholderPages.length > 0
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

                DisplayPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "display"
                }

                InputPage {
                    id: inputPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "input"
                }

                AudioPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "audio"
                }

                BluetoothPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "bluetooth"
                }

                NetworkPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "network"
                }

                ThemesPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "themes"
                }

                PowerPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "power"
                }

                SystemPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "sysinfo"
                }

                KeyboardPage {
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "keyboard"
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

        // Shared 15s Confirm-or-Revert Countdown Modal (Display & Input)
        Rectangle {
            readonly property bool inputModal: InputService.countdownActive && !DisplayService.countdownActive
            readonly property bool modalBusy: inputModal ? InputService.busy : DisplayService.busy
            readonly property int modalSecs: inputModal ? InputService.remainingSeconds : DisplayService.remainingSeconds
            anchors.fill: parent
            visible: DisplayService.countdownActive || InputService.countdownActive
            color: HKS.alpha(HKS.bg, 0.78)
            z: 30

            MouseArea { anchors.fill: parent }

            Rectangle {
                anchors.centerIn: parent
                width: 440
                height: displayConfirmCol.implicitHeight + 36
                radius: HKS.radius
                color: HKS.surface
                border.width: 1
                border.color: HKS.accent

                Column {
                    id: displayConfirmCol
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12

                    Text {
                        text: parent.parent.parent.inputModal ? "Keep these input settings?" : "Keep these display settings?"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeLarge
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Text {
                        width: parent.width
                        text: "Reverting automatically in " + parent.parent.parent.modalSecs + "s unless confirmed."
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.warning
                        wrapMode: Text.WordWrap
                    }

                    Row {
                        anchors.right: parent.right
                        spacing: 8

                        ActionButton {
                            text: "Revert now"
                            variant: "danger"
                            compact: true
                            enabled: !parent.parent.parent.parent.modalBusy
                            onClicked: {
                                if (parent.parent.parent.parent.inputModal) {
                                    InputService.revertChanges();
                                } else {
                                    DisplayService.revertChanges();
                                }
                            }
                        }

                        ActionButton {
                            text: "Keep changes"
                            variant: "accent"
                            compact: true
                            enabled: !parent.parent.parent.parent.modalBusy
                            onClicked: {
                                if (parent.parent.parent.parent.inputModal) {
                                    InputService.keepChanges();
                                } else {
                                    DisplayService.keepChanges();
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
