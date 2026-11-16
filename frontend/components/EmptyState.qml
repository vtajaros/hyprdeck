import QtQuick
import "../theme"

Item {
    id: root

    property string icon: ""
    property string title: "No keybindings found"
    property string message: "Try adjusting your search terms or selecting another category."
    property string buttonText: ""
    signal buttonClicked()

    implicitWidth: 400
    implicitHeight: 200

    Column {
        anchors.centerIn: parent
        spacing: 12
        width: Math.min(parent.width - 40, 420)

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.icon
            font.family: Deck.fontFamily
            font.pixelSize: 36
            color: Deck.alpha(Deck.muted, 0.4)
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.title
            font.family: Deck.fontFamily
            font.pixelSize: Deck.fontSizeLarge
            font.weight: Font.Bold
            color: Deck.fg
            horizontalAlignment: Text.AlignHCenter
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            text: root.message
            font.family: Deck.fontFamily
            font.pixelSize: Deck.fontSize
            color: Deck.muted
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.buttonText.length > 0
            width: btnText.implicitWidth + 24
            height: 32
            radius: 6
            color: btnMouse.containsMouse ? Deck.elevated : Deck.surface
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.5)

            Text {
                id: btnText
                anchors.centerIn: parent
                text: root.buttonText
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                font.weight: Font.DemiBold
                color: Deck.accent
            }

            MouseArea {
                id: btnMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.buttonClicked()
            }
        }
    }
}
