import QtQuick
import "../theme"

Flow {
    id: root

    property string layoutClass: "expanded"
    property bool layoutShort: false

    width: parent ? parent.width : implicitWidth
    spacing: Deck.scaledSpace(Deck.space8, root.layoutClass, root.layoutShort)
}
