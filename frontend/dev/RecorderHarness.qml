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
    color: HKS.bg

    property int lastModmask: 0
    property string lastKey: ""
    property string lastDisplay: "None"
    property string lastEventStatus: "Ready"

    Component.onCompleted: {
        RecorderService.heal();
    }

    Rectangle {
        anchors.fill: parent
        color: HKS.bg

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
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeLarge
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Dev testing for live submap interception & key translation"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: HKS.muted
                }
            }

            // Results Card
            Rectangle {
                width: parent.width
                height: 160
                radius: HKS.radius
                color: HKS.surface
                border.width: 1
                border.color: HKS.border

                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    width: parent.width - 32

                    Row {
                        spacing: 8
                        anchors.horizontalCenter: parent.horizontalCenter

                        Text {
                            text: "Status:"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                        }
                        Text {
                            text: win.lastEventStatus
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            font.weight: Font.DemiBold
                            color: win.lastEventStatus === "Accepted" ? HKS.accent : HKS.fg
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
                            font.family: HKS.fontFamily
                            font.pixelSize: 11
                            color: HKS.muted
                        }

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "Display String: " + win.lastDisplay
                            font.family: HKS.fontFamily
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            color: HKS.fg
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
                    color: HKS.accent

                    Text {
                        id: recordBtnText
                        anchors.centerIn: parent
                        text: "  Record Keybinding"
                        font.family: HKS.fontFamily
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
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.border

                    Text {
                        id: healBtnText
                        anchors.centerIn: parent
                        text: "Reset Submap (Heal)"
                        font.family: HKS.fontFamily
                        font.pixelSize: 12
                        color: HKS.fg
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
