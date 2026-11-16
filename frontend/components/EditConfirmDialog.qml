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
        radius: Deck.radius
        color: Deck.bg
        border.width: 1
        border.color: EditService.activeOp && EditService.activeOp.isDestructive
            ? Deck.alpha(Deck.critical, 0.5)
            : Deck.alpha(Deck.accent, 0.45)

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
                        font.family: Deck.fontFamily
                        font.pixelSize: 16
                        color: EditService.activeOp && EditService.activeOp.isDestructive ? Deck.critical : Deck.accent
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: EditService.activeOp ? EditService.activeOp.title : "Confirm Edit"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeLarge
                        font.weight: Font.Bold
                        color: Deck.fg
                    }
                }

                // Close Button
                Rectangle {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24
                    height: 24
                    radius: 4
                    color: closeMa.containsMouse ? Deck.alpha(Deck.muted, 0.2) : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.family: Deck.fontFamily
                        font.pixelSize: 12
                        color: Deck.muted
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
                color: Deck.alpha(Deck.surface, 0.8)
                border.width: 1
                border.color: Deck.alpha(Deck.muted, 0.2)

                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10

                    Text {
                        text: "Target:"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.Bold
                        color: Deck.muted
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
                        color: Deck.alpha(Deck.accent, 0.15)
                        border.width: 1
                        border.color: Deck.alpha(Deck.accent, 0.3)

                        Text {
                            id: targetLabel
                            anchors.centerIn: parent
                            text: EditService.activeOp ? EditService.activeOp.label : ""
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            font.weight: Font.Bold
                            color: Deck.accent
                        }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: EditService.activeOp ? EditService.activeOp.description : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
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
                        ? Deck.alpha(Deck.accent, 0.15)
                        : (isFailed ? Deck.alpha(Deck.critical, 0.15) : Deck.alpha(Deck.warning, 0.15))
                    border.width: 1
                    border.color: isOk
                        ? Deck.alpha(Deck.accent, 0.4)
                        : (isFailed ? Deck.alpha(Deck.critical, 0.4) : Deck.alpha(Deck.warning, 0.4))

                    Row {
                        id: verifyTxt
                        anchors.centerIn: parent
                        spacing: 4
                        Text {
                            text: parent.parent.isOk ? "" : (parent.parent.isFailed ? "" : "")
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: parent.parent.isOk
                                ? Deck.accent
                                : (parent.parent.isFailed ? Deck.critical : Deck.warning)
                        }
                        Text {
                            text: parent.parent.isOk
                                ? "Hyprland syntax: OK"
                                : (parent.parent.isFailed ? "Hyprland verify: FAILED" : "Hyprland verify: skipped")
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            color: parent.parent.isOk
                                ? Deck.accent
                                : (parent.parent.isFailed ? Deck.critical : Deck.warning)
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
                    color: Deck.alpha(Deck.surface, 0.8)
                    border.width: 1
                    border.color: Deck.alpha(Deck.muted, 0.3)

                    Text {
                        id: bcTxt
                        anchors.centerIn: parent
                        text: {
                            var b = parent.bc;
                            if (!b) return "";
                            return "Binds: " + b.before_count + " → " + b.after_count +
                                " (+" + b.added_count + " / -" + b.removed_count + ")";
                        }
                        font.family: Deck.fontFamily
                        font.pixelSize: 10
                        color: Deck.fg
                    }
                }

                // 3. Dispatcher Preserved Badge
                Rectangle {
                    visible: !!(EditService.previewData && EditService.previewData.dispatcher_unchanged)
                    height: 22
                    width: dspPreservedTxt.implicitWidth + 14
                    radius: 4
                    color: Deck.alpha(Deck.accent, 0.15)
                    border.width: 1
                    border.color: Deck.alpha(Deck.accent, 0.4)

                    Row {
                        id: dspPreservedTxt
                        anchors.centerIn: parent
                        spacing: 4
                        Text {
                            text: ""
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: Deck.accent
                        }
                        Text {
                            text: "Dispatcher preserved as written"
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            color: Deck.accent
                        }
                    }
                }

                // 4. Target File and Line Badge (when adding)
                Rectangle {
                    visible: !!(EditService.activeOp && EditService.activeOp.action === "add" && EditService.previewData && EditService.previewData.file_to_modify)
                    height: 22
                    width: fileLineTxt.implicitWidth + 14
                    radius: 4
                    color: Deck.alpha(Deck.surface, 0.8)
                    border.width: 1
                    border.color: Deck.alpha(Deck.muted, 0.3)

                    Row {
                        id: fileLineTxt
                        anchors.centerIn: parent
                        spacing: 4
                        Text {
                            text: ""
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: Deck.muted
                        }
                        Text {
                            text: {
                                if (!EditService.previewData || !EditService.previewData.file_to_modify) return "";
                                var f = EditService.previewData.file_to_modify.split("/").pop();
                                var l = EditService.previewData.insert_line;
                                return f + (l ? (":" + l) : "");
                            }
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: Deck.fg
                        }
                    }
                }
            }

            // Anchor Created Notice Banner
            Rectangle {
                width: parent.width
                height: 28
                radius: 6
                color: Deck.alpha(Deck.accent, 0.12)
                border.width: 1
                border.color: Deck.alpha(Deck.accent, 0.4)
                visible: !!(EditService.activeOp && EditService.activeOp.action === "add" && EditService.previewData && EditService.previewData.anchor_created)

                Row {
                    anchors.centerIn: parent
                    spacing: 8
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 11
                        color: Deck.accent
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Notice: custom binds anchor block ('# HKS: custom binds') will be created in this file."
                        font.family: Deck.fontFamily
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        color: Deck.accent
                    }
                }
            }

            // Sidecar Migration Notice Banner
            Rectangle {
                property var mig: EditService.previewData ? EditService.previewData.sidecar_migration : null
                property var scWarn: EditService.previewData ? EditService.previewData.sidecar_warning : null
                width: parent.width
                height: Math.max(28, scRow.implicitHeight + 10)
                radius: 6
                visible: !!(mig && mig.has_override) || !!scWarn
                color: (scWarn || (mig && mig.collision)) ? Deck.alpha(Deck.warning, 0.15) : Deck.alpha(Deck.accent, 0.12)
                border.width: 1
                border.color: (scWarn || (mig && mig.collision)) ? Deck.alpha(Deck.warning, 0.4) : Deck.alpha(Deck.accent, 0.4)

                Row {
                    id: scRow
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    spacing: 8
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: (parent.parent.scWarn || (parent.parent.mig && parent.parent.mig.collision)) ? "" : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 11
                        color: (parent.parent.scWarn || (parent.parent.mig && parent.parent.mig.collision)) ? Deck.warning : Deck.accent
                    }
                    Text {
                        width: parent.width - 24
                        text: {
                            if (parent.parent.scWarn && parent.parent.scWarn.message) {
                                return parent.parent.scWarn.message;
                            }
                            if (parent.parent.mig && parent.parent.mig.collision) {
                                return "Custom description collision: destination shortcut already has a custom override. The previous description will be preserved on the old shortcut.";
                            }
                            return "Custom description will follow this bind to new shortcut";
                        }
                        font.family: Deck.fontFamily
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        color: (parent.parent.scWarn || (parent.parent.mig && parent.parent.mig.collision)) ? Deck.warning : Deck.accent
                        wrapMode: Text.Wrap
                    }
                }
            }

            // Conflicts Warning Banner (if candidate conflicts with existing active binds)
            Rectangle {
                id: conflictBox
                width: parent.width
                height: confCol.implicitHeight + 14
                radius: 6
                color: Deck.alpha(Deck.warning, 0.12)
                border.width: 1
                border.color: Deck.alpha(Deck.warning, 0.5)
                visible: !!(EditService.activeOp && EditService.activeOp.conflicts && EditService.activeOp.conflicts.length > 0)

                Row {
                    id: confCol
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    Text {
                        text: ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 13
                        color: Deck.warning
                    }

                    Column {
                        width: parent.width - 24
                        spacing: 2
                        Text {
                            text: "Conflict Notice: New shortcut conflicts with existing bind(s):"
                            font.family: Deck.fontFamily
                            font.pixelSize: 11
                            font.weight: Font.Bold
                            color: Deck.warning
                        }
                        Repeater {
                            model: (EditService.activeOp && EditService.activeOp.conflicts) ? EditService.activeOp.conflicts : []
                            Text {
                                width: parent.width
                                text: "• " + modelData.shortcut + " — " + modelData.description + " (" + modelData.file + ":" + modelData.line + ")"
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: Deck.fg
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            // Warnings Box (if companion warning or other warning exists)
            Rectangle {
                id: warningBox
                width: parent.width
                height: warnCol.implicitHeight + 14
                radius: 6
                color: Deck.alpha(Deck.warning, 0.1)
                border.width: 1
                border.color: Deck.alpha(Deck.warning, 0.35)
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
                        font.family: Deck.fontFamily
                        font.pixelSize: 12
                        color: Deck.warning
                    }

                    Text {
                        width: parent.width - 24
                        text: (EditService.previewData && EditService.previewData.warnings) ? EditService.previewData.warnings.join("\n") : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 11
                        color: Deck.warning
                        wrapMode: Text.Wrap
                    }
                }
            }

            // Diff Title
            Text {
                text: "Proposed Changes (Unified Diff):"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                font.weight: Font.DemiBold
                color: Deck.muted
            }

            // Diff Viewer Box
            Rectangle {
                id: diffBox
                width: parent.width
                height: Math.max(120, parent.height - y - bottomControlArea.height - 12)
                radius: 6
                color: Deck.alpha(Deck.elevated, 0.6)
                border.width: 1
                border.color: Deck.alpha(Deck.muted, 0.25)
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
                        font.family: Deck.fontFamily
                        font.pixelSize: 11
                        font.bold: modelData.startsWith("+++") || modelData.startsWith("---") || modelData.startsWith("@@")
                        color: {
                            if (modelData.startsWith("+++") || modelData.startsWith("---")) return Deck.fg;
                            if (modelData.startsWith("+")) return "#4ade80";
                            if (modelData.startsWith("-")) return Deck.critical;
                            if (modelData.startsWith("@@")) return "#38bdf8";
                            return Deck.alpha(Deck.fg, 0.7);
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
                        color: root.deleteConfirmed ? Deck.critical : Deck.alpha(Deck.surface, 0.8)
                        border.width: 1
                        border.color: root.deleteConfirmed ? Deck.critical : Deck.alpha(Deck.muted, 0.4)

                        Text {
                            anchors.centerIn: parent
                            text: ""
                            font.family: Deck.fontFamily
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
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.DemiBold
                        color: root.deleteConfirmed ? Deck.fg : Deck.critical

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
                            font.family: Deck.fontFamily
                            font.pixelSize: 12
                            color: Deck.muted
                        }
                        Text {
                            text: "Safe mode active (read-only environment)"
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: Deck.muted
                            font.italic: true
                        }
                    }

                    // Right side buttons
                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        // Cancel Button
                        ActionButton {
                            variant: "neutral"
                            text: "Cancel"
                            onClicked: EditService.cancelDialog()
                        }

                        // Apply Button
                        ActionButton {
                            property bool isDeleteBlocked: (EditService.activeOp && EditService.activeOp.action === "delete") && !root.deleteConfirmed
                            property bool canApply: !EditService.dryRunOnly && !isDeleteBlocked && !EditService.busy

                            variant: (EditService.activeOp && EditService.activeOp.action === "delete") ? "danger" : "accent"
                            enabled: canApply
                            text: {
                                if (EditService.dryRunOnly) return "Apply (disabled in test mode)";
                                if (EditService.busy) return "Applying...";
                                if (EditService.activeOp && EditService.activeOp.action === "add") return "Add & Reload";
                                return "Apply & Reload";
                            }
                            onClicked: EditService.confirmApply()
                        }
                    }
                }
            }
        }
    }
}
