import QtQuick
import QtQuick.Controls.Basic
import "../theme"
import "../services"

Item {
    id: root

    property bool deleteConfirmed: false

    // Reset state when dialog opens
    onVisibleChanged: {
        if (visible) {
            deleteConfirmed = false;
        }
    }

    // Modal background overlay
    Rectangle {
        anchors.fill: parent
        color: "#b8090b0e"

        MouseArea {
            anchors.fill: parent
            // Prevent clicks from reaching beneath the modal
            onClicked: {}
        }
    }

    // Centered modal card
    Rectangle {
        id: card
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 720)
        height: Math.min(parent.height - 48, 580)
        radius: HKS.radius
        color: HKS.bg
        border.width: 1
        border.color: EditService.activeOp && EditService.activeOp.isDestructive
            ? HKS.alpha(HKS.critical, 0.5)
            : HKS.alpha(HKS.accent, 0.45)

        Column {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            // Header Bar
            Item {
                width: parent.width
                height: 28

                Row {
                    spacing: 8
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: EditService.activeOp && EditService.activeOp.isDestructive ? "" : ""
                        font.family: HKS.fontFamily
                        font.pixelSize: 16
                        color: EditService.activeOp && EditService.activeOp.isDestructive ? HKS.critical : HKS.accent
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: EditService.activeOp ? EditService.activeOp.title : "Confirm Edit"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeLarge
                        font.weight: Font.Bold
                        color: HKS.fg
                    }
                }

                // Close Button
                Rectangle {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24
                    height: 24
                    radius: 4
                    color: closeMa.containsMouse ? HKS.alpha(HKS.muted, 0.2) : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.family: HKS.fontFamily
                        font.pixelSize: 12
                        color: HKS.muted
                    }

                    MouseArea {
                        id: closeMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: EditService.cancelDialog()
                    }
                }
            }

            // Target Keybind Info Banner
            Rectangle {
                width: parent.width
                height: 40
                radius: 6
                color: HKS.alpha(HKS.surface, 0.8)
                border.width: 1
                border.color: HKS.alpha(HKS.muted, 0.2)

                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10

                    Text {
                        text: "Target:"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        font.weight: Font.Bold
                        color: HKS.muted
                    }

                    // Shortcut Target (when operation targets a keybinding)
                    ShortcutKeys {
                        id: targetShortcutKeys
                        anchors.verticalCenter: parent.verticalCenter
                        parts: (EditService.activeOp && EditService.activeOp.parts) ? EditService.activeOp.parts : []
                        visible: !!(EditService.activeOp && EditService.activeOp.parts && EditService.activeOp.parts.length > 0)
                    }

                    // Text Label Fallback (e.g. for restore operations)
                    Rectangle {
                        id: targetLabelRect
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !targetShortcutKeys.visible
                        height: 22
                        width: targetLabel.implicitWidth + 12
                        radius: 4
                        color: HKS.alpha(HKS.accent, 0.15)
                        border.width: 1
                        border.color: HKS.alpha(HKS.accent, 0.3)

                        Text {
                            id: targetLabel
                            anchors.centerIn: parent
                            text: EditService.activeOp ? EditService.activeOp.label : ""
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            font.weight: Font.Bold
                            color: HKS.accent
                        }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: EditService.activeOp ? EditService.activeOp.description : ""
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                        elide: Text.ElideRight
                        width: Math.max(100, parent.width - (targetShortcutKeys.visible ? targetShortcutKeys.width : targetLabelRect.width) - 80)
                    }
                }
            }

            // Verification Badges Row
            Row {
                width: parent.width
                spacing: 8

                // 1. Hyprland Verify Badge
                Rectangle {
                    property var v: EditService.previewData ? EditService.previewData.verify : null
                    property bool isOk: v && (v.ok === true)
                    property bool isFailed: v && (v.ok === false)
                    property bool isSkipped: !v || (v.ok === null)

                    height: 22
                    width: verifyTxt.implicitWidth + 14
                    radius: 4
                    color: isOk
                        ? HKS.alpha(HKS.accent, 0.15)
                        : (isFailed ? HKS.alpha(HKS.critical, 0.15) : HKS.alpha(HKS.warning, 0.15))
                    border.width: 1
                    border.color: isOk
                        ? HKS.alpha(HKS.accent, 0.4)
                        : (isFailed ? HKS.alpha(HKS.critical, 0.4) : HKS.alpha(HKS.warning, 0.4))

                    Row {
                        id: verifyTxt
                        anchors.centerIn: parent
                        spacing: 4
                        Text {
                            text: parent.parent.isOk ? "" : (parent.parent.isFailed ? "" : "")
                            font.family: HKS.fontFamily
                            font.pixelSize: 10
                            color: parent.parent.isOk
                                ? HKS.accent
                                : (parent.parent.isFailed ? HKS.critical : HKS.warning)
                        }
                        Text {
                            text: parent.parent.isOk
                                ? "Hyprland syntax: OK"
                                : (parent.parent.isFailed ? "Hyprland verify: FAILED" : "Hyprland verify: skipped")
                            font.family: HKS.fontFamily
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            color: parent.parent.isOk
                                ? HKS.accent
                                : (parent.parent.isFailed ? HKS.critical : HKS.warning)
                        }
                    }
                }

                // 2. Bind Set Diff Badge
                Rectangle {
                    property var bc: EditService.previewData ? EditService.previewData.bind_comparison : null
                    visible: !!bc
                    height: 22
                    width: bcTxt.implicitWidth + 14
                    radius: 4
                    color: HKS.alpha(HKS.surface, 0.8)
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.3)

                    Text {
                        id: bcTxt
                        anchors.centerIn: parent
                        text: {
                            var b = parent.bc;
                            if (!b) return "";
                            return "Binds: " + b.before_count + " → " + b.after_count +
                                " (+" + b.added_count + " / -" + b.removed_count + ")";
                        }
                        font.family: HKS.fontFamily
                        font.pixelSize: 10
                        color: HKS.fg
                    }
                }
            }

            // Warnings Box (if companion warning or other warning exists)
            Rectangle {
                id: warningBox
                width: parent.width
                height: warnCol.implicitHeight + 14
                radius: 6
                color: HKS.alpha(HKS.warning, 0.1)
                border.width: 1
                border.color: HKS.alpha(HKS.warning, 0.35)
                visible: !!(EditService.previewData && EditService.previewData.warnings && EditService.previewData.warnings.length > 0)

                Row {
                    id: warnCol
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    Text {
                        text: ""
                        font.family: HKS.fontFamily
                        font.pixelSize: 12
                        color: HKS.warning
                    }

                    Text {
                        width: parent.width - 24
                        text: (EditService.previewData && EditService.previewData.warnings) ? EditService.previewData.warnings.join("\n") : ""
                        font.family: HKS.fontFamily
                        font.pixelSize: 11
                        color: HKS.warning
                        wrapMode: Text.Wrap
                    }
                }
            }

            // Diff Title
            Text {
                text: "Proposed Changes (Unified Diff):"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                font.weight: Font.DemiBold
                color: HKS.muted
            }

            // Diff Viewer Box
            Rectangle {
                id: diffBox
                width: parent.width
                height: Math.max(120, parent.height - y - bottomControlArea.height - 12)
                radius: 6
                color: HKS.alpha(HKS.elevated, 0.6)
                border.width: 1
                border.color: HKS.alpha(HKS.muted, 0.25)
                clip: true

                ListView {
                    id: diffListView
                    anchors.fill: parent
                    anchors.margins: 10
                    model: (EditService.previewData && EditService.previewData.diff)
                        ? EditService.previewData.diff.split("\n")
                        : ["(no diff generated)"]
                    spacing: 2
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {
                        active: true
                        width: 6
                    }

                    delegate: Text {
                        width: diffListView.width - 12
                        text: modelData
                        font.family: HKS.fontFamily
                        font.pixelSize: 11
                        font.bold: modelData.startsWith("+++") || modelData.startsWith("---") || modelData.startsWith("@@")
                        color: {
                            if (modelData.startsWith("+++") || modelData.startsWith("---")) return HKS.fg;
                            if (modelData.startsWith("+")) return "#4ade80";
                            if (modelData.startsWith("-")) return HKS.critical;
                            if (modelData.startsWith("@@")) return "#38bdf8";
                            return HKS.alpha(HKS.fg, 0.7);
                        }
                    }
                }
            }

            // Bottom Control Area (Delete checkbox confirmation + Action buttons)
            Column {
                id: bottomControlArea
                width: parent.width
                spacing: 10

                // Second confirmation for Delete
                Row {
                    spacing: 8
                    visible: !!(EditService.activeOp && EditService.activeOp.action === "delete")

                    Rectangle {
                        id: checkRect
                        width: 18
                        height: 18
                        radius: 3
                        color: root.deleteConfirmed ? HKS.critical : HKS.alpha(HKS.surface, 0.8)
                        border.width: 1
                        border.color: root.deleteConfirmed ? HKS.critical : HKS.alpha(HKS.muted, 0.4)

                        Text {
                            anchors.centerIn: parent
                            text: ""
                            font.family: HKS.fontFamily
                            font.pixelSize: 11
                            color: "#ffffff"
                            visible: root.deleteConfirmed
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.deleteConfirmed = !root.deleteConfirmed
                        }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "I understand this permanently deletes the keybinding line"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        font.weight: Font.DemiBold
                        color: root.deleteConfirmed ? HKS.fg : HKS.critical

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.deleteConfirmed = !root.deleteConfirmed
                        }
                    }
                }

                // Action Buttons Row
                Item {
                    width: parent.width
                    height: 32

                    // Left side: Dry run indicator if active
                    Row {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        visible: EditService.dryRunOnly

                        Text {
                            text: ""
                            font.family: HKS.fontFamily
                            font.pixelSize: 12
                            color: HKS.muted
                        }
                        Text {
                            text: "Safe mode active (read-only environment)"
                            font.family: HKS.fontFamily
                            font.pixelSize: 10
                            color: HKS.muted
                            font.italic: true
                        }
                    }

                    // Right side buttons
                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        // Cancel Button
                        Rectangle {
                            width: cancelTxt.implicitWidth + 24
                            height: 32
                            radius: 6
                            color: cancelMa.containsMouse ? HKS.alpha(HKS.muted, 0.25) : HKS.alpha(HKS.muted, 0.12)
                            border.width: 1
                            border.color: HKS.alpha(HKS.muted, 0.3)

                            Text {
                                id: cancelTxt
                                anchors.centerIn: parent
                                text: "Cancel"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                color: HKS.fg
                            }

                            MouseArea {
                                id: cancelMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: EditService.cancelDialog()
                            }
                        }

                        // Apply Button
                        Rectangle {
                            property bool isDeleteBlocked: (EditService.activeOp && EditService.activeOp.action === "delete") && !root.deleteConfirmed
                            property bool canApply: !EditService.dryRunOnly && !isDeleteBlocked && !EditService.busy

                            width: applyTxt.implicitWidth + 24
                            height: 32
                            radius: 6
                            color: {
                                if (EditService.dryRunOnly) return HKS.alpha(HKS.muted, 0.15);
                                if (!canApply) return HKS.alpha(HKS.muted, 0.2);
                                if (applyMa.containsMouse) {
                                    return EditService.activeOp && EditService.activeOp.isDestructive
                                        ? HKS.critical
                                        : HKS.accent;
                                }
                                return EditService.activeOp && EditService.activeOp.isDestructive
                                    ? HKS.alpha(HKS.critical, 0.8)
                                    : HKS.alpha(HKS.accent, 0.85);
                            }
                            border.width: 1
                            border.color: canApply
                                ? (EditService.activeOp && EditService.activeOp.isDestructive ? HKS.critical : HKS.accent)
                                : HKS.alpha(HKS.muted, 0.3)

                            Text {
                                id: applyTxt
                                anchors.centerIn: parent
                                text: {
                                    if (EditService.dryRunOnly) return "Apply (disabled in test mode)";
                                    if (EditService.busy) return "Applying...";
                                    if (EditService.activeOp && EditService.activeOp.isDestructive) return "Apply & Reload";
                                    return "Apply & Reload";
                                }
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                font.weight: Font.DemiBold
                                color: parent.canApply ? "#ffffff" : HKS.muted
                            }

                            MouseArea {
                                id: applyMa
                                anchors.fill: parent
                                hoverEnabled: parent.canApply
                                cursorShape: parent.canApply ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: {
                                    if (parent.canApply) {
                                        EditService.confirmApply();
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
