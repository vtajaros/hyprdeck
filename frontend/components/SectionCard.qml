import QtQuick
import "../theme"

Rectangle {
    id: root

    property string title: ""
    property string subtitle: ""
    property bool highlighted: false
    property real cardPadding: HKS.space12
    property alias spacing: innerCol.spacing
    default property alias content: innerCol.data

    implicitHeight: innerCol.implicitHeight + (root.cardPadding * 2)
    height: implicitHeight
    radius: HKS.radiusMedium
    color: HKS.surface
    border.width: 1
    border.color: root.highlighted ? HKS.accent : HKS.alpha(HKS.muted, 0.18)

    Column {
        id: innerCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: root.cardPadding
        spacing: HKS.space8

        Text {
            visible: root.title.length > 0
            text: root.title
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSize
            font.weight: Font.DemiBold
            color: HKS.fg
        }

        Text {
            visible: root.subtitle.length > 0
            width: parent.width
            text: root.subtitle
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeSmall
            color: HKS.muted
            wrapMode: Text.WordWrap
        }
    }
}
