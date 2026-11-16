import QtQuick
import Quickshell
import "../theme"
import "../pages" as HksPages

FloatingWindow {
    id: cardWin

    title: "HyprDeck Card Harness"
    implicitWidth: 760
    implicitHeight: 560
    color: Deck.bg
    visible: Deck.env("START_HIDDEN") !== "1"

    property int debugOverrideWidth: 0
    property int debugOverrideHeight: 0
    property int lastGrabSeq: 0
    property string lastGrabStatus: ""
    property alias rootSurfaceRef: cardSurface
    property alias cardAllRef: cardAll

    function activeAuditTarget() {
        return cardAll;
    }

    Rectangle {
        id: cardSurface
        width: cardWin.debugOverrideWidth > 0 ? cardWin.debugOverrideWidth : 760
        height: cardWin.debugOverrideHeight > 0 ? cardWin.debugOverrideHeight : 560
        color: Deck.bg

        Column {
            anchors.fill: parent

            Rectangle {
                width: parent.width
                height: 44
                color: Deck.surface

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Deck.alpha(Deck.muted, 0.2)
                }

                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "\uf11c"
                        font.family: Deck.fontFamily
                        font.pixelSize: 15
                        color: Deck.accent
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Hyprland Keybind Studio"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSize
                        font.weight: Font.Bold
                        color: Deck.fg
                    }
                }
            }

            HksPages.AllKeybindings {
                id: cardAll
                width: parent.width
                height: parent.height - 44
                onRequestClose: {}
            }
        }
    }
}
