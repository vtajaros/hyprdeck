import QtQuick
import "../theme"

Rectangle {
    id: root

    property alias text: input.text
    property string placeholder: "Search keybindings (e.g. 'super enter', 'workspace', 'kitty')..."
    signal cleared()

    function forceFocus() {
        input.forceActiveFocus();
    }

    implicitWidth: 320
    implicitHeight: 38
    radius: Deck.radiusSmall
    color: Deck.surface
    border.width: 1
    border.color: input.activeFocus ? Deck.accent : Deck.alpha(Deck.muted, 0.25)

    Behavior on border.color {
        ColorAnimation { duration: 120 }
    }

    Row {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 10
        spacing: 8

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: ""
            font.family: Deck.fontFamily
            font.pixelSize: 13
            color: input.activeFocus ? Deck.accent : Deck.muted
        }

        Item {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(50, row.width - 24 - (clearBtn.visible ? 28 : 0))
            height: parent.height

            TextInput {
                id: input
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                color: Deck.fg
                selectByMouse: true
                selectionColor: Deck.alpha(Deck.accent, 0.35)
                selectedTextColor: Deck.fg
                clip: true

                Text {
                    objectName: "elideOk"
                    anchors.fill: parent
                    text: root.placeholder
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSize
                    color: Deck.alpha(Deck.muted, 0.6)
                    elide: Text.ElideRight
                    visible: !input.text && !input.inputMethodComposing
                }
            }
        }

        Rectangle {
            id: clearBtn
            anchors.verticalCenter: parent.verticalCenter
            width: 20
            height: 20
            radius: 10
            visible: input.text.length > 0
            color: clearMouse.containsMouse ? Deck.elevated : "transparent"

            Text {
                anchors.centerIn: parent
                text: ""
                font.family: Deck.fontFamily
                font.pixelSize: 11
                color: Deck.muted
            }

            MouseArea {
                id: clearMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    input.text = "";
                    root.cleared();
                    input.forceActiveFocus();
                }
            }
        }
    }
}
