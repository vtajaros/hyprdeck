import QtQuick
import QtQuick.Controls.Basic
import Quickshell
import "../theme"
import "../services"

Rectangle {
    id: root

    property var bindData: null
    property bool isExpanded: false
    property bool isSelected: false
    property string layoutClass: "expanded"
    signal toggleExpand()

    readonly property string rowMode: ResponsiveLogic.keybindRowModeForClass(layoutClass)
    readonly property bool actionsCollapsed: ResponsiveLogic.keybindActionsCollapsed(layoutClass)
    readonly property bool showCollapsedActionBtn: actionsCollapsed && (mouseArea.containsMouse || root.isSelected || root.isExpanded)
    readonly property bool isPopupMode: Deck.env("MODE") === "popup"

    readonly property var badgeItems: {
        if (!root.bindData) return [];
        var res = [];
        var f = root.bindData.flags || {};
        if (f.locked) res.push({ text: "locked", type: "flag" });
        if (f.repeating) res.push({ text: "repeat", type: "flag" });
        if (root.bindData.generated) res.push({ text: "loop", type: "loop" });
        if (root.bindData.conflict_ids && root.bindData.conflict_ids.length > 0) res.push({ text: "stacked", type: "stacked" });
        if (f.mouse) res.push({ text: "mouse", type: "flag" });
        if (f.release) res.push({ text: "release", type: "flag" });
        if (f.long_press) res.push({ text: "long", type: "flag" });
        return res;
    }

    readonly property string displaySource: {
        if (!root.bindData || !root.bindData.source_file) return "";
        var path = root.bindData.source_file;
        var home = Quickshell.env("HOME") || "";
        if (home && path.startsWith(home)) {
            path = "~" + path.slice(home.length);
        }
        if (root.bindData.source_line !== undefined && root.bindData.source_line !== null) {
            path += ":" + root.bindData.source_line;
        }
        return path;
    }

    readonly property bool isJustEdited: !!(root.bindData && EditService.lastEditedBindId && EditService.lastEditedBindId === root.bindData.id)

    implicitWidth: 600
    implicitHeight: mainCol.implicitHeight + 16

    radius: 8
    color: isJustEdited
        ? Deck.alpha(Deck.accent, 0.3)
        : (isExpanded
            ? Deck.alpha(Deck.elevated, 0.75)
            : (mouseArea.containsMouse ? Deck.alpha(Deck.surface, 0.8) : Deck.alpha(Deck.surface, 0.4)))

    border.width: 1
    border.color: isJustEdited
        ? Deck.accent
        : (isExpanded
            ? Deck.alpha(Deck.accent, 0.5)
            : (isSelected ? Deck.alpha(Deck.accent, 0.3) : Deck.alpha(Deck.muted, 0.12)))

    Behavior on color { ColorAnimation { duration: 100 } }
    Behavior on border.color { ColorAnimation { duration: 100 } }

    Column {
        id: mainCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8
        spacing: 8

        // Responsive top summary area
        Item {
            id: topRowItem
            width: parent.width
            height: root.rowMode === "stacked"
                ? stackedCol.implicitHeight
                : (root.rowMode === "two-line"
                    ? twoLineCol.implicitHeight
                    : Math.max(shortcutCol.implicitHeight, Math.max(descCol.implicitHeight, Math.max(badgesCol.implicitHeight, 28))))

            MouseArea {
                id: mouseArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.toggleExpand()
            }

            // === MODE 1: COLUMNS (regular / wide) ===
            Item {
                anchors.fill: parent
                visible: root.rowMode === "columns"

                readonly property int catColW: Math.min(130, Math.max(76, Math.round(parent.width * 0.16)))
                readonly property int keyColW: Math.min(260, Math.max(150, Math.round(parent.width * 0.28)))

                Item {
                    id: shortcutCol
                    width: parent.keyColW
                    implicitHeight: shortcutKeys.implicitHeight
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter

                    ShortcutKeys {
                        id: shortcutKeys
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        wrap: true
                        parts: root.bindData ? KeybindData.shortcutParts(root.bindData) : []
                    }
                }

                Item {
                    id: categoryCol
                    width: parent.catColW
                    height: 22
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter

                    Rectangle {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        height: 22
                        width: Math.min(parent.width, catLabel.implicitWidth + 14)
                        radius: 11
                        color: Deck.alpha(Deck.accent, 0.15)
                        border.width: 1
                        border.color: Deck.alpha(Deck.accent, 0.3)

                        Text {
                            id: catLabel
                            objectName: "elideOk"
                            anchors.centerIn: parent
                            width: Math.min(implicitWidth, parent.width - 10)
                            horizontalAlignment: Text.AlignHCenter
                            text: root.bindData ? (root.bindData.category || "Other") : ""
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            color: Deck.accent
                            elide: Text.ElideRight
                        }
                    }
                }

                Flow {
                    id: badgesCol
                    anchors.right: categoryCol.left
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(implicitWidth, 160)
                    spacing: 4

                    Repeater {
                        model: root.badgeItems
                        delegate: Rectangle {
                            height: 20
                            width: badgeText.implicitWidth + (modelData.type === "stacked" ? 10 : 8)
                            radius: 4
                            color: modelData.type === "stacked"
                                ? Deck.alpha(Deck.warning, 0.2)
                                : (modelData.type === "loop" ? Deck.alpha(Deck.muted, 0.15) : Deck.alpha(Deck.muted, 0.12))
                            border.width: 1
                            border.color: modelData.type === "stacked"
                                ? Deck.alpha(Deck.warning, 0.6)
                                : (modelData.type === "loop" ? Deck.alpha(Deck.muted, 0.3) : Deck.alpha(Deck.muted, 0.22))

                            Text {
                                id: badgeText
                                anchors.centerIn: parent
                                text: modelData.text
                                font.family: Deck.fontFamily
                                font.pixelSize: 9
                                font.weight: modelData.type === "stacked" ? Font.Bold : Font.Normal
                                color: modelData.type === "stacked" ? Deck.warning : Deck.muted
                            }
                        }
                    }
                }

                Column {
                    id: descCol
                    anchors.left: shortcutCol.right
                    anchors.leftMargin: 12
                    anchors.right: badgesCol.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Row {
                        width: parent.width
                        spacing: 6

                        Text {
                            id: colDescText
                            objectName: "elideOk"
                            text: root.bindData ? KeybindData.descriptionText(root.bindData) : ""
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSize
                            font.weight: Font.DemiBold
                            color: Deck.fg
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            width: Math.min(implicitWidth, Math.max(40, parent.width - 34))

                            ToolTip.visible: colDescHover.containsMouse && colDescText.truncated
                            ToolTip.text: colDescText.text
                            MouseArea {
                                id: colDescHover
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.NoButton
                            }
                        }

                        Rectangle {
                            width: 28
                            height: 24
                            radius: 4
                            anchors.verticalCenter: parent.verticalCenter
                            color: pencilMa.containsMouse ? Deck.alpha(Deck.accent, 0.2) : "transparent"

                            Text {
                                anchors.centerIn: parent
                                text: ""
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: pencilMa.containsMouse ? Deck.accent : Deck.alpha(Deck.muted, 0.6)
                            }

                            MouseArea {
                                id: pencilMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: EditService.requestEdit(root.bindData)
                            }
                        }
                    }

                    Text {
                        objectName: "elideOk"
                        width: parent.width
                        text: root.bindData ? KeybindData.actionText(root.bindData) : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                        elide: Text.ElideRight
                    }
                }
            }

            // === MODE 2: TWO-LINE (cozy / medium 440-679) ===
            Column {
                id: twoLineCol
                width: parent.width
                visible: root.rowMode === "two-line"
                spacing: 6

                Row {
                    width: parent.width
                    spacing: 10

                    Item {
                        width: Math.min(180, Math.round(parent.width * 0.36))
                        height: twoLineKeys.implicitHeight
                        anchors.verticalCenter: parent.verticalCenter

                        ShortcutKeys {
                            id: twoLineKeys
                            width: parent.width
                            wrap: true
                            parts: root.bindData ? KeybindData.shortcutParts(root.bindData) : []
                        }
                    }

                    Text {
                        id: twoLineDesc
                        objectName: "elideOk"
                        width: Math.max(60, parent.width - Math.min(180, Math.round(parent.width * 0.36)) - (twoLineOverflow.visible ? 38 : 10))
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.bindData ? KeybindData.descriptionText(root.bindData) : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSize
                        font.weight: Font.DemiBold
                        color: Deck.fg
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight

                        ToolTip.visible: twoLineDescHover.containsMouse && twoLineDesc.truncated
                        ToolTip.text: twoLineDesc.text
                        MouseArea {
                            id: twoLineDescHover
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                        }
                    }

                    Rectangle {
                        id: twoLineOverflow
                        visible: !root.isPopupMode && root.showCollapsedActionBtn
                        width: 28
                        height: 24
                        radius: 4
                        anchors.verticalCenter: parent.verticalCenter
                        color: twoOverflowMa.containsMouse ? Deck.alpha(Deck.accent, 0.2) : Deck.alpha(Deck.elevated, 0.7)

                        Text {
                            anchors.centerIn: parent
                            text: "⋯"
                            font.family: Deck.fontFamily
                            font.pixelSize: 12
                            font.weight: Font.Bold
                            color: Deck.fg
                        }

                        MouseArea {
                            id: twoOverflowMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: overflowMenu.popup(twoLineOverflow, 0, twoLineOverflow.height)
                        }
                    }
                }

                Flow {
                    width: parent.width
                    spacing: 6

                    Rectangle {
                        height: 20
                        width: Math.min(parent.width, twoCatTxt.implicitWidth + 12)
                        radius: 10
                        color: Deck.alpha(Deck.accent, 0.15)
                        border.width: 1
                        border.color: Deck.alpha(Deck.accent, 0.3)

                        Text {
                            id: twoCatTxt
                            objectName: "elideOk"
                            anchors.centerIn: parent
                            width: Math.min(implicitWidth, parent.width - 8)
                            text: root.bindData ? (root.bindData.category || "Other") : ""
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            color: Deck.accent
                            elide: Text.ElideRight
                        }
                    }

                    Text {
                        objectName: "elideOk"
                        width: Math.min(implicitWidth, parent.width)
                        height: 20
                        verticalAlignment: Text.AlignVCenter
                        text: root.bindData ? KeybindData.actionText(root.bindData) : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                        elide: Text.ElideRight
                    }

                    Repeater {
                        model: root.badgeItems
                        delegate: Rectangle {
                            height: 20
                            width: badgeTxt2.implicitWidth + 8
                            radius: 4
                            color: modelData.type === "stacked" ? Deck.alpha(Deck.warning, 0.2) : Deck.alpha(Deck.muted, 0.12)
                            border.width: 1
                            border.color: modelData.type === "stacked" ? Deck.alpha(Deck.warning, 0.6) : Deck.alpha(Deck.muted, 0.22)

                            Text {
                                id: badgeTxt2
                                anchors.centerIn: parent
                                text: modelData.text
                                font.family: Deck.fontFamily
                                font.pixelSize: 9
                                color: modelData.type === "stacked" ? Deck.warning : Deck.muted
                            }
                        }
                    }
                }
            }

            // === MODE 3: STACKED CARD (compact < 440) ===
            Column {
                id: stackedCol
                width: parent.width
                visible: root.rowMode === "stacked"
                spacing: 6

                Row {
                    width: parent.width
                    spacing: 8

                    ShortcutKeys {
                        width: Math.max(40, parent.width - (stackedOverflow.visible ? 36 : 0))
                        wrap: true
                        parts: root.bindData ? KeybindData.shortcutParts(root.bindData) : []
                    }

                    Rectangle {
                        id: stackedOverflow
                        visible: !root.isPopupMode && root.showCollapsedActionBtn
                        width: 28
                        height: 24
                        radius: 4
                        color: stOverflowMa.containsMouse ? Deck.alpha(Deck.accent, 0.2) : Deck.alpha(Deck.elevated, 0.7)

                        Text {
                            anchors.centerIn: parent
                            text: "⋯"
                            font.family: Deck.fontFamily
                            font.pixelSize: 12
                            font.weight: Font.Bold
                            color: Deck.fg
                        }

                        MouseArea {
                            id: stOverflowMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: overflowMenu.popup(stackedOverflow, 0, stackedOverflow.height)
                        }
                    }
                }

                Text {
                    id: stackedDesc
                    objectName: "elideOk"
                    width: parent.width
                    text: root.bindData ? KeybindData.descriptionText(root.bindData) : ""
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSize
                    font.weight: Font.DemiBold
                    color: Deck.fg
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight

                    ToolTip.visible: stackedDescHover.containsMouse && stackedDesc.truncated
                    ToolTip.text: stackedDesc.text
                    MouseArea {
                        id: stackedDescHover
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }
                }

                Text {
                    objectName: "elideOk"
                    width: parent.width
                    text: root.bindData ? KeybindData.actionText(root.bindData) : ""
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.muted
                    wrapMode: Text.WrapAnywhere
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                Flow {
                    width: parent.width
                    spacing: 6

                    Rectangle {
                        height: 20
                        width: Math.min(parent.width, stCatTxt.implicitWidth + 12)
                        radius: 10
                        color: Deck.alpha(Deck.accent, 0.15)
                        border.width: 1
                        border.color: Deck.alpha(Deck.accent, 0.3)

                        Text {
                            id: stCatTxt
                            objectName: "elideOk"
                            anchors.centerIn: parent
                            width: Math.min(implicitWidth, parent.width - 8)
                            text: root.bindData ? (root.bindData.category || "Other") : ""
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            color: Deck.accent
                            elide: Text.ElideRight
                        }
                    }

                    Repeater {
                        model: root.badgeItems
                        delegate: Rectangle {
                            height: 20
                            width: badgeTxt3.implicitWidth + 8
                            radius: 4
                            color: modelData.type === "stacked" ? Deck.alpha(Deck.warning, 0.2) : Deck.alpha(Deck.muted, 0.12)
                            border.width: 1
                            border.color: modelData.type === "stacked" ? Deck.alpha(Deck.warning, 0.6) : Deck.alpha(Deck.muted, 0.22)

                            Text {
                                id: badgeTxt3
                                anchors.centerIn: parent
                                text: modelData.text
                                font.family: Deck.fontFamily
                                font.pixelSize: 9
                                color: modelData.type === "stacked" ? Deck.warning : Deck.muted
                            }
                        }
                    }
                }
            }
        }

        Menu {
            id: overflowMenu
            MenuItem {
                text: (root.bindData && root.bindData.generated) ? "Edit Description" : "Edit"
                onTriggered: EditService.requestEdit(root.bindData)
            }
            MenuItem {
                text: "Disable"
                enabled: !(root.bindData && root.bindData.generated)
                onTriggered: EditService.requestCommentOut(root.bindData)
            }
            MenuItem {
                text: "Delete"
                enabled: !(root.bindData && root.bindData.generated)
                onTriggered: EditService.requestDelete(root.bindData)
            }
        }

        // Expanded details section: grid with fixed label column (~80px) and selectable text
        Rectangle {
            width: parent.width
            height: root.isExpanded ? detailsCol.implicitHeight + 20 : 0
            visible: root.isExpanded
            clip: true
            radius: 6
            color: Deck.alpha(Deck.bg, 0.7)
            border.width: 1
            border.color: Deck.alpha(Deck.muted, 0.18)

            Column {
                id: detailsCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10
                spacing: 8

                // Row 1: Source file with "~" replacement + ":line"
                Row {
                    width: parent.width
                    spacing: 8

                    Text {
                        width: 80
                        text: "Source:"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.Bold
                        color: Deck.muted
                    }

                    TextEdit {
                        width: parent.width - 88
                        text: root.displaySource
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.fg
                        readOnly: true
                        selectByMouse: true
                        selectionColor: Deck.alpha(Deck.accent, 0.4)
                        selectedTextColor: Deck.fg
                        wrapMode: TextEdit.WrapAnywhere
                    }
                }

                // Row 2: Config original line
                Row {
                    width: parent.width
                    spacing: 8

                    Text {
                        width: 80
                        text: "Config:"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.Bold
                        color: Deck.muted
                    }

                    TextEdit {
                        width: parent.width - 88
                        text: root.bindData ? (root.bindData.original_line || "") : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.accent
                        readOnly: true
                        selectByMouse: true
                        selectionColor: Deck.alpha(Deck.accent, 0.4)
                        selectedTextColor: Deck.fg
                        wrapMode: TextEdit.WrapAnywhere
                    }
                }

                // Row 3: Submap (visible only when non-empty)
                Row {
                    width: parent.width
                    spacing: 8
                    visible: !!(root.bindData && root.bindData.submap)

                    Text {
                        width: 80
                        text: "Submap:"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.Bold
                        color: Deck.muted
                    }

                    TextEdit {
                        width: parent.width - 88
                        text: root.bindData ? (root.bindData.submap || "") : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.fg
                        readOnly: true
                        selectByMouse: true
                        selectionColor: Deck.alpha(Deck.accent, 0.4)
                        selectedTextColor: Deck.fg
                    }
                }

                // Row 4: Action buttons (Disable / Delete) or Loop Notice (12px spacing above)
                Flow {
                    id: actionsRow
                    width: parent.width
                    spacing: 10
                    visible: !root.isPopupMode

                    ActionButton {
                        variant: "accent"
                        iconText: ""
                        text: (root.bindData && root.bindData.generated) ? "Edit Description" : "Edit"
                        enabled: true
                        onClicked: EditService.requestEdit(root.bindData)
                    }

                    ActionButton {
                        variant: "neutral"
                        iconText: ""
                        text: "Disable"
                        enabled: !(root.bindData && root.bindData.generated)
                        onClicked: EditService.requestCommentOut(root.bindData)
                    }

                    ActionButton {
                        variant: "danger"
                        iconText: ""
                        text: "Delete"
                        enabled: !(root.bindData && root.bindData.generated)
                        onClicked: EditService.requestDelete(root.bindData)
                    }

                    // Loop generated notice (disabled editing)
                    Row {
                        spacing: 8
                        width: Math.min(implicitWidth, parent.width)
                        visible: !!(root.bindData && root.bindData.generated)

                        Rectangle {
                            width: 22
                            height: 22
                            radius: 4
                            color: Deck.alpha(Deck.muted, 0.15)
                            Text {
                                anchors.centerIn: parent
                                text: ""
                                font.family: Deck.fontFamily
                                font.pixelSize: 11
                                color: Deck.muted
                            }
                        }

                        Text {
                            width: Math.min(implicitWidth, parent.width - 30)
                            wrapMode: Text.WordWrap
                            text: "generated by a loop at " + root.displaySource + " (only description can be edited)"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.muted
                            font.italic: true
                        }
                    }
                }
            }
        }
    }
}
