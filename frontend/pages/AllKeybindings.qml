import QtQuick
import QtQuick.Controls.Basic
import "../theme"
import "../services"
import "../components"

Item {
    id: root

    property string searchText: ""
    property string selectedCategory: "All"
    property string selectedSubmap: "All"
    property int expandedIndex: -1
    property int selectedIndex: 0
    signal requestClose()

    property real savedScrollY: 0
    property int savedSelectedIndex: 0
    property bool shouldRestorePosition: false
    property bool initialLoadDone: false
    property string layoutClass: "expanded"

    function _syncLayoutClass() {
        layoutClass = ResponsiveLogic.computeLayoutClass(root.width, layoutClass);
    }
    onWidthChanged: _syncLayoutClass()
    Component.onCompleted: _syncLayoutClass()

    function findBindIndex(bindId) {
        if (!bindId || !root.filteredBinds) return -1;
        for (var i = 0; i < root.filteredBinds.length; i++) {
            if (root.filteredBinds[i] && root.filteredBinds[i].id === bindId) {
                return i;
            }
        }
        return -1;
    }

    function saveScrollPositionForOp(op) {
        if (!initialLoadDone) return;
        savedScrollY = listView.contentY;
        var idx = -1;
        if (op && op.bindId) {
            idx = findBindIndex(op.bindId);
        }
        if (idx >= 0) {
            savedSelectedIndex = idx;
        } else {
            savedSelectedIndex = root.selectedIndex;
        }
        shouldRestorePosition = true;
    }

    function showSearch(text) {
        var q = text || "";
        root.shouldRestorePosition = false;
        searchField.text = q;
        root.searchText = q;
        root.selectedCategory = "All";
        root.selectedSubmap = "All";
        searchField.forceFocus();
    }

    readonly property var filteredBinds: KeybindData.filter(searchText, selectedCategory, selectedSubmap)

    Connections {
        target: EditService
        function onBindAdded(shortcut, key, mods, submap) {
            var filterActive = (root.searchText.length > 0) || (root.selectedCategory !== "All") || (root.selectedSubmap !== "All");
            if (filterActive) {
                root.shouldRestorePosition = false;
                root.searchText = "";
                root.selectedCategory = "All";
                root.selectedSubmap = "All";
                searchField.text = "";
                EditService.showToast("Added " + shortcut + " (filter cleared to show new bind)", true);
            }
        }
        function onDialogOpenChanged() {
            if (EditService.dialogOpen && EditService.activeOp) {
                root.saveScrollPositionForOp(EditService.activeOp);
            }
        }
        function onBindDeleted(bindId, label) {
            if (!root.shouldRestorePosition) {
                root.savedScrollY = listView.contentY;
                var idx = root.findBindIndex(bindId);
                root.savedSelectedIndex = (idx >= 0) ? idx : root.selectedIndex;
                root.shouldRestorePosition = true;
            }
        }
    }

    Connections {
        target: KeybindData
        function onLoadingChanged() {
            if (KeybindData.loading && KeybindData.binds && KeybindData.binds.length > 0) {
                if (!root.shouldRestorePosition) {
                    root.savedScrollY = listView.contentY;
                    root.savedSelectedIndex = root.selectedIndex;
                    root.shouldRestorePosition = true;
                }
            }
        }
    }

    onSearchTextChanged: {
        shouldRestorePosition = false;
    }
    onSelectedCategoryChanged: {
        shouldRestorePosition = false;
    }
    onSelectedSubmapChanged: {
        shouldRestorePosition = false;
    }

    onFilteredBindsChanged: {
        if (!initialLoadDone) {
            initialLoadDone = (filteredBinds && filteredBinds.length > 0);
            selectedIndex = (filteredBinds && filteredBinds.length > 0) ? 0 : -1;
            expandedIndex = -1;
            return;
        }

        if (shouldRestorePosition) {
            shouldRestorePosition = false;
            var targetIndex = Math.min(savedSelectedIndex, Math.max(0, filteredBinds.length - 1));
            selectedIndex = targetIndex;
            expandedIndex = -1;
            var targetY = savedScrollY;
            Qt.callLater(function() {
                var maxY = Math.max(0, listView.contentHeight - listView.height);
                listView.contentY = Math.min(targetY, maxY);
                listView.positionViewAtIndex(targetIndex, ListView.Contain);
            });
        } else {
            if (selectedIndex >= filteredBinds.length) {
                selectedIndex = Math.max(0, filteredBinds.length - 1);
            }
            expandedIndex = -1;
        }
    }

    focus: true

    Keys.onPressed: function(event) {
        if (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_R) {
            KeybindData.reload();
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Escape) {
            if (searchField.text.length > 0) {
                searchField.text = "";
                event.accepted = true;
            } else {
                root.requestClose();
                event.accepted = true;
            }
            return;
        }
        if (event.key === Qt.Key_Down) {
            if (selectedIndex < filteredBinds.length - 1) {
                selectedIndex++;
                listView.positionViewAtIndex(selectedIndex, ListView.Contain);
            }
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Up) {
            if (selectedIndex > 0) {
                selectedIndex--;
                listView.positionViewAtIndex(selectedIndex, ListView.Contain);
            }
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (selectedIndex >= 0 && selectedIndex < filteredBinds.length) {
                expandedIndex = (expandedIndex === selectedIndex) ? -1 : selectedIndex;
            }
            event.accepted = true;
            return;
        }
        // Focus search if printable text is typed while list has focus
        if (event.text && event.text.length > 0 && !(event.modifiers & Qt.ControlModifier) && !(event.modifiers & Qt.AltModifier)) {
            searchField.forceFocus();
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: Deck.space16
        spacing: Deck.space12

        // Top control bar: Search + Add Keybind + Keyboard View Toggle (wrapping Flow)
        Flow {
            width: parent.width
            spacing: Deck.space12

            SearchField {
                id: searchField
                width: root.layoutClass === "compact"
                    ? parent.width
                    : Math.max(180, parent.width - kbToggle.width - addKeybindBtn.width - 24)
                onTextChanged: {
                    root.shouldRestorePosition = false;
                    root.searchText = text;
                }
                onCleared: {
                    root.shouldRestorePosition = false;
                    root.searchText = "";
                }
            }

            ActionButton {
                id: addKeybindBtn
                variant: "accent"
                iconText: ""
                text: "Add Keybind"
                onClicked: EditService.requestAdd()
            }

            // Keyboard View Toggle (disabled: "soon" until Phase 2b-2)
            Rectangle {
                id: kbToggle
                width: kbRow.width + 18
                height: 38
                radius: Deck.radiusSmall
                color: Deck.surface
                border.width: 1
                border.color: Deck.alpha(Deck.muted, 0.2)
                opacity: 0.55

                Row {
                    id: kbRow
                    anchors.centerIn: parent
                    spacing: 8

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 14
                        color: Deck.muted
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Keyboard"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                    }

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: soonText.implicitWidth + 8
                        height: 16
                        radius: 4
                        color: Deck.elevated

                        Text {
                            id: soonText
                            anchors.centerIn: parent
                            text: "soon"
                            font.family: Deck.fontFamily
                            font.pixelSize: 9
                            color: Deck.muted
                        }
                    }
                }
            }
        }

        // Category Chips (wrap via ChipFlow)
        CategoryChips {
            width: parent.width
            categories: KeybindData.categories
            totalCount: KeybindData.binds.length
            selectedCategory: root.selectedCategory
            onCategorySelected: function(cat) {
                root.shouldRestorePosition = false;
                root.selectedCategory = cat;
            }
        }

        // Submap note or selector + Results header count (wrapping Flow)
        Flow {
            width: parent.width
            spacing: 8

            // Submap selector or note
            Flow {
                spacing: 8
                width: Math.min(implicitWidth, parent.width)

                Text {
                    text: KeybindData.submaps.length > 0 ? "Submap:" : "No submaps in this config"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.muted
                }

                // Submap chips if present
                Repeater {
                    model: KeybindData.submaps.length > 0 ? ["All"].concat(KeybindData.submaps) : []
                    delegate: Rectangle {
                        height: 20
                        width: subTxt.implicitWidth + 10
                        radius: 4
                        color: root.selectedSubmap === modelData ? Deck.accent : Deck.surface
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
                                root.shouldRestorePosition = false;
                                root.selectedSubmap = modelData;
                            }
                        }
                    }
                }
            }

            // Results count "N of M keybindings"
            Text {
                text: root.filteredBinds.length + " of " + KeybindData.binds.length + " keybindings"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
            }
        }

        // Main List Area
        Item {
            width: parent.width
            height: parent.height - y - (companionBanner.visible ? (companionBanner.height + parent.spacing) : 0)

            // Loading state (initial scan only)
            Item {
                anchors.fill: parent
                visible: KeybindData.loading && (!KeybindData.binds || KeybindData.binds.length === 0)

                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 32
                        color: Deck.accent
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Scanning keybindings..."
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSize
                        color: Deck.muted
                    }
                }
            }

            // Error state
            EmptyState {
                anchors.fill: parent
                visible: !KeybindData.loading && KeybindData.error.length > 0
                icon: ""
                title: "Failed to scan configuration"
                message: KeybindData.error
                buttonText: "Retry Scan"
                onButtonClicked: KeybindData.reload()
            }

            // No results search state
            EmptyState {
                anchors.fill: parent
                visible: (!KeybindData.loading || (KeybindData.binds && KeybindData.binds.length > 0)) && !KeybindData.error && root.filteredBinds.length === 0
                icon: ""
                title: "No keybindings match your search"
                message: "Try searching for another key, description, or action."
                buttonText: root.searchText ? "Clear Search" : ""
                onButtonClicked: {
                    root.shouldRestorePosition = false;
                    searchField.text = "";
                    root.searchText = "";
                    root.selectedCategory = "All";
                }
            }

            // Virtualized ListView
            ListView {
                id: listView
                objectName: "listView"
                anchors.fill: parent
                anchors.topMargin: 8
                visible: (!KeybindData.loading || (KeybindData.binds && KeybindData.binds.length > 0)) && !KeybindData.error && root.filteredBinds.length > 0
                model: root.filteredBinds
                clip: true
                spacing: 6
                boundsBehavior: Flickable.StopAtBounds

                ScrollBar.vertical: ScrollBar {
                    active: true
                    width: 6
                }

                delegate: KeybindRow {
                    width: listView.width - (listView.ScrollBar.vertical.visible ? 10 : 0)
                    layoutClass: root.layoutClass
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

        // Persistent Companion Warning Footer Banner
        Rectangle {
            id: companionBanner
            width: parent.width
            height: Math.max(26, companionRow.implicitHeight + 8)
            radius: 4
            color: Deck.alpha(Deck.muted, 0.12)
            border.width: 1
            border.color: Deck.alpha(Deck.muted, 0.25)
            visible: (EditService.companionWarning.length > 0) || KeybindData.hasCompanionConf

            Row {
                id: companionRow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 8
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: ""
                    font.family: Deck.fontFamily
                    font.pixelSize: 11
                    color: Deck.muted
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 18
                    wrapMode: Text.WordWrap
                    text: "hyprland.conf is not modified by HyprDeck"
                    font.family: Deck.fontFamily
                    font.pixelSize: 10
                    color: Deck.muted
                    font.italic: true
                }
            }
        }
    }
}
