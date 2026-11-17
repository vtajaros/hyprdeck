import QtQuick
import "../theme"
import "../shared_components"
import "../services"
import "../keybind_studio/pages" as StudioPages
import "../keybind_studio/services" as StudioServices
import "../keybind_studio/components" as StudioComponents

Item {
    id: root

    property string activeTab: "all" // "all" | "conflicts" | "disabled" | "backups" | "settings"
    property string searchText: ""
    property string selectedCategory: "All"
    property string selectedSubmap: "All"
    property int expandedIndex: -1
    property int selectedIndex: 0

    property string layoutClass: "expanded"
    readonly property bool layoutShort: ResponsiveLogic.isLayoutShort(root.height)
    readonly property int outerMargin: Deck.scaledSpace(Deck.space24, root.layoutClass, root.layoutShort)
    readonly property real innerWidth: Math.min(
        Math.max(0, root.width - root.outerMargin * 2),
        Deck.contentMaxWidth
    )

    readonly property var filteredBinds: StudioServices.KeybindData.filter(
        root.searchText,
        root.selectedCategory,
        root.selectedSubmap
    )

    function _updateLayoutClass() {
        var usable = Math.max(Deck.minContentScrollWidth, root.width - Deck.space24 * 2);
        var next = ResponsiveLogic.computeLayoutClass(usable, root.layoutClass);
        if (next !== root.layoutClass) {
            root.layoutClass = next;
        }
    }

    Component.onCompleted: _updateLayoutClass()
    onWidthChanged: _updateLayoutClass()

    // Centered Header + View Switcher matching PageViewport
    Column {
        id: topHeaderCol
        width: root.innerWidth
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: root.outerMargin
        spacing: Deck.space12

        PageHeader {
            width: parent.width
            title: "Keyboard Shortcuts"
            subtitle: "Inspect, search, record, and edit Hyprland keybindings."

            ActionButton {
                text: "Refresh"
                compact: true
                enabled: !StudioServices.KeybindData.loading
                onClicked: StudioServices.KeybindData.reload()
            }

            ActionButton {
                visible: KeyboardService.available
                text: "Pop Out"
                compact: true
                enabled: !KeyboardService.busy
                onClicked: KeyboardService.openWindow()
            }
        }

        ChipFlow {
            width: parent.width
            layoutClass: root.layoutClass
            layoutShort: root.layoutShort
            spacing: 6

            ActionButton {
                text: "All Keybindings (" + (StudioServices.KeybindData.binds ? StudioServices.KeybindData.binds.length : 0) + ")"
                compact: true
                variant: root.activeTab === "all" ? "primary" : "default"
                onClicked: root.activeTab = "all"
            }

            ActionButton {
                text: "Conflicts (" + (StudioServices.KeybindData.conflicts ? StudioServices.KeybindData.conflicts.length : 0) + ")"
                compact: true
                variant: root.activeTab === "conflicts" ? "primary" : "default"
                onClicked: root.activeTab = "conflicts"
            }

            ActionButton {
                text: "Disabled (" + (StudioServices.KeybindData.disabledBinds ? StudioServices.KeybindData.disabledBinds.length : 0) + ")"
                compact: true
                variant: root.activeTab === "disabled" ? "primary" : "default"
                onClicked: root.activeTab = "disabled"
            }

            ActionButton {
                text: "Backups (" + (StudioServices.EditService.backups ? StudioServices.EditService.backups.length : 0) + ")"
                compact: true
                variant: root.activeTab === "backups" ? "primary" : "default"
                onClicked: root.activeTab = "backups"
            }

            ActionButton {
                text: "Studio Settings"
                compact: true
                variant: root.activeTab === "settings" ? "primary" : "default"
                onClicked: root.activeTab = "settings"
            }
        }
    }

    // Unified scrolling PageViewport for All Keybindings (two-column card grid)
    PageViewport {
        id: allViewport
        visible: root.activeTab === "all"
        anchors.top: topHeaderCol.bottom
        anchors.topMargin: Deck.space8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        allowTwoColumns: true

        readonly property string cardLayoutClass: ResponsiveLogic.computeLayoutClass(
            allViewport.twoColumnCardWidth,
            allViewport.layoutClass
        )

        // Search + Add Keybind + Category Chips Card
        SectionCard {
            width: allViewport.innerWidth
            cardPadding: Deck.space12
            spacing: Deck.space12

            Item {
                id: searchRow
                width: parent.width
                readonly property bool stacked: width < 420
                implicitHeight: stacked
                    ? (bindSearch.height + Deck.space8 + addBindBtn.height)
                    : Math.max(bindSearch.height, addBindBtn.height)
                height: implicitHeight

                SearchField {
                    id: bindSearch
                    x: 0
                    y: 0
                    width: searchRow.stacked
                        ? searchRow.width
                        : Math.max(160, searchRow.width - addBindBtn.width - Deck.space12)
                    placeholder: "Search keybindings (e.g. 'super enter', 'workspace', 'kitty')..."
                    onTextChanged: {
                        root.expandedIndex = -1;
                        root.searchText = text;
                    }
                    onCleared: {
                        root.expandedIndex = -1;
                        root.searchText = "";
                    }
                }

                ActionButton {
                    id: addBindBtn
                    x: searchRow.stacked ? 0 : Math.max(0, searchRow.width - width)
                    y: searchRow.stacked ? (bindSearch.height + Deck.space8) : 0
                    variant: "accent"
                    iconText: ""
                    text: "Add Keybind"
                    onClicked: StudioServices.EditService.requestAdd()
                }
            }

            StudioComponents.CategoryChips {
                width: parent.width
                categories: StudioServices.KeybindData.categories
                totalCount: StudioServices.KeybindData.binds ? StudioServices.KeybindData.binds.length : 0
                selectedCategory: root.selectedCategory
                onCategorySelected: function(cat) {
                    root.expandedIndex = -1;
                    root.selectedCategory = cat;
                }
            }

            // Submap selector + count row
            Flow {
                width: parent.width
                spacing: 8

                Text {
                    text: (StudioServices.KeybindData.submaps && StudioServices.KeybindData.submaps.length > 0)
                        ? "Submap:"
                        : "No submaps in this config"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.muted
                }

                Repeater {
                    model: (StudioServices.KeybindData.submaps && StudioServices.KeybindData.submaps.length > 0)
                        ? ["All"].concat(StudioServices.KeybindData.submaps)
                        : []
                    delegate: Rectangle {
                        required property string modelData
                        height: 20
                        width: subTxt.implicitWidth + 10
                        radius: 4
                        color: root.selectedSubmap === modelData ? Deck.accent : Deck.elevated
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.25)

                        Text {
                            id: subTxt
                            anchors.centerIn: parent
                            text: modelData
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: root.selectedSubmap === modelData ? Deck.bg : Deck.fg
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.expandedIndex = -1;
                                root.selectedSubmap = modelData;
                            }
                        }
                    }
                }

                Text {
                    text: "•  " + root.filteredBinds.length + " of " + (StudioServices.KeybindData.binds ? StudioServices.KeybindData.binds.length : 0) + " keybindings"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.muted
                }
            }
        }

        // Loading state
        SectionCard {
            visible: StudioServices.KeybindData.loading && (!StudioServices.KeybindData.binds || StudioServices.KeybindData.binds.length === 0)
            width: allViewport.innerWidth
            cardPadding: Deck.space24
            spacing: Deck.space8

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Scanning keybindings..."
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                color: Deck.muted
            }
        }

        // Error state
        EmptyState {
            visible: !StudioServices.KeybindData.loading && StudioServices.KeybindData.error.length > 0
            width: allViewport.innerWidth
            height: 220
            icon: ""
            title: "Failed to scan configuration"
            message: StudioServices.KeybindData.error
            buttonText: "Retry Scan"
            onButtonClicked: StudioServices.KeybindData.reload()
        }

        // Empty search state
        EmptyState {
            visible: (!StudioServices.KeybindData.loading || (StudioServices.KeybindData.binds && StudioServices.KeybindData.binds.length > 0))
                && !StudioServices.KeybindData.error
                && root.filteredBinds.length === 0
            width: allViewport.innerWidth
            height: 220
            icon: ""
            title: "No keybindings match your search"
            message: "Try searching for another key, description, or action."
            buttonText: root.searchText ? "Clear Search" : ""
            onButtonClicked: {
                bindSearch.text = "";
                root.searchText = "";
                root.selectedCategory = "All";
                root.selectedSubmap = "All";
            }
        }

        // Two-column Keybindings Grid (scrolls as one unified page)
        Flow {
            visible: (!StudioServices.KeybindData.loading || (StudioServices.KeybindData.binds && StudioServices.KeybindData.binds.length > 0))
                && !StudioServices.KeybindData.error
                && root.filteredBinds.length > 0
            width: allViewport.innerWidth
            spacing: allViewport.columnSpacing

            Repeater {
                model: (root.visible && root.activeTab === "all") ? root.filteredBinds : []
                delegate: StudioComponents.KeybindRow {
                    required property var modelData
                    required property int index
                    width: allViewport.twoColumnCardWidth
                    layoutClass: allViewport.cardLayoutClass
                    bindData: modelData
                    isSelected: root.selectedIndex === index
                    isExpanded: root.expandedIndex === index
                    onToggleExpand: {
                        root.selectedIndex = index;
                        root.expandedIndex = (root.expandedIndex === index) ? -1 : index;
                    }
                }
            }
        }

        // Companion Warning Banner
        Rectangle {
            visible: (StudioServices.EditService.companionWarning.length > 0) || StudioServices.KeybindData.hasCompanionConf
            width: allViewport.innerWidth
            height: Math.max(28, companionTxt.implicitHeight + 10)
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.muted, 0.12)
            border.width: 1
            border.color: Deck.alpha(Deck.muted, 0.25)

            Text {
                id: companionTxt
                anchors.fill: parent
                anchors.margins: 8
                wrapMode: Text.WordWrap
                text: "hyprland.conf is not modified by HyprDeck"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                font.italic: true
            }
        }
    }

    // Embedded Keybind Studio Sub-pages (Conflicts / Disabled / Backups / Settings)
    Item {
        id: hksContent
        visible: root.activeTab !== "all"
        width: Math.min(root.width, root.innerWidth + Deck.space16 * 2)
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: topHeaderCol.bottom
        anchors.topMargin: Deck.space8
        anchors.bottom: parent.bottom
        clip: true

        StudioPages.Conflicts {
            id: conflictsPage
            anchors.fill: parent
            visible: root.activeTab === "conflicts"
            onRequestShowInList: function(query) {
                bindSearch.text = query || "";
                root.searchText = query || "";
                root.selectedCategory = "All";
                root.selectedSubmap = "All";
                root.activeTab = "all";
            }
            onRequestClose: root.activeTab = "all"
        }

        StudioPages.Disabled {
            id: disabledPage
            anchors.fill: parent
            visible: root.activeTab === "disabled"
        }

        StudioPages.Backups {
            id: backupsPage
            anchors.fill: parent
            visible: root.activeTab === "backups"
        }

        StudioPages.Settings {
            id: settingsPage
            anchors.fill: parent
            visible: root.activeTab === "settings"
        }
    }

    // Floating Toast Notification for Keybind Studio edits
    Rectangle {
        id: toastBox
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 16
        height: 38
        width: toastRow.implicitWidth + 28
        radius: 19
        color: Deck.elevated
        border.width: 1
        border.color: Deck.alpha(Deck.accent, 0.5)
        visible: StudioServices.EditService.toastVisible
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
                text: StudioServices.EditService.toastMessage
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                font.weight: Font.DemiBold
                color: Deck.fg
            }

            ActionButton {
                visible: StudioServices.EditService.canUndo
                text: "Undo"
                compact: true
                onClicked: StudioServices.EditService.requestRestoreLatest()
            }

            ActionButton {
                text: "✕"
                compact: true
                onClicked: StudioServices.EditService.hideToast()
            }
        }
    }

    // Keybind Edit Dialog Modal Overlay
    StudioComponents.KeybindEditDialog {
        id: editDialog
        anchors.fill: parent
        visible: StudioServices.EditService.editDialogOpen
        z: 90
    }

    // Confirmation Dialog Modal Overlay
    StudioComponents.EditConfirmDialog {
        id: confirmDialog
        anchors.fill: parent
        visible: StudioServices.EditService.dialogOpen
        z: 100
    }
}
