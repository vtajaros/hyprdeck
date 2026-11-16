import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    ThemesControlLogic {
        id: themesLogic
    }

    Column {
        anchors.fill: parent
        anchors.margins: HKS.space24
        spacing: HKS.space12

        // Header
        Row {
            width: parent.width
            spacing: HKS.space12

            Column {
                width: Math.max(200, parent.width - headerActions.width - HKS.space12)
                spacing: 4

                Text {
                    text: "Themes"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: "Wallpaper, GTK, icons, cursor, Qt6ct, and consistency checks."
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: HKS.muted
                }
            }

            Row {
                id: headerActions
                anchors.verticalCenter: parent.verticalCenter
                spacing: HKS.space8

                ActionButton {
                    text: "Revert to previous"
                    compact: true
                    visible: ThemesService.hasSessionChanges
                    enabled: !ThemesService.busy
                    onClicked: ThemesService.revertToPrevious()
                }

                ActionButton {
                    text: ThemesService.busy ? "Applying..." : "Refresh"
                    compact: true
                    enabled: !ThemesService.busy
                    onClicked: ThemesService.reload(false)
                }
            }
        }

        // Error banner
        Rectangle {
            visible: ThemesService.error.length > 0
            width: parent.width
            height: errTxt.implicitHeight + 16
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.critical, 0.14)
            border.width: 1
            border.color: HKS.alpha(HKS.critical, 0.5)

            Text {
                id: errTxt
                anchors.fill: parent
                anchors.margins: 8
                text: ThemesService.error
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Warning / status banner
        Rectangle {
            visible: ThemesService.warningMessage.length > 0
            width: parent.width
            height: warnMsgTxt.implicitHeight + 16
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.warning, 0.14)
            border.width: 1
            border.color: HKS.alpha(HKS.warning, 0.5)

            Text {
                id: warnMsgTxt
                anchors.fill: parent
                anchors.margins: 8
                text: ThemesService.warningMessage
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.warning
                wrapMode: Text.WordWrap
            }
        }

        Flickable {
            id: flick
            width: parent.width
            height: Math.max(120, parent.height - y)
            clip: true
            contentWidth: width
            contentHeight: contentCol.implicitHeight
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: contentCol
                width: flick.width
                spacing: HKS.space16

                // Consistency & Conflicts Panel
                Column {
                    width: parent.width
                    spacing: HKS.space8
                    visible: ThemesService.conflicts.length > 0

                    Text {
                        text: "Consistency & Conflicts (" + ThemesService.conflicts.length + ")"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Repeater {
                        model: ThemesService.conflicts
                        delegate: Rectangle {
                            id: confCard
                            required property var modelData
                            width: contentCol.width
                            height: confCol.implicitHeight + 20
                            radius: HKS.radiusSmall
                            color: HKS.surface
                            border.width: 1
                            border.color: confCard.modelData.severity === "warning"
                                ? HKS.alpha(HKS.warning, 0.5)
                                : HKS.alpha(HKS.muted, 0.25)

                            Column {
                                id: confCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 10
                                spacing: 4

                                Text {
                                    text: String(confCard.modelData.explanation || "")
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    font.weight: Font.DemiBold
                                    color: confCard.modelData.severity === "warning" ? HKS.warning : HKS.fg
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                }

                                Text {
                                    text: String(confCard.modelData.fix_hint || "")
                                    font.family: HKS.fontFamily
                                    font.pixelSize: 11
                                    color: HKS.muted
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                }

                                Rectangle {
                                    visible: !!(confCard.modelData.copy_text && String(confCard.modelData.copy_text).length > 0)
                                    width: parent.width
                                    height: 28
                                    radius: 4
                                    color: HKS.elevated

                                    TextInput {
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        readOnly: true
                                        selectByMouse: true
                                        text: String(confCard.modelData.copy_text || "")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.fg
                                        clip: true
                                    }
                                }
                            }
                        }
                    }
                }

                // Wallpaper (Read-only + Open Picker)
                Rectangle {
                    width: parent.width
                    height: wpRow.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Row {
                        id: wpRow
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: HKS.space12
                        spacing: HKS.space12

                        Column {
                            width: Math.max(180, parent.width - wpBtn.width - HKS.space12)
                            spacing: 2

                            Text {
                                text: "Wallpaper"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSize
                                font.weight: Font.DemiBold
                                color: HKS.fg
                            }
                            Text {
                                text: ThemesService.wallpaper.path
                                    ? (String(ThemesService.wallpaper.path) + " (" + String(ThemesService.wallpaper.source || "none") + ")")
                                    : "No active wallpaper detected."
                                font.family: HKS.fontFamily
                                font.pixelSize: 11
                                color: HKS.muted
                                elide: Text.ElideMiddle
                                width: parent.width
                            }
                        }

                        ActionButton {
                            id: wpBtn
                            text: "Open wallpaper picker"
                            variant: "accent"
                            compact: true
                            enabled: !ThemesService.busy
                            onClicked: ThemesService.openWallpaperPicker()
                        }
                    }
                }

                // GTK Theme & Color Scheme (read-only)
                Rectangle {
                    width: parent.width
                    height: gtkCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: gtkCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: HKS.space8

                        Text {
                            text: "GTK Theme (" + String(ThemesService.gtk.effective_theme || "unset") + ") · Color scheme: " + ThemesService.colorScheme
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.DemiBold
                            color: HKS.fg
                        }

                        Flow {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: ThemesService.gtk.installed || []
                                delegate: ActionButton {
                                    required property string modelData
                                    text: modelData
                                    variant: ThemesService.gtk.gsettings_theme === modelData ? "accent" : "secondary"
                                    compact: true
                                    enabled: !ThemesService.busy
                                    onClicked: ThemesService.setGtkTheme(modelData)
                                }
                            }
                        }
                    }
                }

                // Icons
                Rectangle {
                    width: parent.width
                    height: iconCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: iconCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: HKS.space8

                        Text {
                            text: "Icon Theme (" + String(ThemesService.icons.gsettings_theme || "unset") + ") — " + themesLogic.iconBadgeText(ThemesService.icons.gsettings_theme)
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.DemiBold
                            color: HKS.fg
                        }

                        Flow {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: ThemesService.icons.installed || []
                                delegate: ActionButton {
                                    required property string modelData
                                    text: modelData === "Papirus-Dynamic" ? "Papirus-Dynamic ★" : modelData
                                    variant: ThemesService.icons.gsettings_theme === modelData ? "accent" : "secondary"
                                    compact: true
                                    enabled: !ThemesService.busy
                                    onClicked: ThemesService.setIconTheme(modelData)
                                }
                            }
                        }
                    }
                }

                // Cursor (live)
                Rectangle {
                    width: parent.width
                    height: curCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: curCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: HKS.space8

                        Row {
                            width: parent.width
                            spacing: HKS.space12

                            Text {
                                width: Math.max(160, parent.width - curSizeRow.width - HKS.space12)
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Cursor (" + String(ThemesService.cursor.gsettings_theme || "unset") + ", size " + String(ThemesService.cursor.size || 24) + ") · Applies live"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSize
                                font.weight: Font.DemiBold
                                color: HKS.fg
                            }

                            Row {
                                id: curSizeRow
                                spacing: 6
                                ActionButton {
                                    text: "-"
                                    compact: true
                                    enabled: !ThemesService.busy && Number(ThemesService.cursor.size || 24) > 16
                                    onClicked: ThemesService.setCursor(
                                        ThemesService.cursor.gsettings_theme || "Pop",
                                        themesLogic.clampCursorSize(Number(ThemesService.cursor.size || 24) - 4)
                                    )
                                }
                                ActionButton {
                                    text: "+"
                                    compact: true
                                    enabled: !ThemesService.busy && Number(ThemesService.cursor.size || 24) < 64
                                    onClicked: ThemesService.setCursor(
                                        ThemesService.cursor.gsettings_theme || "Pop",
                                        themesLogic.clampCursorSize(Number(ThemesService.cursor.size || 24) + 4)
                                    )
                                }
                            }
                        }

                        Flow {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: ThemesService.cursor.installed || []
                                delegate: ActionButton {
                                    required property string modelData
                                    text: modelData
                                    variant: ThemesService.cursor.gsettings_theme === modelData ? "accent" : "secondary"
                                    compact: true
                                    enabled: !ThemesService.busy
                                    onClicked: ThemesService.setCursor(modelData, Number(ThemesService.cursor.size || 24))
                                }
                            }
                        }
                    }
                }

                // Qt6ct
                Rectangle {
                    width: parent.width
                    height: qtCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: qtCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: HKS.space8

                        Text {
                            text: "Qt6ct Style (" + String(ThemesService.qt.style || "unset") + ") · Qt apps pick this up after restart"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.DemiBold
                            color: HKS.fg
                        }

                        Flow {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: ThemesService.qt.installed_styles || []
                                delegate: ActionButton {
                                    required property string modelData
                                    text: modelData
                                    variant: ThemesService.qt.style === modelData ? "accent" : "secondary"
                                    compact: true
                                    enabled: !ThemesService.busy
                                    onClicked: ThemesService.setQt(modelData, null, null)
                                }
                            }
                        }

                        Text {
                            text: "Qt6ct Color Schemes"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                        }

                        Flow {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: ThemesService.qt.installed_color_schemes || []
                                delegate: ActionButton {
                                    required property var modelData
                                    text: String(modelData.name || "")
                                    variant: ThemesService.qt.color_scheme_path === modelData.path ? "accent" : "secondary"
                                    compact: true
                                    enabled: !ThemesService.busy
                                    onClicked: ThemesService.setQt(null, null, modelData.path)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
