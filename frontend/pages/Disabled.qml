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
                    text: ""
                    font.family: Deck.fontFamily
                    font.pixelSize: 20
                    color: Deck.accent
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Disabled Keybindings"
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
                        text: root.count + " disabled"
                        font.family: Deck.fontFamily
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        color: Deck.accent
                    }
                }
            }
        }

        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Keybindings disabled with Deck. Click 'Enable' to restore any keybinding to your active configuration."
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

            // Empty State
            EmptyState {
                anchors.fill: parent
                visible: root.count === 0
                icon: ""
                title: "No disabled keybindings"
                message: "Keybindings disabled via Keybind Studio will appear here so you can re-enable them at any time."
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
                        spacing: 10

                        // Top Row: Shortcut hint + Description + Source + Enable button (wrapping Flow)
                        Flow {
                            width: parent.width
                            spacing: 10

                            ShortcutKeys {
                                width: Math.min(implicitWidth, parent.width)
                                wrap: true
                                parts: KeybindData.parseShortcutString(modelData.key_hint)
                            }

                            Text {
                                objectName: "elideOk"
                                text: modelData.description_hint || "Disabled keybinding"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                font.weight: Font.DemiBold
                                color: Deck.fg
                                elide: Text.ElideRight
                                width: Math.min(implicitWidth, Math.min(260, parent.width))
                            }

                            Text {
                                objectName: "elideOk"
                                text: root.formatSource(modelData.file, modelData.line)
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: Deck.muted
                                elide: Text.ElideLeft
                                width: Math.min(implicitWidth, parent.width)
                            }

                            ActionButton {
                                variant: "accent"
                                iconText: ""
                                text: "Enable"
                                onClicked: EditService.requestUncomment(modelData)
                            }
                        }

                        // Code Snippet Box
                        Rectangle {
                            width: parent.width
                            height: rawTxt.implicitHeight + 12
                            radius: 4
                            color: Deck.alpha(Deck.elevated, 0.7)
                            border.width: 1
                            border.color: Deck.alpha(Deck.muted, 0.15)

                            Text {
                                id: rawTxt
                                objectName: "elideOk"
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                text: modelData.original_text || ""
                                font.family: Deck.fontFamily
                                font.pixelSize: 11
                                color: Deck.alpha(Deck.muted, 0.9)
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }
    }
}
