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
    minimumSize: Qt.size(Deck.minWindowWidth, Deck.minWindowHeight)
    color: Deck.bg
    visible: Quickshell.env("HKS_START_HIDDEN") !== "1"

    readonly property bool keepAlive: Quickshell.env("HKS_KEEP_ALIVE") === "1"
    property bool reopening: false
    property bool unsavedPromptOpen: false
    property string currentPage: Quickshell.env("HKS_SETTINGS_PAGE") || "appearance"
    property alias inputPageRef: inputPage
    property alias globalSearchRef: globalSearch
    property alias rootSurfaceRef: rootSurface
    property string lastGrabStatus: ""
    property int lastGrabSeq: 0
    property int debugOverrideWidth: 0
    property int debugOverrideHeight: 0
    readonly property real effectiveWinWidth: win.debugOverrideWidth > 0 ? win.debugOverrideWidth : win.width
    readonly property real effectiveWinHeight: win.debugOverrideHeight > 0 ? win.debugOverrideHeight : win.height
    readonly property string sidebarMode: ResponsiveLogic.sidebarModeForWindowWidth(win.effectiveWinWidth)
    readonly property bool compactRail: win.sidebarMode === "rail"
    property bool railSearchExpanded: false
    property string railTipText: ""
    property real railTipY: 0

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
        if (globalSearch.text.trim().length > 0) return optionsPage;
        if (win.currentPage === "appearance" || win.currentPage === "desktop") return optionsPage;
        if (win.currentPage === "display") return displayPage;
        if (win.currentPage === "input") return inputPage;
        if (win.currentPage === "audio") return audioPage;
        if (win.currentPage === "bluetooth") return bluetoothPage;
        if (win.currentPage === "network") return networkPage;
        if (win.currentPage === "themes") return themesPage;
        if (win.currentPage === "power") return powerPage;
        if (win.currentPage === "sysinfo") return systemPage;
        if (win.currentPage === "keyboard") return keyboardPage;
        return optionsPage;
    }

    function pageItemById(pageId) {
        if (pageId === "appearance" || pageId === "desktop") return optionsPage;
        if (pageId === "display") return displayPage;
        if (pageId === "input") return inputPage;
        if (pageId === "audio") return audioPage;
        if (pageId === "bluetooth") return bluetoothPage;
        if (pageId === "network") return networkPage;
        if (pageId === "themes") return themesPage;
        if (pageId === "power") return powerPage;
        if (pageId === "sysinfo") return systemPage;
        if (pageId === "keyboard") return keyboardPage;
        return null;
    }

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
            Deck.refreshTheme();
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
        width: win.effectiveWinWidth
        height: win.effectiveWinHeight
        color: Deck.bg
        focus: true

        Keys.onEscapePressed: function(event) {
            if (win.compactRail && win.railSearchExpanded) {
                win.railSearchExpanded = false;
                event.accepted = true;
                return;
            }
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
                id: sidebarRect
                width: ResponsiveLogic.sidebarWidthForMode(win.sidebarMode)
                height: parent.height
                color: Deck.surface

                Column {
                    id: sidebarTopCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Deck.space12
                    spacing: Deck.space12

                    // Brand Header
                    Row {
                        id: brandRow
                        spacing: 10
                        width: parent.width
                        topPadding: 4
                        bottomPadding: 4

                        Item {
                            width: win.compactRail ? parent.width : 30
                            height: 30

                            Rectangle {
                                x: win.compactRail ? Math.round((parent.width - width) / 2) : 4
                                width: 30
                                height: 30
                                radius: 8
                                color: Deck.alpha(Deck.accent, 0.15)
                                border.width: 1
                                border.color: Deck.accent

                                Text {
                                    anchors.centerIn: parent
                                    text: ""
                                    font.family: Deck.fontFamily
                                    font.pixelSize: 14
                                    color: Deck.accent
                                }
                            }
                        }

                        Column {
                            visible: !win.compactRail
                            width: Math.max(0, parent.width - 44)
                            anchors.verticalCenter: parent.verticalCenter

                            Text {
                                objectName: "elideOk"
                                width: parent.width
                                text: AppInfo.appDisplayName
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                font.weight: Font.Bold
                                color: Deck.fg
                                elide: Text.ElideRight
                            }

                            Text {
                                objectName: "elideOk"
                                width: parent.width
                                text: AppInfo.subtitle
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: Deck.muted
                                elide: Text.ElideRight
                            }
                        }
                    }

                    // Slot reserving space for inline SearchField when expanded/narrow, or search toggle icon when rail
                    Item {
                        id: searchSlotBox
                        width: parent.width
                        height: 34

                        Rectangle {
                            visible: win.compactRail
                            anchors.fill: parent
                            radius: 6
                            color: (win.railSearchExpanded || globalSearch.text.length > 0)
                                ? Deck.alpha(Deck.accent, 0.18)
                                : Deck.elevated
                            border.width: 1
                            border.color: (win.railSearchExpanded || globalSearch.text.length > 0)
                                ? Deck.accent
                                : Deck.alpha(Deck.muted, 0.25)

                            Text {
                                anchors.centerIn: parent
                                text: "󰍉"
                                font.family: Deck.fontFamily
                                font.pixelSize: 15
                                color: (win.railSearchExpanded || globalSearch.text.length > 0) ? Deck.accent : Deck.fg
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    win.railSearchExpanded = !win.railSearchExpanded;
                                    if (win.railSearchExpanded) {
                                        globalSearch.forceFocus();
                                    }
                                }
                            }
                        }
                    }
                }

                Flickable {
                    id: sidebarNavFlick
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: sidebarTopCol.bottom
                    anchors.topMargin: Deck.space12
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: Deck.space12
                    anchors.rightMargin: Deck.space12
                    anchors.bottomMargin: Deck.space12
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    contentWidth: width
                    contentHeight: navCol.implicitHeight

                    Column {
                        id: navCol
                        width: sidebarNavFlick.width
                        spacing: 4

                        SidebarItem {
                            width: parent.width
                            icon: "󰃟"
                            text: "Appearance"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "appearance" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "appearance";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰖲"
                            text: "Desktop behavior"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "desktop" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "desktop";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰍹"
                            text: "Display"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "display" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "display";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰌌"
                            text: "Input"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "input" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "input";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰕾"
                            text: "Audio"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "audio" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "audio";
                                AudioService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰂯"
                            text: "Bluetooth"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "bluetooth" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "bluetooth";
                                BluetoothService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰖩"
                            text: "Network"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "network" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "network";
                                NetworkService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰏘"
                            text: "Themes"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "themes" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "themes";
                                ThemesService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰁹"
                            text: "Power"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "power" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "power";
                                PowerService.reload(false);
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰋼"
                            text: "System info"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "sysinfo" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "sysinfo";
                            }
                        }

                        SidebarItem {
                            width: parent.width
                            icon: "󰌌"
                            text: "Keyboard shortcuts"
                            compactRail: win.compactRail
                            showRailTooltip: false
                            active: win.currentPage === "keyboard" && globalSearch.text.trim().length === 0
                            onRailHoverState: function(h, lbl, src) { win._updateRailTip(h, lbl, src); }
                            onClicked: {
                                globalSearch.text = "";
                                win.railSearchExpanded = false;
                                win.currentPage = "keyboard";
                                KeyboardService.reload();
                            }
                        }

                        Rectangle {
                            visible: win.placeholderPages.length > 0
                            width: parent.width
                            height: 1
                            color: Deck.alpha(Deck.muted, 0.15)
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
                                compactRail: win.compactRail
                                showRailTooltip: false
                                active: win.currentPage === modelData.id
                            }
                        }
                    }
                }
            }

            // Main Content
            Item {
                id: mainContentItem
                width: parent.width - sidebarRect.width
                height: parent.height

                OptionsPage {
                    id: optionsPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length > 0 || win.currentPage === "appearance" || win.currentPage === "desktop"
                    section: win.currentPage === "desktop" ? "desktop" : "appearance"
                    pageTitle: win.currentPage === "desktop" ? "Desktop behavior" : "Appearance"
                    searchQuery: globalSearch.text
                }

                DisplayPage {
                    id: displayPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "display"
                }

                InputPage {
                    id: inputPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "input"
                }

                AudioPage {
                    id: audioPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "audio"
                }

                BluetoothPage {
                    id: bluetoothPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "bluetooth"
                }

                NetworkPage {
                    id: networkPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "network"
                }

                ThemesPage {
                    id: themesPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "themes"
                }

                PowerPage {
                    id: powerPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "power"
                }

                SystemPage {
                    id: systemPage
                    anchors.fill: parent
                    visible: globalSearch.text.trim().length === 0 && win.currentPage === "sysinfo"
                }

                KeyboardPage {
                    id: keyboardPage
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

        // Single persistent SearchField (inline in full/narrow sidebar, floating overlay in compactRail mode)
        SearchField {
            id: globalSearch
            z: 40
            visible: !win.compactRail || win.railSearchExpanded || text.length > 0
            x: win.compactRail ? (sidebarRect.width + Deck.space8) : (sidebarRect.x + Deck.space12)
            y: Deck.space12 + brandRow.height + Deck.space12
            width: win.compactRail
                ? Math.min(280, Math.max(180, rootSurface.width - sidebarRect.width - Deck.space16))
                : (sidebarRect.width - Deck.space12 * 2)
            height: 34
            placeholder: "Search settings..."
        }

        // Rail hover tooltip rendered above content outside Flickable clipping
        Rectangle {
            visible: win.compactRail && win.railTipText.length > 0
            z: 45
            x: sidebarRect.width + 8
            y: win.railTipY
            width: railOverlayTipTxt.implicitWidth + 16
            height: 26
            radius: 6
            color: Deck.elevated
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.5)

            Text {
                id: railOverlayTipTxt
                anchors.centerIn: parent
                text: win.railTipText
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.fg
            }
        }

        // Unsaved-changes bottom bar
        Rectangle {
            id: unsavedBar
            visible: SettingsService.hasUnsavedChanges || SettingsService.statusMessage.length > 0
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: unsavedInner.implicitHeight + Deck.space16
            color: Deck.surface
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.35)

            Item {
                id: unsavedInner
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: Deck.space16
                anchors.rightMargin: Deck.space16
                anchors.topMargin: Deck.space8

                readonly property real actionsNaturalW: SettingsService.hasUnsavedChanges ? (discardBtn.implicitWidth + Deck.space8 + saveBtn.implicitWidth) : 0
                readonly property bool stacked: SettingsService.hasUnsavedChanges
                    && (unsavedMsgMetrics.advanceWidth + Deck.space12 + actionsNaturalW > unsavedInner.width)

                implicitHeight: stacked
                    ? (unsavedTxt.implicitHeight + Deck.space8 + actionsRow.implicitHeight)
                    : Math.max(unsavedTxt.implicitHeight, actionsRow.implicitHeight)
                height: implicitHeight

                TextMetrics {
                    id: unsavedMsgMetrics
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    text: unsavedTxt.text
                }

                Text {
                    id: unsavedTxt
                    x: 0
                    y: unsavedInner.stacked ? 0 : Math.max(0, Math.round((unsavedInner.implicitHeight - height) / 2))
                    width: unsavedInner.stacked
                        ? unsavedInner.width
                        : Math.max(0, unsavedInner.width - unsavedInner.actionsNaturalW - (unsavedInner.actionsNaturalW > 0 ? Deck.space12 : 0))
                    text: SettingsService.hasUnsavedChanges
                        ? "You have unsaved changes (live preview active)."
                        : SettingsService.statusMessage
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: SettingsService.hasUnsavedChanges ? Deck.warning : Deck.accent
                    wrapMode: Text.WordWrap
                }

                Flow {
                    id: actionsRow
                    visible: SettingsService.hasUnsavedChanges
                    x: unsavedInner.stacked ? 0 : Math.max(0, unsavedInner.width - width)
                    y: unsavedInner.stacked
                        ? (unsavedTxt.implicitHeight + Deck.space8)
                        : Math.max(0, Math.round((unsavedInner.implicitHeight - height) / 2))
                    width: unsavedInner.stacked ? unsavedInner.width : unsavedInner.actionsNaturalW
                    spacing: Deck.space8

                    ActionButton {
                        id: discardBtn
                        text: "Discard"
                        compact: true
                        enabled: !SettingsService.busy
                        onClicked: SettingsService.discard()
                    }

                    ActionButton {
                        id: saveBtn
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
            color: Deck.alpha(Deck.bg, 0.72)
            z: 20

            MouseArea { anchors.fill: parent }

            Rectangle {
                anchors.centerIn: parent
                width: Math.min(420, parent.width - Deck.space24)
                height: promptCol.implicitHeight + 36
                radius: Deck.radius
                color: Deck.surface
                border.width: 1
                border.color: Deck.accent

                Column {
                    id: promptCol
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12

                    Text {
                        width: parent.width
                        text: "Unsaved Changes"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeLarge
                        font.weight: Font.Bold
                        color: Deck.fg
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: "Discard live preview changes and close, or keep editing?"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                        wrapMode: Text.WordWrap
                    }

                    Flow {
                        width: parent.width
                        layoutDirection: Qt.RightToLeft
                        spacing: 8

                        ActionButton {
                            text: "Discard & Close"
                            variant: "danger"
                            compact: true
                            onClicked: win.closeWindow(true)
                        }

                        ActionButton {
                            text: "Keep Editing"
                            compact: true
                            onClicked: win.unsavedPromptOpen = false
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
            color: Deck.alpha(Deck.bg, 0.78)
            z: 30

            MouseArea { anchors.fill: parent }

            Rectangle {
                anchors.centerIn: parent
                width: Math.min(440, parent.width - Deck.space24)
                height: displayConfirmCol.implicitHeight + 36
                radius: Deck.radius
                color: Deck.surface
                border.width: 1
                border.color: Deck.accent

                Column {
                    id: displayConfirmCol
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12

                    Text {
                        width: parent.width
                        text: parent.parent.parent.inputModal ? "Keep these input settings?" : "Keep these display settings?"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeLarge
                        font.weight: Font.Bold
                        color: Deck.fg
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: "Reverting automatically in " + parent.parent.parent.modalSecs + "s unless confirmed."
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.warning
                        wrapMode: Text.WordWrap
                    }

                    Flow {
                        width: parent.width
                        layoutDirection: Qt.RightToLeft
                        spacing: 8

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
                    }
                }
            }
        }
    }
}
