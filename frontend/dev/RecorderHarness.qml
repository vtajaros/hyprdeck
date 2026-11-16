import QtQuick
import Quickshell
import "../theme"
import "../services"
import "../components"

FloatingWindow {
    id: win

    title: "HKS Keybind Recorder Harness"
    implicitWidth: 640
    implicitHeight: 480
    color: Deck.bg

    property int lastModmask: 0
    property string lastKey: ""
    property string lastDisplay: "None"
    property string lastEventStatus: "Ready"

    Component.onCompleted: {
        RecorderService.heal();
    }

    Rectangle {
        anchors.fill: parent
        color: Deck.bg

        Column {
            anchors.centerIn: parent
            spacing: 20
            width: Math.min(parent.width - 48, 520)

            // Header
            Column {
                spacing: 4
                anchors.horizontalCenter: parent.horizontalCenter

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "HKS Recorder Test Harness"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeLarge
                    font.weight: Font.Bold
                    color: Deck.fg
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Dev testing for live submap interception & key translation"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.muted
                }
            }

            // Results Card
            Rectangle {
                width: parent.width
                height: 160
                radius: Deck.radius
                color: Deck.surface
                border.width: 1
                border.color: Deck.border

                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    width: parent.width - 32

                    Row {
                        spacing: 8
                        anchors.horizontalCenter: parent.horizontalCenter

                        Text {
                            text: "Status:"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.muted
                        }
                        Text {
                            text: win.lastEventStatus
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            font.weight: Font.DemiBold
                            color: win.lastEventStatus === "Accepted" ? Deck.accent : Deck.fg
                        }
                    }

                    // Keycap visual preview
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: win.lastDisplay !== "None"
                        spacing: 6

                        ShortcutKeys {
                            parts: win.lastDisplay
                        }
                    }

                    // Numeric details
                    Column {
                        spacing: 4
                        anchors.horizontalCenter: parent.horizontalCenter

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "Modmask: " + win.lastModmask + " (0x" + win.lastModmask.toString(16) + ") | Key: \"" + win.lastKey + "\""
                            font.family: Deck.fontFamily
                            font.pixelSize: 11
                            color: Deck.muted
                        }

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "Display String: " + win.lastDisplay
                            font.family: Deck.fontFamily
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            color: Deck.fg
                        }
                    }
                }
            }

            // Actions Row
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12

                // Record Button
                Rectangle {
                    width: recordBtnText.implicitWidth + 28
                    height: 38
                    radius: 6
                    color: Deck.accent

                    Text {
                        id: recordBtnText
                        anchors.centerIn: parent
                        text: "  Record Keybinding"
                        font.family: Deck.fontFamily
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        color: "#ffffff"
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            recorder.openRecorder();
                        }
                    }
                }

                // Force Heal Submap Button
                Rectangle {
                    width: healBtnText.implicitWidth + 24
                    height: 38
                    radius: 6
                    color: Deck.surface
                    border.width: 1
                    border.color: Deck.border

                    Text {
                        id: healBtnText
                        anchors.centerIn: parent
                        text: "Reset Submap (Heal)"
                        font.family: Deck.fontFamily
                        font.pixelSize: 12
                        color: Deck.fg
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            RecorderService.heal(function(res) {
                                win.lastEventStatus = "Healed (" + ((res && res.message) ? res.message : "ok") + ")";
                            });
                        }
                    }
                }
            }
        }

        KeybindRecorder {
            id: recorder

            onAccepted: (modmask, key, display) => {
                win.lastModmask = modmask;
                win.lastKey = key;
                win.lastDisplay = display;
                win.lastEventStatus = "Accepted";
            }

            onCancelled: () => {
                win.lastEventStatus = "Cancelled";
            }
        }
    }
}
