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

    readonly property var filteredBinds: KeybindData.filter(searchText, selectedCategory, selectedSubmap)

    onFilteredBindsChanged: {
        if (selectedIndex >= filteredBinds.length) {
            selectedIndex = Math.max(0, filteredBinds.length - 1);
        }
        expandedIndex = -1;
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
        anchors.margins: HKS.space16
        spacing: HKS.space12

        // Top control bar: Search + Keyboard View Toggle
        Row {
            width: parent.width
            spacing: HKS.space12

            SearchField {
                id: searchField
                width: parent.width - kbToggle.width - 12
                onTextChanged: root.searchText = text
                onCleared: root.searchText = ""
            }

            // Keyboard View Toggle (disabled: "soon" until Phase 2b-2)
            Rectangle {
                id: kbToggle
                width: kbRow.width + 18
                height: 38
                radius: HKS.radiusSmall
                color: HKS.surface
                border.width: 1
                border.color: HKS.alpha(HKS.muted, 0.2)
                opacity: 0.55

                Row {
                    id: kbRow
                    anchors.centerIn: parent
                    spacing: 8

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: ""
                        font.family: HKS.fontFamily
                        font.pixelSize: 14
                        color: HKS.muted
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Keyboard"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                    }

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: soonText.implicitWidth + 8
                        height: 16
                        radius: 4
                        color: HKS.elevated

                        Text {
                            id: soonText
                            anchors.centerIn: parent
                            text: "soon"
                            font.family: HKS.fontFamily
                            font.pixelSize: 9
                            color: HKS.muted
                        }
                    }
                }
            }
        }

        // Category Chips
        CategoryChips {
            width: parent.width
            categories: KeybindData.categories
            totalCount: KeybindData.binds.length
            selectedCategory: root.selectedCategory
            onCategorySelected: function(cat) {
                root.selectedCategory = cat;
            }
        }

        // Submap note or selector + Results header count
        Item {
            width: parent.width
            height: 22

            // Left: Submap selector or note
            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: KeybindData.submaps.length > 0 ? "Submap:" : "No submaps in this config"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: HKS.muted
                }

                // Submap chips if present
                Repeater {
                    model: KeybindData.submaps.length > 0 ? ["All"].concat(KeybindData.submaps) : []
                    delegate: Rectangle {
                        height: 20
                        width: subTxt.implicitWidth + 10
                        radius: 4
                        color: root.selectedSubmap === modelData ? HKS.accent : HKS.surface
                        border.width: 1
                        border.color: HKS.alpha(HKS.muted, 0.25)

                        Text {
                            id: subTxt
                            anchors.centerIn: parent
                            text: modelData
                            font.family: HKS.fontFamily
                            font.pixelSize: 10
                            color: root.selectedSubmap === modelData ? HKS.bg : HKS.fg
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.selectedSubmap = modelData
                        }
                    }
                }
            }

            // Right: Results count "N of M keybindings"
            Text {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: root.filteredBinds.length + " of " + KeybindData.binds.length + " keybindings"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.muted
            }
        }

        // Main List Area
        Item {
            width: parent.width
            height: parent.height - y

            // Loading state
            Item {
                anchors.fill: parent
                visible: KeybindData.loading

                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: ""
                        font.family: HKS.fontFamily
                        font.pixelSize: 32
                        color: HKS.accent
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Scanning keybindings..."
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        color: HKS.muted
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
                visible: !KeybindData.loading && !KeybindData.error && root.filteredBinds.length === 0
                icon: ""
                title: "No keybindings match your search"
                message: "Try searching for another key, description, or action."
                buttonText: root.searchText ? "Clear Search" : ""
                onButtonClicked: {
                    searchField.text = "";
                    root.searchText = "";
                    root.selectedCategory = "All";
                }
            }

            // Virtualized ListView
            ListView {
                id: listView
                anchors.fill: parent
                anchors.topMargin: 8
                visible: !KeybindData.loading && !KeybindData.error && root.filteredBinds.length > 0
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
    }
}
