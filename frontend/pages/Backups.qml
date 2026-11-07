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
        anchors.margins: HKS.space24
        spacing: HKS.space16

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
                    font.family: HKS.fontFamily
                    font.pixelSize: 20
                    color: HKS.accent
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Backups & History"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeLarge
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    height: 22
                    width: countTxt.implicitWidth + 14
                    radius: 11
                    color: HKS.alpha(HKS.accent, 0.15)
                    border.width: 1
                    border.color: HKS.alpha(HKS.accent, 0.3)

                    Text {
                        id: countTxt
                        anchors.centerIn: parent
                        text: root.count + " snapshots"
                        font.family: HKS.fontFamily
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        color: HKS.accent
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
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeSmall
            color: HKS.muted
        }

        Rectangle {
            width: parent.width
            height: 1
            color: HKS.alpha(HKS.muted, 0.15)
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
                        font.family: HKS.fontFamily
                        font.pixelSize: 28
                        color: HKS.accent
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Loading backups..."
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        color: HKS.muted
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
                    radius: HKS.radiusSmall
                    color: HKS.alpha(HKS.surface, 0.7)
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.2)

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
                                    font.family: HKS.fontFamily
                                    font.pixelSize: 12
                                    color: HKS.muted
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.created_at || "-"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    font.weight: Font.DemiBold
                                    color: HKS.fg
                                }

                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    height: 20
                                    width: shaTxt.implicitWidth + 10
                                    radius: 3
                                    color: HKS.alpha(HKS.muted, 0.15)
                                    border.width: 1
                                    border.color: HKS.alpha(HKS.muted, 0.25)

                                    Text {
                                        id: shaTxt
                                        anchors.centerIn: parent
                                        text: (modelData.sha256 ? modelData.sha256.slice(0, 12) : "-")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 10
                                        color: HKS.muted
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
                                Text { text: "File:"; font.family: HKS.fontFamily; font.pixelSize: 10; color: HKS.muted; font.weight: Font.Bold }
                                Text { text: root.formatSource(modelData.original_path); font.family: HKS.fontFamily; font.pixelSize: 10; color: HKS.fg }
                            }

                            Row {
                                spacing: 6
                                Text { text: "ID:"; font.family: HKS.fontFamily; font.pixelSize: 10; color: HKS.muted; font.weight: Font.Bold }
                                Text { text: modelData.id || "-"; font.family: HKS.fontFamily; font.pixelSize: 10; color: HKS.muted }
                            }
                        }
                    }
                }
            }
        }
    }
}
