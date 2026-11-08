import QtQuick
import QtQuick.Controls.Basic
import Quickshell
import "../theme"
import "../services"
import "../components"

Item {
    id: root

    property var confirmingDeleteOrphan: null

    onVisibleChanged: {
        if (visible) {
            SidecarService.loadOrphans();
            SidecarService.loadAllOverrides();
        }
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentCol.implicitHeight + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ScrollBar.vertical: ScrollBar {
            active: true
            width: 6
        }

        Column {
            id: contentCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: HKS.space24
            spacing: HKS.space16

            // Header Bar
            Item {
                width: parent.width
                height: 36

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 12

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: ""
                        font.family: HKS.fontFamily
                        font.pixelSize: 20
                        color: HKS.accent
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Settings & Information"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeLarge
                        font.weight: Font.Bold
                        color: HKS.fg
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: HKS.alpha(HKS.muted, 0.2)
            }

            // Section 1: Custom Descriptions (Sidecar)
            Text {
                text: "Custom Descriptions (Sidecar)"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSize
                font.weight: Font.Bold
                color: HKS.fg
            }

            Rectangle {
                width: parent.width
                height: sidecarCol.implicitHeight + 24
                radius: HKS.radiusSmall
                color: HKS.surface
                border.width: 1
                border.color: HKS.alpha(HKS.muted, 0.2)

                Column {
                    id: sidecarCol
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10

                    Text {
                        width: parent.width
                        text: "Sidecar overrides store custom descriptions and categories in ~/.config/hks/descriptions.json without modifying your Hyprland configuration files."
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                        wrapMode: Text.WordWrap
                    }

                    Row {
                        spacing: 16

                        // Stat 1: Total Overrides
                        Rectangle {
                            height: 28
                            width: totalTxt.implicitWidth + 20
                            radius: 4
                            color: HKS.alpha(HKS.accent, 0.15)
                            border.width: 1
                            border.color: HKS.alpha(HKS.accent, 0.3)

                            Text {
                                id: totalTxt
                                anchors.centerIn: parent
                                text: SidecarService.overrideCount + " total overrides"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                font.weight: Font.DemiBold
                                color: HKS.accent
                            }
                        }

                        // Stat 2: Orphans
                        Rectangle {
                            height: 28
                            width: orphanStatTxt.implicitWidth + 20
                            radius: 4
                            color: SidecarService.orphanCount > 0 ? HKS.alpha(HKS.warning, 0.15) : HKS.alpha(HKS.muted, 0.15)
                            border.width: 1
                            border.color: SidecarService.orphanCount > 0 ? HKS.alpha(HKS.warning, 0.4) : HKS.alpha(HKS.muted, 0.3)

                            Text {
                                id: orphanStatTxt
                                anchors.centerIn: parent
                                text: SidecarService.orphanCount + " orphaned overrides"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                font.weight: Font.DemiBold
                                color: SidecarService.orphanCount > 0 ? HKS.warning : HKS.muted
                            }
                        }
                    }

                    // Orphans List
                    Column {
                        width: parent.width
                        spacing: 8
                        visible: SidecarService.orphans.length > 0

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: HKS.alpha(HKS.muted, 0.15)
                        }

                        Text {
                            text: "Orphaned Overrides (no matching active or disabled keybinding):"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            font.weight: Font.DemiBold
                            color: HKS.warning
                        }

                        Repeater {
                            model: SidecarService.orphans
                            delegate: Rectangle {
                                width: parent.width
                                height: 44
                                radius: 4
                                color: HKS.alpha(HKS.elevated, 0.5)
                                border.width: 1
                                border.color: HKS.alpha(HKS.warning, 0.25)

                                Row {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 12
                                    anchors.right: actionRow.left
                                    anchors.rightMargin: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 12

                                    // Key combo
                                    ShortcutKeys {
                                        anchors.verticalCenter: parent.verticalCenter
                                        parts: {
                                            var m = (modelData.match && modelData.match.modifiers) ? modelData.match.modifiers.slice() : [];
                                            if (modelData.match && modelData.match.key) m.push(modelData.match.key);
                                            return m;
                                        }
                                    }

                                    // Description
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: modelData.description || ""
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        font.weight: Font.DemiBold
                                        color: HKS.fg
                                        elide: Text.ElideRight
                                        width: Math.min(implicitWidth, 220)
                                    }

                                    // Category badge
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        height: 20
                                        width: orphanCatTxt.implicitWidth + 10
                                        radius: 10
                                        color: HKS.alpha(HKS.accent, 0.15)
                                        border.width: 1
                                        border.color: HKS.alpha(HKS.accent, 0.3)
                                        visible: !!modelData.category

                                        Text {
                                            id: orphanCatTxt
                                            anchors.centerIn: parent
                                            text: modelData.category || ""
                                            font.family: HKS.fontFamily
                                            font.pixelSize: 10
                                            color: HKS.accent
                                        }
                                    }
                                }

                                // Delete confirmation vs Delete button
                                Row {
                                    id: actionRow
                                    anchors.right: parent.right
                                    anchors.rightMargin: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 8

                                    Item {
                                        visible: root.confirmingDeleteOrphan === modelData
                                        width: confirmRow.implicitWidth
                                        height: 26

                                        Row {
                                            id: confirmRow
                                            spacing: 6
                                            anchors.verticalCenter: parent.verticalCenter

                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: "Delete orphan?"
                                                font.family: HKS.fontFamily
                                                font.pixelSize: 11
                                                color: HKS.critical
                                            }

                                            ActionButton {
                                                variant: "danger"
                                                text: "Yes, delete"
                                                onClicked: {
                                                    SidecarService.deleteOrphan(modelData.match, function(success, res, err) {
                                                        root.confirmingDeleteOrphan = null;
                                                        if (success) {
                                                            EditService.showToast("Orphan override deleted", false);
                                                        } else {
                                                            EditService.showToast("Failed to delete orphan: " + (err || "error"), false);
                                                        }
                                                    });
                                                }
                                            }

                                            ActionButton {
                                                variant: "neutral"
                                                text: "Cancel"
                                                onClicked: root.confirmingDeleteOrphan = null
                                            }
                                        }
                                    }

                                    ActionButton {
                                        visible: root.confirmingDeleteOrphan !== modelData
                                        variant: "danger"
                                        iconText: ""
                                        text: "Delete"
                                        onClicked: root.confirmingDeleteOrphan = modelData
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Section 2: App / Config Details Card
            Text {
                text: "Environment & Configuration"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSize
                font.weight: Font.Bold
                color: HKS.fg
            }

            Rectangle {
                width: parent.width
                height: infoCol.implicitHeight + 24
                radius: HKS.radiusSmall
                color: HKS.surface
                border.width: 1
                border.color: HKS.alpha(HKS.muted, 0.2)

                Column {
                    id: infoCol
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Row {
                        spacing: 8
                        Text { width: 140; text: "Repository Root:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                        Text { text: KeybindData.rootPath; color: HKS.fg; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                    }
                    Row {
                        spacing: 8
                        Text { width: 140; text: "Entrypoint:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                        Text { text: KeybindData.environment ? (KeybindData.environment.entrypoint || "-") : "-"; color: HKS.fg; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                    }
                    Row {
                        spacing: 8
                        Text { width: 140; text: "Language:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                        Text { text: KeybindData.environment ? (KeybindData.environment.language || "-") : "-"; color: HKS.accent; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                    }
                    Row {
                        spacing: 8
                        Text { width: 140; text: "Hyprland Version:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                        Text { text: KeybindData.environment ? (KeybindData.environment.hyprland_version || "unknown") : "unknown"; color: HKS.fg; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall }
                    }
                    Row {
                        spacing: 8
                        Text {
                            width: 140
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Theme:"
                            color: HKS.muted
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            font.weight: Font.Bold
                        }

                        Row {
                            spacing: 8
                            anchors.verticalCenter: parent.verticalCenter

                            Rectangle {
                                height: 26
                                width: sysTxt.implicitWidth + 16
                                radius: HKS.radiusSmall
                                color: HKS.themeMode === "system" ? HKS.alpha(HKS.accent, 0.25) : HKS.alpha(HKS.elevated, 0.6)
                                border.width: 1
                                border.color: HKS.themeMode === "system" ? HKS.accent : HKS.alpha(HKS.muted, 0.25)

                                Text {
                                    id: sysTxt
                                    anchors.centerIn: parent
                                    text: "Follow system (Matugen)"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    font.weight: HKS.themeMode === "system" ? Font.Bold : Font.Normal
                                    color: HKS.themeMode === "system" ? HKS.accent : HKS.fg
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: HKS.themeMode = "system"
                                }
                            }

                            Rectangle {
                                height: 26
                                width: graphTxt.implicitWidth + 16
                                radius: HKS.radiusSmall
                                color: HKS.themeMode === "graphite" ? HKS.alpha(HKS.accent, 0.25) : HKS.alpha(HKS.elevated, 0.6)
                                border.width: 1
                                border.color: HKS.themeMode === "graphite" ? HKS.accent : HKS.alpha(HKS.muted, 0.25)

                                Text {
                                    id: graphTxt
                                    anchors.centerIn: parent
                                    text: "Fixed graphite"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    font.weight: HKS.themeMode === "graphite" ? Font.Bold : Font.Normal
                                    color: HKS.themeMode === "graphite" ? HKS.accent : HKS.fg
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: HKS.themeMode = "graphite"
                                }
                            }

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "(in-memory only)"
                                font.family: HKS.fontFamily
                                font.pixelSize: 10
                                color: HKS.alpha(HKS.muted, 0.6)
                            }
                        }
                    }
                    Row {
                        spacing: 8
                        Text { width: 140; text: "Theme Source:"; color: HKS.muted; font.family: HKS.fontFamily; font.pixelSize: HKS.fontSizeSmall; font.weight: Font.Bold }
                        Text {
                            text: HKS.themeMode === "system"
                                ? "~/.config/quickshell/theme/colors.json (Matugen / Quickshell)"
                                : "Fixed graphite palette (offline defaults)"
                            color: HKS.fg
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                        }
                    }
                }
            }

            // Section 3: Active Palette Swatches
            Text {
                text: "Active Palette Swatches"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSize
                font.weight: Font.Bold
                color: HKS.fg
            }

            Row {
                spacing: 8
                Repeater {
                    model: [
                        { label: "bg", color: HKS.bg },
                        { label: "surface", color: HKS.surface },
                        { label: "elevated", color: HKS.elevated },
                        { label: "accent", color: HKS.accent },
                        { label: "fg", color: HKS.fg },
                        { label: "muted", color: HKS.muted },
                        { label: "warning", color: HKS.warning },
                        { label: "critical", color: HKS.critical }
                    ]
                    delegate: Column {
                        spacing: 4
                        Rectangle {
                            width: 44
                            height: 32
                            radius: 4
                            color: modelData.color
                            border.width: 1
                            border.color: HKS.alpha(HKS.muted, 0.3)
                        }
                        Text {
                            text: modelData.label
                            font.family: HKS.fontFamily
                            font.pixelSize: 10
                            color: HKS.muted
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                    }
                }
            }
        }
    }
}
