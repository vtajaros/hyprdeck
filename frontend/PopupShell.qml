import QtQuick
import Quickshell
import Quickshell.Wayland
import "theme"
import "services"
import "components"
import "pages"

Item {
    id: root

    property bool isClosing: false

    function dismiss(reason) {
        if (isClosing) return;
        isClosing = true;
        closeTimer.start();
    }

    Timer {
        id: closeTimer
        interval: 100
        onTriggered: Qt.quit()
    }

    // 1. Dimmed background scrim window
    PanelWindow {
        id: bgWindow

        anchors {
            top: true
            bottom: true
            left: true
            right: true
        }

        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "hks-backdrop"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

        color: "#b8090b0e"
        visible: !root.isClosing

        MouseArea {
            anchors.fill: parent
            onClicked: root.dismiss("bg_click")
        }
    }

    // 2. Foreground centered card window
    PanelWindow {
        id: fgWindow

        anchors {
            top: true
            bottom: true
            left: true
            right: true
        }

        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "hks-popup"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

        color: "transparent"
        visible: !root.isClosing

        // Dismiss on clicking outside the card
        MouseArea {
            anchors.fill: parent
            z: -1
            onClicked: root.dismiss("outside_click")
        }

        Rectangle {
            id: card
            anchors.centerIn: parent
            width: Math.min(parent.width - 40, 760)
            height: Math.min(parent.height - 40, 560)
            radius: HKS.radius
            color: HKS.bg
            border.width: 1
            border.color: HKS.alpha(HKS.accent, 0.45)

            // Prevent clicks inside card from dismissing
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.AllButtons
            }

            Column {
                anchors.fill: parent

                // Header bar
                Rectangle {
                    width: parent.width
                    height: 44
                    radius: HKS.radius
                    color: HKS.surface

                    // Bottom border
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: HKS.alpha(HKS.muted, 0.2)
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: HKS.space16
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: ""
                            font.family: HKS.fontFamily
                            font.pixelSize: 15
                            color: HKS.accent
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Hyprland Keybind Studio"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.Bold
                            color: HKS.fg
                        }

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: modeBadge.implicitWidth + 8
                            height: 16
                            radius: 4
                            color: HKS.alpha(HKS.accent, 0.15)

                            Text {
                                id: modeBadge
                                anchors.centerIn: parent
                                text: "popup"
                                font.family: HKS.fontFamily
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                                color: HKS.accent
                            }
                        }
                    }

                    // Close Button
                    Rectangle {
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        width: 24
                        height: 24
                        radius: 12
                        color: closeMouse.containsMouse ? HKS.elevated : "transparent"

                        Text {
                            anchors.centerIn: parent
                            text: ""
                            font.family: HKS.fontFamily
                            font.pixelSize: 12
                            color: closeMouse.containsMouse ? HKS.fg : HKS.muted
                        }

                        MouseArea {
                            id: closeMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.dismiss("close_button")
                        }
                    }
                }

                // Shared List Content
                AllKeybindings {
                    width: parent.width
                    height: parent.height - 44
                    onRequestClose: root.dismiss("key_escape")
                }
            }
        }
    }
}
