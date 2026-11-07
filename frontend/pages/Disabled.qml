import QtQuick
import QtQuick.Controls.Basic
import Quickshell
import "../theme"
import "../services"
import "../components"

Item {
    id: root

    readonly property int count: KeybindData.disabledBinds ? KeybindData.disabledBinds.length : 0

    function formatSource(file, line) {
        if (!file) return "-";
        var path = String(file);
        var home = Quickshell.env("HOME") || "";
        if (home && path.startsWith(home)) {
            path = "~" + path.slice(home.length);
        }
        if (line !== undefined && line !== null) {
            path += ":" + line;
        }
        return path;
    }

    focus: true

    Keys.onPressed: function(event) {
        if (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_R) {
            KeybindData.reload();
            event.accepted = true;
            return;
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: HKS.space24
        spacing: HKS.space16

        // Page Header
        Row {
            width: parent.width
            height: 36

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: ""
                    font.family: HKS.fontFamily
                    font.pixelSize: 20
                    color: HKS.accent
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Disabled Keybindings"
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
                        text: root.count + " disabled"
                        font.family: HKS.fontFamily
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        color: HKS.accent
                    }
                }
            }
        }

        Text {
            text: "Keybindings disabled with HKS. Click 'Enable' to restore any keybinding to your active configuration."
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

            // Empty State
            EmptyState {
                anchors.fill: parent
                visible: root.count === 0
                icon: ""
                title: "No disabled keybindings"
                message: "Keybindings disabled via HKS will appear here so you can re-enable them at any time."
            }

            // List of Disabled Binds
            ListView {
                id: listView
                anchors.fill: parent
                visible: root.count > 0
                model: KeybindData.disabledBinds
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
                        spacing: 10

                        // Top Row: Key hint + Description hint + Source + Enable Button
                        Item {
                            width: parent.width
                            height: 30

                            Row {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 10

                                // Key Hint Badge
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    height: 24
                                    width: keyHintTxt.implicitWidth + 14
                                    radius: 4
                                    color: HKS.alpha(HKS.accent, 0.15)
                                    border.width: 1
                                    border.color: HKS.alpha(HKS.accent, 0.35)

                                    Text {
                                        id: keyHintTxt
                                        anchors.centerIn: parent
                                        text: modelData.key_hint || "disabled"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        font.weight: Font.Bold
                                        color: HKS.accent
                                    }
                                }

                                // Description Hint
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.description_hint || "Disabled keybinding"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    font.weight: Font.DemiBold
                                    color: HKS.fg
                                    elide: Text.ElideRight
                                    width: Math.min(implicitWidth, 260)
                                }

                                // Source Path
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: root.formatSource(modelData.file, modelData.line)
                                    font.family: HKS.fontFamily
                                    font.pixelSize: 10
                                    color: HKS.muted
                                }
                            }

                            // Enable Action Button
                            Rectangle {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                height: 28
                                width: enableTxt.implicitWidth + 24
                                radius: 6
                                color: enableMa.containsMouse ? HKS.alpha(HKS.accent, 0.25) : HKS.alpha(HKS.accent, 0.12)
                                border.width: 1
                                border.color: HKS.alpha(HKS.accent, 0.4)

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 6

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: ""
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 12
                                        color: HKS.accent
                                    }

                                    Text {
                                        id: enableTxt
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Enable"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        font.weight: Font.DemiBold
                                        color: HKS.accent
                                    }
                                }

                                MouseArea {
                                    id: enableMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        EditService.requestUncomment(modelData);
                                    }
                                }
                            }
                        }

                        // Code Snippet Box
                        Rectangle {
                            width: parent.width
                            height: rawTxt.implicitHeight + 12
                            radius: 4
                            color: HKS.alpha(HKS.elevated, 0.7)
                            border.width: 1
                            border.color: HKS.alpha(HKS.muted, 0.15)

                            Text {
                                id: rawTxt
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                text: modelData.original_text || ""
                                font.family: HKS.fontFamily
                                font.pixelSize: 11
                                color: HKS.alpha(HKS.muted, 0.9)
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }
    }
}
