import QtQuick
import "../theme"

Rectangle {
    id: root

    property string icon: ""
    property string text: ""
    property string badge: ""
    property bool active: false
    property bool disabled: false
    property bool compactRail: false
    property bool showRailTooltip: true
    readonly property bool itemHovered: mouseArea.containsMouse && !root.disabled
    signal clicked()
    signal railHoverState(bool hovered, string label, Item sourceItem)

    onItemHoveredChanged: root.railHoverState(root.itemHovered, root.text, root)

    implicitWidth: compactRail ? 40 : 180
    implicitHeight: 36
    radius: 6
    color: active
        ? HKS.alpha(HKS.accent, 0.18)
        : (mouseArea.containsMouse && !disabled ? HKS.alpha(HKS.elevated, 0.6) : "transparent")
    border.width: active ? 1 : 0
    border.color: active ? HKS.alpha(HKS.accent, 0.5) : "transparent"

    opacity: disabled ? 0.45 : 1.0

    Text {
        id: iconTxt
        x: root.compactRail ? Math.round((parent.width - width) / 2) : 12
        anchors.verticalCenter: parent.verticalCenter
        text: root.icon
        font.family: HKS.fontFamily
        font.pixelSize: 14
        color: root.active ? HKS.accent : (root.disabled ? HKS.muted : HKS.fg)
    }

    Text {
        id: labelTxt
        objectName: "elideOk"
        visible: !root.compactRail
        x: iconTxt.x + iconTxt.width + 10
        width: Math.max(0, (badgeBox.visible ? badgeBox.x - 8 : parent.width - 10) - x)
        anchors.verticalCenter: parent.verticalCenter
        text: root.text
        font.family: HKS.fontFamily
        font.pixelSize: HKS.fontSizeSmall
        font.weight: root.active ? Font.DemiBold : Font.Normal
        color: root.active ? HKS.accent : (root.disabled ? HKS.muted : HKS.fg)
        elide: Text.ElideRight
    }

    // Optional right-aligned badge (or corner indicator dot in compactRail mode)
    Rectangle {
        id: badgeBox
        x: parent.width - width - 10
        anchors.verticalCenter: parent.verticalCenter
        visible: !root.compactRail && root.badge.length > 0
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

    Rectangle {
        visible: root.compactRail && root.badge.length > 0
        width: 7
        height: 7
        radius: 3.5
        anchors.right: parent.right
        anchors.rightMargin: 6
        anchors.top: parent.top
        anchors.topMargin: 6
        color: root.disabled ? HKS.muted : HKS.accent
    }

    // Floating tooltip when used in compactRail outside clipping parents
    Rectangle {
        visible: root.showRailTooltip && root.compactRail && root.itemHovered && root.text.length > 0
        z: 100
        x: root.width + 8
        y: Math.round((root.height - height) / 2)
        width: railTipTxt.implicitWidth + 16
        height: 26
        radius: 6
        color: HKS.elevated
        border.width: 1
        border.color: HKS.alpha(HKS.accent, 0.5)

        Text {
            id: railTipTxt
            anchors.centerIn: parent
            text: root.text
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeSmall
            color: HKS.fg
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.disabled ? Qt.ArrowCursor : Qt.PointingHandCursor
        onClicked: {
            if (!root.disabled) {
                root.clicked();
            }
        }
    }
}
