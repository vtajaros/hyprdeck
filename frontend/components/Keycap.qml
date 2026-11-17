import QtQuick
import "../theme"

Rectangle {
    id: root

    property string text: ""
    property bool active: false
    readonly property bool isModifier: ["SUPER", "SHIFT", "CTRL", "ALT", "MOD2", "MOD3", "MOD5"].indexOf(text.toUpperCase()) !== -1

    implicitWidth: Math.min(280, Math.max(26, label.implicitWidth + 14))
    implicitHeight: 24
    radius: 5
    color: active
        ? Deck.alpha(Deck.accent, 0.25)
        : (isModifier ? Deck.elevated : Deck.alpha(Deck.surface, 0.85))

    border.width: 1
    border.color: active
        ? Deck.accent
        : (isModifier ? Deck.alpha(Deck.muted, 0.35) : Deck.alpha(Deck.muted, 0.2))

    Text {
        id: label
        objectName: "elideOk"
        anchors.centerIn: parent
        width: Math.min(parent.width - 8, implicitWidth)
        text: root.text
        font.family: Deck.fontFamily
        font.pixelSize: Deck.fontSizeSmall
        font.weight: Font.DemiBold
        color: root.active ? Deck.accent : Deck.fg
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignHCenter
    }
}
