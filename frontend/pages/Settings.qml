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
            anchors.margins: Deck.space24
            spacing: Deck.space16

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
                        font.family: Deck.fontFamily
                        font.pixelSize: 20
                        color: Deck.accent
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Settings & Information"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeLarge
                        font.weight: Font.Bold
                        color: Deck.fg
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Deck.alpha(Deck.muted, 0.2)
            }

            // Section 1: Custom Descriptions (Sidecar)
            Text {
                text: "Custom Descriptions (Sidecar)"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.Bold
                color: Deck.fg
            }

            Rectangle {
                width: parent.width
                height: sidecarCol.implicitHeight + 24
                radius: Deck.radiusSmall
                color: Deck.surface
                border.width: 1
                border.color: Deck.alpha(Deck.muted, 0.2)

                Column {
                    id: sidecarCol
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10

                    Text {
                        width: parent.width
                        text: "Sidecar overrides store custom descriptions and categories in ~/.config/hyprdeck/descriptions.json without modifying your Hyprland configuration files."
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                        wrapMode: Text.WordWrap
                    }

                    Row {
                        spacing: 16

                        // Stat 1: Total Overrides
                        Rectangle {
                            height: 28
                            width: totalTxt.implicitWidth + 20
                            radius: 4
                            color: Deck.alpha(Deck.accent, 0.15)
                            border.width: 1
                            border.color: Deck.alpha(Deck.accent, 0.3)

                            Text {
                                id: totalTxt
                                anchors.centerIn: parent
                                text: SidecarService.overrideCount + " total overrides"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                font.weight: Font.DemiBold
                                color: Deck.accent
                            }
                        }

                        // Stat 2: Orphans
                        Rectangle {
                            height: 28
                            width: orphanStatTxt.implicitWidth + 20
                            radius: 4
                            color: SidecarService.orphanCount > 0 ? Deck.alpha(Deck.warning, 0.15) : Deck.alpha(Deck.muted, 0.15)
                            border.width: 1
                            border.color: SidecarService.orphanCount > 0 ? Deck.alpha(Deck.warning, 0.4) : Deck.alpha(Deck.muted, 0.3)

                            Text {
                                id: orphanStatTxt
                                anchors.centerIn: parent
                                text: SidecarService.orphanCount + " orphaned overrides"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                font.weight: Font.DemiBold
                                color: SidecarService.orphanCount > 0 ? Deck.warning : Deck.muted
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
                            color: Deck.alpha(Deck.muted, 0.15)
                        }

                        Text {
                            text: "Orphaned Overrides (no matching active or disabled keybinding):"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            font.weight: Font.DemiBold
                            color: Deck.warning
                        }

                        Repeater {
                            model: SidecarService.orphans
                            delegate: Rectangle {
                                width: parent.width
                                height: 44
                                radius: 4
                                color: Deck.alpha(Deck.elevated, 0.5)
                                border.width: 1
                                border.color: Deck.alpha(Deck.warning, 0.25)

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
                                        font.family: Deck.fontFamily
                                        font.pixelSize: Deck.fontSizeSmall
                                        font.weight: Font.DemiBold
                                        color: Deck.fg
                                        elide: Text.ElideRight
                                        width: Math.min(implicitWidth, 220)
                                    }

                                    // Category badge
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        height: 20
                                        width: orphanCatTxt.implicitWidth + 10
                                        radius: 10
                                        color: Deck.alpha(Deck.accent, 0.15)
                                        border.width: 1
                                        border.color: Deck.alpha(Deck.accent, 0.3)
                                        visible: !!modelData.category

                                        Text {
                                            id: orphanCatTxt
                                            anchors.centerIn: parent
                                            text: modelData.category || ""
                                            font.family: Deck.fontFamily
                                            font.pixelSize: 10
                                            color: Deck.accent
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
                                                font.family: Deck.fontFamily
                                                font.pixelSize: 11
                                                color: Deck.critical
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
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.Bold
                color: Deck.fg
            }

            Rectangle {
                width: parent.width
                height: infoCol.implicitHeight + 24
                radius: Deck.radiusSmall
                color: Deck.surface
                border.width: 1
                border.color: Deck.alpha(Deck.muted, 0.2)

                Column {
                    id: infoCol
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Flow {
                        width: parent.width
                        spacing: 8
                        Text { width: Math.min(140, parent.width); text: "Repository Root:"; color: Deck.muted; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall; font.weight: Font.Bold }
                        Text { width: Math.min(implicitWidth, parent.width); wrapMode: Text.WrapAnywhere; text: KeybindData.rootPath; color: Deck.fg; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall }
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Text { width: Math.min(140, parent.width); text: "Entrypoint:"; color: Deck.muted; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall; font.weight: Font.Bold }
                        Text { width: Math.min(implicitWidth, parent.width); wrapMode: Text.WrapAnywhere; text: KeybindData.environment ? (KeybindData.environment.entrypoint || "-") : "-"; color: Deck.fg; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall }
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Text { width: Math.min(140, parent.width); text: "Language:"; color: Deck.muted; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall; font.weight: Font.Bold }
                        Text { text: KeybindData.environment ? (KeybindData.environment.language || "-") : "-"; color: Deck.accent; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall }
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Text { width: Math.min(140, parent.width); text: "Hyprland Version:"; color: Deck.muted; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall; font.weight: Font.Bold }
                        Text { text: KeybindData.environment ? (KeybindData.environment.hyprland_version || "unknown") : "unknown"; color: Deck.fg; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall }
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Text {
                            width: Math.min(140, parent.width)
                            text: "Theme:"
                            color: Deck.muted
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            font.weight: Font.Bold
                        }

                        Flow {
                            width: Math.min(implicitWidth, parent.width)
                            spacing: 8

                            Rectangle {
                                height: 26
                                width: sysTxt.implicitWidth + 16
                                radius: Deck.radiusSmall
                                color: Deck.themeMode === "system" ? Deck.alpha(Deck.accent, 0.25) : Deck.alpha(Deck.elevated, 0.6)
                                border.width: 1
                                border.color: Deck.themeMode === "system" ? Deck.accent : Deck.alpha(Deck.muted, 0.25)

                                Text {
                                    id: sysTxt
                                    anchors.centerIn: parent
                                    text: "Follow system (Matugen)"
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    font.weight: Deck.themeMode === "system" ? Font.Bold : Font.Normal
                                    color: Deck.themeMode === "system" ? Deck.accent : Deck.fg
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: Deck.themeMode = "system"
                                }
                            }

                            Rectangle {
                                height: 26
                                width: graphTxt.implicitWidth + 16
                                radius: Deck.radiusSmall
                                color: Deck.themeMode === "graphite" ? Deck.alpha(Deck.accent, 0.25) : Deck.alpha(Deck.elevated, 0.6)
                                border.width: 1
                                border.color: Deck.themeMode === "graphite" ? Deck.accent : Deck.alpha(Deck.muted, 0.25)

                                Text {
                                    id: graphTxt
                                    anchors.centerIn: parent
                                    text: "Fixed graphite"
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    font.weight: Deck.themeMode === "graphite" ? Font.Bold : Font.Normal
                                    color: Deck.themeMode === "graphite" ? Deck.accent : Deck.fg
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: Deck.themeMode = "graphite"
                                }
                            }

                            Text {
                                height: 26
                                verticalAlignment: Text.AlignVCenter
                                text: "(in-memory only)"
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: Deck.alpha(Deck.muted, 0.6)
                            }
                        }
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Text { width: Math.min(140, parent.width); text: "Theme Source:"; color: Deck.muted; font.family: Deck.fontFamily; font.pixelSize: Deck.fontSizeSmall; font.weight: Font.Bold }
                        Text {
                            width: Math.min(implicitWidth, parent.width)
                            wrapMode: Text.WrapAnywhere
                            text: Deck.themeMode === "system"
                                ? "~/.config/quickshell/theme/colors.json (Matugen / Quickshell)"
                                : "Fixed graphite palette (offline defaults)"
                            color: Deck.fg
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                        }
                    }
                }
            }

            // Section 3: Active Palette Swatches
            Text {
                text: "Active Palette Swatches"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.Bold
                color: Deck.fg
            }

            Flow {
                width: parent.width
                spacing: 8
                Repeater {
                    model: [
                        { label: "bg", color: Deck.bg },
                        { label: "surface", color: Deck.surface },
                        { label: "elevated", color: Deck.elevated },
                        { label: "accent", color: Deck.accent },
                        { label: "fg", color: Deck.fg },
                        { label: "muted", color: Deck.muted },
                        { label: "warning", color: Deck.warning },
                        { label: "critical", color: Deck.critical }
                    ]
                    delegate: Column {
                        spacing: 4
                        Rectangle {
                            width: 44
                            height: 32
                            radius: 4
                            color: modelData.color
                            border.width: 1
                            border.color: Deck.alpha(Deck.muted, 0.3)
                        }
                        Text {
                            text: modelData.label
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: Deck.muted
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                    }
                }
            }
        }
    }
}
