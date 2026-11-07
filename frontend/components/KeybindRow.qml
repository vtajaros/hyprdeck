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

    implicitWidth: 600
    implicitHeight: mainCol.implicitHeight + 16

    radius: 8
    color: isExpanded
        ? HKS.alpha(HKS.elevated, 0.75)
        : (mouseArea.containsMouse ? HKS.alpha(HKS.surface, 0.8) : HKS.alpha(HKS.surface, 0.4))

    border.width: 1
    border.color: isExpanded
        ? HKS.alpha(HKS.accent, 0.5)
        : (isSelected ? HKS.alpha(HKS.accent, 0.3) : HKS.alpha(HKS.muted, 0.12))

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
                implicitHeight: keycapsRow.implicitHeight
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                clip: true

                Row {
                    id: keycapsRow
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4

                    Repeater {
                        model: root.bindData ? KeybindData.shortcutParts(root.bindData) : []
                        delegate: Keycap {
                            text: modelData
                        }
                    }
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
                    color: HKS.alpha(HKS.accent, 0.15)
                    border.width: 1
                    border.color: HKS.alpha(HKS.accent, 0.3)

                    Text {
                        id: catLabel
                        anchors.centerIn: parent
                        text: root.bindData ? (root.bindData.category || "Other") : ""
                        font.family: HKS.fontFamily
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        color: HKS.accent
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
                            ? HKS.alpha(HKS.warning, 0.2)
                            : (modelData.type === "loop" ? HKS.alpha(HKS.muted, 0.15) : HKS.alpha(HKS.muted, 0.12))
                        border.width: 1
                        border.color: modelData.type === "stacked"
                            ? HKS.alpha(HKS.warning, 0.6)
                            : (modelData.type === "loop" ? HKS.alpha(HKS.muted, 0.3) : HKS.alpha(HKS.muted, 0.22))

                        Text {
                            id: badgeText
                            anchors.centerIn: parent
                            text: modelData.text
                            font.family: HKS.fontFamily
                            font.pixelSize: 9
                            font.weight: modelData.type === "stacked" ? Font.Bold : Font.Normal
                            color: modelData.type === "stacked" ? HKS.warning : HKS.muted
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

                Text {
                    width: parent.width
                    text: root.bindData ? KeybindData.descriptionText(root.bindData) : ""
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.DemiBold
                    color: HKS.fg
                    elide: Text.ElideRight
                }

                Text {
                    width: parent.width
                    text: root.bindData ? KeybindData.actionText(root.bindData) : ""
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: HKS.muted
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
            color: HKS.alpha(HKS.bg, 0.7)
            border.width: 1
            border.color: HKS.alpha(HKS.muted, 0.18)

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
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        font.weight: Font.Bold
                        color: HKS.muted
                    }

                    TextEdit {
                        width: parent.width - 88
                        text: root.displaySource
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.fg
                        readOnly: true
                        selectByMouse: true
                        selectionColor: HKS.alpha(HKS.accent, 0.4)
                        selectedTextColor: HKS.fg
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
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        font.weight: Font.Bold
                        color: HKS.muted
                    }

                    TextEdit {
                        width: parent.width - 88
                        text: root.bindData ? (root.bindData.original_line || "") : ""
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.accent
                        readOnly: true
                        selectByMouse: true
                        selectionColor: HKS.alpha(HKS.accent, 0.4)
                        selectedTextColor: HKS.fg
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
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        font.weight: Font.Bold
                        color: HKS.muted
                    }

                    TextEdit {
                        width: parent.width - 88
                        text: root.bindData ? (root.bindData.submap || "") : ""
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.fg
                        readOnly: true
                        selectByMouse: true
                        selectionColor: HKS.alpha(HKS.accent, 0.4)
                        selectedTextColor: HKS.fg
                    }
                }

                // Row 4: Action buttons (Disable / Delete) or Loop Notice
                Item {
                    width: parent.width
                    height: 32

                    // Loop generated notice (disabled editing)
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        visible: !!(root.bindData && root.bindData.generated)

                        Rectangle {
                            width: 22
                            height: 22
                            radius: 4
                            color: HKS.alpha(HKS.muted, 0.15)
                            Text {
                                anchors.centerIn: parent
                                text: ""
                                font.family: HKS.fontFamily
                                font.pixelSize: 11
                                color: HKS.muted
                            }
                        }

                        Text {
                            text: "generated by a loop at " + root.displaySource + ", edit the loop instead"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                            font.italic: true
                        }
                    }

                    // Editable action buttons (window mode only)
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10
                        visible: !(root.bindData && root.bindData.generated) && (Quickshell.env("HKS_MODE") !== "popup")

                        // Disable Button
                        Rectangle {
                            width: disableText.implicitWidth + 24
                            height: 28
                            radius: 6
                            color: disMa.containsMouse ? HKS.alpha(HKS.accent, 0.25) : HKS.alpha(HKS.accent, 0.12)
                            border.width: 1
                            border.color: HKS.alpha(HKS.accent, 0.4)

                            Row {
                                anchors.centerIn: parent
                                spacing: 6
                                Text {
                                    text: ""
                                    font.family: HKS.fontFamily
                                    font.pixelSize: 12
                                    color: HKS.accent
                                }
                                Text {
                                    id: disableText
                                    text: "Disable"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    font.weight: Font.DemiBold
                                    color: HKS.accent
                                }
                            }

                            MouseArea {
                                id: disMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    EditService.requestCommentOut(root.bindData);
                                }
                            }
                        }

                        // Delete Button (destructive)
                        Rectangle {
                            width: delText.implicitWidth + 24
                            height: 28
                            radius: 6
                            color: delMa.containsMouse ? HKS.alpha(HKS.critical, 0.25) : HKS.alpha(HKS.critical, 0.12)
                            border.width: 1
                            border.color: HKS.alpha(HKS.critical, 0.4)

                            Row {
                                anchors.centerIn: parent
                                spacing: 6
                                Text {
                                    text: ""
                                    font.family: HKS.fontFamily
                                    font.pixelSize: 12
                                    color: HKS.critical
                                }
                                Text {
                                    id: delText
                                    text: "Delete"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    font.weight: Font.DemiBold
                                    color: HKS.critical
                                }
                            }

                            MouseArea {
                                id: delMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    EditService.requestDelete(root.bindData);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
