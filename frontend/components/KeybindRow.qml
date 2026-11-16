import QtQuick
import Quickshell
import "../theme"
import "../services"

Rectangle {
    id: root

    property var bindData: null
    property bool isExpanded: false
    property bool isSelected: false
    signal toggleExpand()

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

        // Top line fixed-column layout:
        // [shortcut column (300px) | description+action column (fills) | badge column | category column (140px)]
        Item {
            id: topRowItem
            width: parent.width
            height: Math.max(shortcutCol.implicitHeight, Math.max(descCol.implicitHeight, Math.max(badgesCol.implicitHeight, 28)))

            MouseArea {
                id: mouseArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.toggleExpand()
            }

            // 1. Shortcut column: fixed width ~300px, content left-aligned, keycaps never wrap or overlap
            Item {
                id: shortcutCol
                width: 300
                implicitHeight: shortcutKeys.implicitHeight
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                clip: true

                ShortcutKeys {
                    id: shortcutKeys
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width
                    parts: root.bindData ? KeybindData.shortcutParts(root.bindData) : []
                }
            }

            // 4. Category column: fixed width (width of longest category "Media & Hardware" ~140px), right-aligned
            Item {
                id: categoryCol
                width: 140
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
                        anchors.centerIn: parent
                        text: root.bindData ? (root.bindData.category || "Other") : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        color: Deck.accent
                        elide: Text.ElideRight
                    }
                }
            }

            // 3. Badges column: right-aligned Row in fixed order (locked, repeat, loop, stacked, flags)
            Row {
                id: badgesCol
                anchors.right: categoryCol.left
                anchors.rightMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Repeater {
                    model: {
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

                    delegate: Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
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

            // 2. Description + action column: fills between shortcut column and badges, starting at the exact same x on every row
            Column {
                id: descCol
                anchors.left: shortcutCol.right
                anchors.leftMargin: 12
                anchors.right: badgesCol.left
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                clip: true

                Row {
                    width: parent.width
                    spacing: 6

                    Text {
                        text: root.bindData ? KeybindData.descriptionText(root.bindData) : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSize
                        font.weight: Font.DemiBold
                        color: Deck.fg
                        elide: Text.ElideRight
                        width: Math.min(implicitWidth, parent.width - 24)
                    }

                    Rectangle {
                        width: 18
                        height: 18
                        radius: 3
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
                    width: parent.width
                    text: root.bindData ? KeybindData.actionText(root.bindData) : ""
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.muted
                    elide: Text.ElideRight
                }
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
                Item {
                    width: parent.width
                    height: actionsRow.height + 12

                    Row {
                        id: actionsRow
                        anchors.bottom: parent.bottom
                        spacing: 10
                        visible: Deck.env("MODE") !== "popup"

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
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8
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
}
