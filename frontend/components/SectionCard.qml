import QtQuick
import "../theme"

Rectangle {
    id: root

    property string title: ""
    property string subtitle: ""
    property bool highlighted: false
    property real cardPadding: Deck.space12
    property alias spacing: innerCol.spacing
    default property alias content: innerCol.data

    implicitHeight: innerCol.implicitHeight + (root.cardPadding * 2)
    height: implicitHeight
    radius: Deck.radiusMedium
    color: Deck.surface
    border.width: 1
    border.color: root.highlighted ? Deck.accent : Deck.alpha(Deck.muted, 0.18)

    Column {
        id: innerCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: root.cardPadding
        spacing: Deck.space8

        Text {
            visible: root.title.length > 0
            text: root.title
            font.family: Deck.fontFamily
            font.pixelSize: Deck.fontSize
            font.weight: Font.DemiBold
            color: Deck.fg
        }

        Text {
            visible: root.subtitle.length > 0
            width: parent.width
            text: root.subtitle
            font.family: Deck.fontFamily
            font.pixelSize: Deck.fontSizeSmall
            color: Deck.muted
            wrapMode: Text.WordWrap
        }
    }
}
