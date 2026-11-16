import QtQuick
import "../theme"

Rectangle {
    id: root

    property string text: ""
    property string iconText: ""
    property string variant: "neutral" // "neutral" | "accent" | "danger"
    property bool compact: false
    signal clicked()

    readonly property real horizontalPadding: compact ? 10 : 14
    readonly property real contentSpacing: (iconLabel.visible && textLabel.visible) ? 8 : 0

    TextMetrics {
        id: textMetrics
        font.family: HKS.fontFamily
        font.pixelSize: HKS.fontSizeSmall
        font.weight: Font.DemiBold
        text: root.text
    }

    implicitHeight: compact ? 28 : 32
    implicitWidth: Math.max(84, (iconLabel.visible ? iconLabel.implicitWidth : 0) + contentSpacing + (root.text.length > 0 ? Math.ceil(textMetrics.advanceWidth) : 0) + (2 * horizontalPadding))
    width: implicitWidth
    height: implicitHeight

    radius: Math.max(4, HKS.radius - 2)
    border.width: 1
    clip: false

    opacity: root.enabled ? 1.0 : 0.4
    Behavior on opacity { NumberAnimation { duration: 100 } }

    activeFocusOnTab: root.enabled

    // Color definitions per variant
    readonly property bool isHovered: mouseArea.containsMouse && root.enabled
    readonly property bool isPressed: mouseArea.pressed && root.enabled

    color: {
        if (root.variant === "accent") {
            if (isPressed) return HKS.alpha(HKS.accent, 0.38);
            if (isHovered) return HKS.alpha(HKS.accent, 0.25);
            return HKS.alpha(HKS.accent, 0.15);
        }
        if (root.variant === "danger") {
            if (isPressed) return HKS.alpha(HKS.critical, 0.38);
            if (isHovered) return HKS.alpha(HKS.critical, 0.25);
            return HKS.alpha(HKS.critical, 0.15);
        }
        // neutral
        if (isPressed) return Qt.darker(HKS.elevated, 1.25);
        if (isHovered) return Qt.lighter(HKS.elevated, 1.2);
        return HKS.elevated;
    }

    border.color: {
        if (root.activeFocus) {
            return (root.variant === "danger") ? HKS.critical : HKS.accent;
        }
        if (root.variant === "accent") {
            return isHovered ? HKS.accent : HKS.alpha(HKS.accent, 0.45);
        }
        if (root.variant === "danger") {
            return isHovered ? HKS.critical : HKS.alpha(HKS.critical, 0.45);
        }
        // neutral
        return isHovered ? HKS.alpha(HKS.muted, 0.5) : HKS.alpha(HKS.muted, 0.28);
    }

    readonly property color contentColor: {
        if (root.variant === "accent") return HKS.accent;
        if (root.variant === "danger") return HKS.critical;
        return isHovered ? HKS.fg : HKS.alpha(HKS.fg, 0.9);
    }

    Behavior on color { ColorAnimation { duration: 100 } }
    Behavior on border.color { ColorAnimation { duration: 100 } }

    Row {
        id: contentRow
        anchors.centerIn: parent
        spacing: root.contentSpacing

        Text {
            id: iconLabel
            anchors.verticalCenter: parent.verticalCenter
            visible: root.iconText.length > 0
            text: root.iconText
            font.family: HKS.fontFamily
            font.pixelSize: root.compact ? 11 : 13
            color: root.contentColor
        }

        Text {
            id: textLabel
            objectName: "elideOk"
            anchors.verticalCenter: parent.verticalCenter
            visible: root.text.length > 0
            width: {
                var maxW = Math.max(0, root.width - (2 * root.horizontalPadding) - (iconLabel.visible ? iconLabel.implicitWidth + root.contentSpacing : 0));
                return Math.min(Math.ceil(textMetrics.advanceWidth) + 2, maxW);
            }
            text: root.text
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeSmall
            font.weight: Font.DemiBold
            color: root.contentColor
            elide: Text.ElideRight
        }
    }

    Keys.onPressed: function(event) {
        if (!root.enabled) return;
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            root.clicked();
            event.accepted = true;
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: root.enabled
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        enabled: root.enabled
        onClicked: {
            root.forceActiveFocus();
            root.clicked();
        }
    }
}
