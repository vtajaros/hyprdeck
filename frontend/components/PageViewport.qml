import QtQuick
import "../theme"

Item {
    id: root

    property bool allowTwoColumns: false
    property real maxContentWidth: HKS.contentMaxWidth
    property alias header: headerSlot.data
    property alias contentItem: bodyCol
    property alias verticalFlickable: vFlick
    default property alias content: bodyCol.data

    property string layoutClass: "expanded"
    readonly property bool layoutShort: ResponsiveLogic.isLayoutShort(root.height)
    readonly property int outerMargin: HKS.scaledSpace(HKS.space24, root.layoutClass, root.layoutShort)
    readonly property int sectionSpacing: HKS.scaledSpace(HKS.space12, root.layoutClass, root.layoutShort)
    readonly property int cardPadding: HKS.scaledSpace(HKS.space12, root.layoutClass, root.layoutShort)

    readonly property bool horizontalScrollNeeded: root.width > 0 && (root.width - root.outerMargin * 2) < HKS.minContentScrollWidth
    readonly property real innerWidth: Math.max(
        HKS.minContentScrollWidth,
        Math.min(Math.max(0, root.width - root.outerMargin * 2), root.maxContentWidth)
    )
    readonly property bool twoColumns: root.allowTwoColumns && root.width >= HKS.twoColumnThreshold
    readonly property int columnSpacing: HKS.space12
    readonly property real twoColumnCardWidth: root.twoColumns
        ? Math.floor((root.innerWidth - root.columnSpacing) / 2)
        : root.innerWidth

    function _updateLayoutClass() {
        var usable = Math.max(HKS.minContentScrollWidth, root.width - HKS.space24 * 2);
        var next = ResponsiveLogic.computeLayoutClass(usable, root.layoutClass);
        if (next !== root.layoutClass) {
            root.layoutClass = next;
        }
    }

    Component.onCompleted: _updateLayoutClass()
    onWidthChanged: _updateLayoutClass()

    Flickable {
        id: hFlick
        objectName: "horizontalSafetyScroller"
        anchors.fill: parent
        clip: true
        interactive: root.horizontalScrollNeeded
        boundsBehavior: Flickable.StopAtBounds
        contentWidth: Math.max(root.width, root.innerWidth + root.outerMargin * 2)
        contentHeight: root.height

        Item {
            id: stage
            x: Math.max(root.outerMargin, Math.floor((hFlick.contentWidth - width) / 2))
            y: 0
            width: root.innerWidth
            height: hFlick.height

            Column {
                id: headerSlot
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: root.outerMargin
                spacing: root.sectionSpacing
            }

            Flickable {
                id: vFlick
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: headerSlot.height > 0 ? headerSlot.bottom : parent.top
                anchors.topMargin: headerSlot.height > 0 ? root.sectionSpacing : root.outerMargin
                anchors.bottom: parent.bottom
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentWidth: width
                contentHeight: bodyCol.implicitHeight + root.outerMargin

                Column {
                    id: bodyCol
                    width: vFlick.width
                    spacing: root.sectionSpacing
                }
            }
        }
    }
}
