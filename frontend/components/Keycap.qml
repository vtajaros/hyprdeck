import QtQuick
import "../theme"

Rectangle {
    id: root

    property string text: ""
    property bool active: false
    readonly property bool isModifier: ["SUPER", "SHIFT", "CTRL", "ALT", "MOD2", "MOD3", "MOD5"].indexOf(text.toUpperCase()) !== -1

    implicitWidth: Math.max(26, label.implicitWidth + 14)
    implicitHeight: 24
    radius: 5
    color: active
        ? HKS.alpha(HKS.accent, 0.25)
        : (isModifier ? HKS.elevated : HKS.alpha(HKS.surface, 0.85))

    border.width: 1
    border.color: active
        ? HKS.accent
        : (isModifier ? HKS.alpha(HKS.muted, 0.35) : HKS.alpha(HKS.muted, 0.2))

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        font.family: HKS.fontFamily
        font.pixelSize: HKS.fontSizeSmall
        font.weight: Font.DemiBold
        color: root.active ? HKS.accent : HKS.fg
    }
}
