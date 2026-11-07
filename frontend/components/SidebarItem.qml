import QtQuick
import "../theme"

Rectangle {
    id: root

    property string icon: ""
    property string text: ""
    property string badge: ""
    property bool active: false
    property bool disabled: false
    signal clicked()

    implicitWidth: 180
    implicitHeight: 36
    radius: 6
    color: active
        ? HKS.alpha(HKS.accent, 0.18)
        : (mouseArea.containsMouse && !disabled ? HKS.alpha(HKS.elevated, 0.6) : "transparent")
    border.width: active ? 1 : 0
    border.color: active ? HKS.alpha(HKS.accent, 0.5) : "transparent"

    opacity: disabled ? 0.45 : 1.0

    Row {
        id: row
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.icon
            font.family: HKS.fontFamily
            font.pixelSize: 14
            color: root.active ? HKS.accent : (root.disabled ? HKS.muted : HKS.fg)
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.text
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeSmall
            font.weight: root.active ? Font.DemiBold : Font.Normal
            color: root.active ? HKS.accent : (root.disabled ? HKS.muted : HKS.fg)
        }
    }

    // Optional right-aligned badge
    Rectangle {
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        visible: root.badge.length > 0
        width: badgeText.implicitWidth + 8
        height: 16
        radius: 4
        color: root.disabled ? HKS.alpha(HKS.muted, 0.2) : HKS.elevated

        Text {
            id: badgeText
            anchors.centerIn: parent
            text: root.badge
            font.family: HKS.fontFamily
            font.pixelSize: 9
            font.weight: Font.DemiBold
            color: root.disabled ? HKS.muted : HKS.accent
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: !root.disabled
        cursorShape: root.disabled ? Qt.ArrowCursor : Qt.PointingHandCursor
        onClicked: {
            if (!root.disabled) {
                root.clicked();
            }
        }
    }
}
