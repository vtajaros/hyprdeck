import QtQuick
import "../theme"

Item {
    id: root

    property string title: ""
    property string subtitle: ""
    property real spacing: HKS.space12
    default property alias actions: actionsFlow.data

    TextMetrics {
        id: titleMetrics
        font.family: HKS.fontFamily
        font.pixelSize: HKS.fontSizeTitle
        font.weight: Font.Bold
        text: root.title
    }

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
    readonly property bool wrapped: ResponsiveLogic.shouldWrapHeaderActions(
        root.width, titleMetrics.advanceWidth, root.actionsNaturalWidth, root.spacing
    )
    readonly property real inlineActionsWidth: (!root.wrapped && root.hasActions)
        ? Math.min(root.actionsNaturalWidth, root.width)
        : 0
    readonly property real _rowMaxHeight: Math.max(titleCol.implicitHeight, actionsFlow.implicitHeight)

    width: parent ? parent.width : implicitWidth
    implicitWidth: Math.max(titleCol.implicitWidth + (hasActions ? root.spacing + actionsNaturalWidth : 0), 200)
    implicitHeight: root.wrapped
        ? (titleCol.implicitHeight + (root.hasActions ? HKS.space8 + actionsFlow.implicitHeight : 0))
        : root._rowMaxHeight
    height: implicitHeight

    Column {
        id: titleCol
        x: 0
        y: root.wrapped ? 0 : Math.max(0, Math.round((root._rowMaxHeight - height) / 2))
        width: root.wrapped
            ? root.width
            : Math.max(0, root.width - root.inlineActionsWidth - (root.hasActions ? root.spacing : 0))
        spacing: 4

        Text {
            id: titleTxt
            width: parent.width
            text: root.title
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeTitle
            font.weight: Font.Bold
            color: HKS.fg
            wrapMode: Text.WordWrap
        }

        Text {
            id: subtitleTxt
            visible: root.subtitle.length > 0
            width: parent.width
            text: root.subtitle
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeSmall
            color: HKS.muted
            wrapMode: Text.WordWrap
        }
    }

    Flow {
        id: actionsFlow
        property int _rev: 0
        onChildrenChanged: _rev++
        x: root.wrapped ? 0 : Math.max(0, root.width - width)
        y: root.wrapped
            ? (titleCol.implicitHeight + HKS.space8)
            : Math.max(0, Math.round((root._rowMaxHeight - height) / 2))
        width: root.wrapped ? root.width : root.inlineActionsWidth
        spacing: HKS.space8
    }
}
