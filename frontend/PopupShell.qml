import QtQuick
import Quickshell
import Quickshell.Wayland
import "theme"
import "services"
import "components"
import "pages"
import "../theme"

Item {
    id: root

    property bool appeared: false
    property bool isClosing: false
    property int debugOverrideWidth: 0
    property int debugOverrideHeight: 0
    property int lastGrabSeq: 0
    property string lastGrabStatus: ""
    property alias rootSurfaceRef: card
    property alias popupListRef: popupList

    function activeAuditTarget() {
        return card;
    }

    readonly property int popupLeft: {
        var raw = Deck.env("POPUP_LEFT");
        if (!raw || raw.trim() === "") return 20;
        var val = parseInt(raw, 10);
        return isNaN(val) ? 20 : val;
    }

    readonly property int popupTop: {
        var raw = Deck.env("POPUP_TOP");
        if (!raw || raw.trim() === "") return 64;
        var val = parseInt(raw, 10);
        return isNaN(val) ? 64 : val;
    }

    Component.onCompleted: {
        appeared = true;
        RecorderService.heal();
    }

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

    // Full-screen invisible click-catcher window
    PanelWindow {
        id: popupWindow

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

        // Invisible full-screen click-catcher scrim: closes on click outside card
        Rectangle {
            anchors.fill: parent
            color: "transparent"

            focus: true
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) {
                    root.dismiss("key_escape");
                    event.accepted = true;
                }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: root.dismiss("outside_click")
            }
        }

        // Top-left anchored ~760x560 popup card with clear opaque boundary & slide-in
        Rectangle {
            id: card
            x: root.popupLeft
            y: root.popupTop + (root.appeared ? 0 : -8)
            width: root.debugOverrideWidth > 0 ? root.debugOverrideWidth : (parent.width > 0 ? Math.min(parent.width - root.popupLeft - 20, 760) : 760)
            height: root.debugOverrideHeight > 0 ? root.debugOverrideHeight : (parent.height > 0 ? Math.min(parent.height - root.popupTop - 20, 560) : 560)
            radius: 10
            color: Deck.bg
            border.width: 1
            border.color: Deck.borderColor

            opacity: root.appeared ? 1.0 : 0.0

            Behavior on opacity {
                NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
            }
            Behavior on y {
                NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
            }

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
                    radius: 10
                    color: Deck.surface

                    // Square off bottom corners so only top corners of the header are rounded
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 10
                        color: Deck.surface
                    }

                    // Bottom border
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: Deck.alpha(Deck.muted, 0.2)
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: Deck.space16
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: ""
                            font.family: Deck.fontFamily
                            font.pixelSize: 15
                            color: Deck.accent
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: AppInfo.windowTitle
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSize
                            font.weight: Font.Bold
                            color: Deck.fg
                        }

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: modeBadge.implicitWidth + 8
                            height: 16
                            radius: 4
                            color: Deck.alpha(Deck.accent, 0.15)

                            Text {
                                id: modeBadge
                                anchors.centerIn: parent
                                text: "popup"
                                font.family: Deck.fontFamily
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                                color: Deck.accent
                            }
                        }
                    }
                }

                // Shared List Content
                AllKeybindings {
                    id: popupList
                    width: parent.width
                    height: parent.height - 44
                    onRequestClose: root.dismiss("key_escape")
                }
            }
        }


    }
}
