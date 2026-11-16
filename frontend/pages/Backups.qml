import QtQuick
import QtQuick.Controls.Basic
import Quickshell
import "../theme"
import "../services"
import "../components"

Item {
    id: root

    Component.onCompleted: {
        EditService.loadBackups();
    }

    function formatSource(file) {
        if (!file) return "-";
        var path = String(file);
        var home = Quickshell.env("HOME") || "";
        if (home && path.startsWith(home)) {
            path = "~" + path.slice(home.length);
        }
        return path;
    }

    readonly property int count: EditService.backups ? EditService.backups.length : 0

    focus: true

    Keys.onPressed: function(event) {
        if (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_R) {
            EditService.loadBackups();
            event.accepted = true;
            return;
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: Deck.space24
        spacing: Deck.space16

        // Page Header
        Item {
            width: parent.width
            height: 36

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: ""
                    font.family: Deck.fontFamily
                    font.pixelSize: 20
                    color: Deck.accent
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Backups & History"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeLarge
                    font.weight: Font.Bold
                    color: Deck.fg
                }

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    height: 22
                    width: countTxt.implicitWidth + 14
                    radius: 11
                    color: Deck.alpha(Deck.accent, 0.15)
                    border.width: 1
                    border.color: Deck.alpha(Deck.accent, 0.3)

                    Text {
                        id: countTxt
                        anchors.centerIn: parent
                        text: root.count + " snapshots"
                        font.family: Deck.fontFamily
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        color: Deck.accent
                    }
                }
            }

            // Refresh Button
            ActionButton {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                variant: "neutral"
                iconText: ""
                text: "Refresh"
                onClicked: EditService.loadBackups()
            }
        }

        Text {
            text: "Automatic snapshots saved to ~/.local/share/hks/backups before modifications. Click 'Restore' to preview and rollback."
            font.family: Deck.fontFamily
            font.pixelSize: Deck.fontSizeSmall
            color: Deck.muted
        }

        Rectangle {
            width: parent.width
            height: 1
            color: Deck.alpha(Deck.muted, 0.15)
        }

        // Main List Area
        Item {
            width: parent.width
            height: parent.height - y

            // Loading state
            Item {
                anchors.fill: parent
                visible: EditService.loadingBackups

                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 28
                        color: Deck.accent
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Loading backups..."
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSize
                        color: Deck.muted
                    }
                }
            }

            // Empty State
            EmptyState {
                anchors.fill: parent
                visible: !EditService.loadingBackups && root.count === 0
                icon: ""
                title: "No backups recorded"
                message: "Backups created before editing your configuration will appear here."
            }

            // List of Backups
            ListView {
                id: listView
                anchors.fill: parent
                visible: !EditService.loadingBackups && root.count > 0
                model: EditService.backups
                spacing: 10
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                ScrollBar.vertical: ScrollBar {
                    active: true
                    width: 6
                }

                delegate: Rectangle {
                    id: card
                    width: listView.width - (listView.ScrollBar.vertical.visible ? 10 : 0)
                    height: cardCol.implicitHeight + 24
                    radius: Deck.radiusSmall
                    color: Deck.alpha(Deck.surface, 0.7)
                    border.width: 1
                    border.color: Deck.alpha(Deck.muted, 0.2)

                    Column {
                        id: cardCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 12
                        spacing: 8

                        // Top Row: Timestamp + Short SHA + Restore Button
                        Item {
                            width: parent.width
                            height: 30

                            Row {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 10

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: ""
                                    font.family: Deck.fontFamily
                                    font.pixelSize: 12
                                    color: Deck.muted
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.created_at || "-"
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    font.weight: Font.DemiBold
                                    color: Deck.fg
                                }

                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    height: 20
                                    width: shaTxt.implicitWidth + 10
                                    radius: 3
                                    color: Deck.alpha(Deck.muted, 0.15)
                                    border.width: 1
                                    border.color: Deck.alpha(Deck.muted, 0.25)

                                    Text {
                                        id: shaTxt
                                        anchors.centerIn: parent
                                        text: (modelData.sha256 ? modelData.sha256.slice(0, 12) : "-")
                                        font.family: Deck.fontFamily
                                        font.pixelSize: 10
                                        color: Deck.muted
                                    }
                                }
                            }

                            // Restore Action Button
                            ActionButton {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                variant: "accent"
                                iconText: ""
                                text: "Restore"
                                onClicked: EditService.requestRestore(modelData.id)
                            }
                        }

                        // Bottom Row: Details path & ID
                        Row {
                            spacing: 16

                            Row {
                                spacing: 6
                                Text { text: "File:"; font.family: Deck.fontFamily; font.pixelSize: 10; color: Deck.muted; font.weight: Font.Bold }
                                Text { text: root.formatSource(modelData.original_path); font.family: Deck.fontFamily; font.pixelSize: 10; color: Deck.fg }
                            }

                            Row {
                                spacing: 6
                                Text { text: "ID:"; font.family: Deck.fontFamily; font.pixelSize: 10; color: Deck.muted; font.weight: Font.Bold }
                                Text { text: modelData.id || "-"; font.family: Deck.fontFamily; font.pixelSize: 10; color: Deck.muted }
                            }
                        }
                    }
                }
            }
        }
    }
}
