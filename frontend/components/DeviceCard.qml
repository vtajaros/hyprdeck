import QtQuick
import "../theme"

Rectangle {
    id: root

    property string title: ""
    property string subtitle: ""
    property string detailText: ""
    // Array of badge objects: { text, textColor?, bgColor?, borderColor? } or strings
    property var badges: []
    property bool highlighted: false
    property real cardPadding: HKS.space12
    property real minInfoWidth: 210
    property alias actions: actionsFlow.data
    property alias extraContent: extraSlot.data

    width: parent ? parent.width : implicitWidth
    implicitHeight: innerBox.implicitHeight + (root.cardPadding * 2)
    height: implicitHeight
    radius: HKS.radiusMedium
    color: root.highlighted ? HKS.alpha(HKS.accent, 0.06) : HKS.surface
    border.width: 1
    border.color: root.highlighted ? HKS.accent : HKS.alpha(HKS.muted, 0.18)

    Item {
        id: innerBox
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: root.cardPadding

        readonly property real actionsNaturalWidth: {
            var _trigger = actionsFlow._rev;
            var total = 0;
            var count = 0;
            var kids = actionsFlow.children;
            for (var i = 0; i < kids.length; i++) {
                var c = kids[i];
                if (c && c.visible && c.implicitWidth > 0) {
                    if (count > 0) total += actionsFlow.spacing;
                    total += c.implicitWidth;
                    count++;
                }
            }
            return total;
        }
        readonly property bool hasActions: actionsNaturalWidth > 0
        readonly property bool actionsWrapped: ResponsiveLogic.shouldWrapDeviceActions(
            innerBox.width, root.minInfoWidth, innerBox.actionsNaturalWidth, HKS.space12
        )
        readonly property real inlineActionsWidth: (!actionsWrapped && hasActions)
            ? Math.min(actionsNaturalWidth, innerBox.width)
            : 0
        readonly property real headerHeight: actionsWrapped
            ? (infoCol.implicitHeight + (hasActions ? HKS.space8 + actionsFlow.implicitHeight : 0))
            : Math.max(infoCol.implicitHeight, actionsFlow.implicitHeight)
        readonly property bool hasExtra: {
            var _trigger = extraSlot._rev;
            var kids = extraSlot.children;
            for (var i = 0; i < kids.length; i++) {
                if (kids[i] && kids[i].visible) return true;
            }
            return false;
        }

        implicitHeight: headerHeight + (hasExtra ? HKS.space8 + extraSlot.implicitHeight : 0)
        height: implicitHeight

        Column {
            id: infoCol
            x: 0
            y: 0
            width: innerBox.actionsWrapped
                ? innerBox.width
                : Math.max(0, innerBox.width - innerBox.inlineActionsWidth - (innerBox.hasActions ? HKS.space12 : 0))
            spacing: HKS.space4

            Text {
                visible: root.title.length > 0
                width: parent.width
                text: root.title
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSize
                font.weight: Font.DemiBold
                color: HKS.fg
                wrapMode: Text.WordWrap
            }

            Flow {
                visible: (root.badges || []).length > 0
                width: parent.width
                spacing: 6

                Repeater {
                    model: root.badges || []

                    Rectangle {
                        id: badgePill
                        required property var modelData
                        readonly property string bText: (typeof modelData === "string")
                            ? modelData
                            : String(modelData && modelData.text ? modelData.text : "")
                        readonly property color bFg: (modelData && modelData.textColor !== undefined)
                            ? modelData.textColor
                            : HKS.fg
                        readonly property color bBg: (modelData && modelData.bgColor !== undefined)
                            ? modelData.bgColor
                            : HKS.elevated
                        readonly property color bBorder: (modelData && modelData.borderColor !== undefined)
                            ? modelData.borderColor
                            : HKS.alpha(HKS.muted, 0.25)

                        TextMetrics {
                            id: badgeMetrics
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            font.weight: Font.Medium
                            text: badgePill.bText
                        }

                        visible: bText.length > 0
                        width: Math.min(Math.ceil(badgeMetrics.advanceWidth) + 14, Math.max(28, infoCol.width))
                        height: 20
                        radius: HKS.radiusSmall
                        color: bBg
                        border.width: 1
                        border.color: bBorder

                        Text {
                            id: badgeTxt
                            objectName: "elideOk"
                            anchors.fill: parent
                            anchors.leftMargin: 7
                            anchors.rightMargin: 7
                            verticalAlignment: Text.AlignVCenter
                            text: badgePill.bText
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            font.weight: Font.Medium
                            color: badgePill.bFg
                            elide: Text.ElideRight
                        }
                    }
                }
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

            Text {
                objectName: "elideOk"
                visible: root.detailText.length > 0
                width: parent.width
                text: root.detailText
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.alpha(HKS.muted, 0.85)
                elide: Text.ElideRight
            }
        }

        Flow {
            id: actionsFlow
            property int _rev: 0
            onChildrenChanged: _rev++
            x: innerBox.actionsWrapped ? 0 : Math.max(0, innerBox.width - width)
            y: innerBox.actionsWrapped ? (infoCol.implicitHeight + HKS.space8) : 0
            width: innerBox.actionsWrapped ? innerBox.width : innerBox.inlineActionsWidth
            spacing: HKS.space8
        }

        Column {
            id: extraSlot
            property int _rev: 0
            onChildrenChanged: _rev++
            x: 0
            y: innerBox.headerHeight + HKS.space8
            width: innerBox.width
            spacing: HKS.space8
        }
    }
}
