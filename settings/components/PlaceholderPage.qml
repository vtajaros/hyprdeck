import QtQuick
import "../theme"

Item {
    id: root

    property string title: ""
    property string icon: ""
    property string summary: "Planned for a future milestone."

    Column {
        anchors.centerIn: parent
        spacing: Deck.space12
        width: 420

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.icon
            font.family: Deck.fontFamily
            font.pixelSize: 36
            color: Deck.muted
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.title
            font.family: Deck.fontFamily
            font.pixelSize: Deck.fontSizeTitle
            font.weight: Font.Bold
            color: Deck.fg
        }

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: soonTxt.implicitWidth + 16
            height: 22
            radius: 6
            color: Deck.elevated
            border.width: 1
            border.color: Deck.alpha(Deck.muted, 0.25)
            Text {
                id: soonTxt
                anchors.centerIn: parent
                text: "Coming soon"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
            }
        }

        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: root.summary
            font.family: Deck.fontFamily
            font.pixelSize: Deck.fontSizeSmall
            color: Deck.muted
            wrapMode: Text.WordWrap
        }
    }
}
