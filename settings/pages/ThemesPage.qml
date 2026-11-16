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

    property bool showAllIcons: false
    property bool showAllCursors: false
    property bool expandConflicts: false

    PageViewport {
        id: viewport
        anchors.fill: parent

        header: PageHeader {
            title: "Themes"
            subtitle: "Wallpaper, GTK, icons, cursor, Qt6ct, and consistency checks."

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

        // Error banner
        Rectangle {
            visible: ThemesService.error.length > 0
            width: viewport.innerWidth
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
            width: viewport.innerWidth
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

        // Consistency & Conflicts Panel
        Column {
            width: viewport.innerWidth
            spacing: HKS.space8
            visible: ThemesService.conflicts.length > 0

            Item {
                id: confHdrBox
                width: parent.width
                readonly property bool wrapped: ResponsiveLogic.shouldWrapHeaderActions(
                    confHdrBox.width, confLblMetrics.advanceWidth, conflictToggleBtn.implicitWidth, HKS.space12
                )
                implicitHeight: wrapped
                    ? (confLbl.implicitHeight + HKS.space8 + conflictToggleBtn.height)
                    : Math.max(confLbl.implicitHeight, conflictToggleBtn.height)
                height: implicitHeight

                TextMetrics {
                    id: confLblMetrics
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.Bold
                    text: confLbl.text
                }

                Text {
                    id: confLbl
                    x: 0
                    y: confHdrBox.wrapped ? 0 : Math.max(0, Math.round((confHdrBox.height - height) / 2))
                    width: confHdrBox.wrapped
                        ? confHdrBox.width
                        : Math.max(0, confHdrBox.width - conflictToggleBtn.width - HKS.space12)
                    text: "Consistency & Conflicts (" + ThemesService.conflicts.length + ")"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.Bold
                    color: HKS.fg
                    wrapMode: Text.WordWrap
                }

                ActionButton {
                    id: conflictToggleBtn
                    x: confHdrBox.wrapped ? 0 : Math.max(0, confHdrBox.width - width)
                    y: confHdrBox.wrapped
                        ? (confLbl.implicitHeight + HKS.space8)
                        : Math.max(0, Math.round((confHdrBox.height - height) / 2))
                    text: root.expandConflicts ? "Hide hints" : "Fix hints"
                    compact: true
                    variant: root.expandConflicts ? "accent" : "neutral"
                    onClicked: root.expandConflicts = !root.expandConflicts
                }
            }

            Repeater {
                model: ThemesService.conflicts
                delegate: Rectangle {
                    id: confCard
                    required property var modelData
                    width: viewport.innerWidth
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
                            objectName: root.expandConflicts ? "" : "elideOk"
                            text: String(confCard.modelData.explanation || "")
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            font.weight: Font.DemiBold
                            color: confCard.modelData.severity === "warning" ? HKS.warning : HKS.fg
                            width: parent.width
                            elide: root.expandConflicts ? Text.ElideNone : Text.ElideRight
                            maximumLineCount: root.expandConflicts ? 10 : 1
                            wrapMode: root.expandConflicts ? Text.WordWrap : Text.NoWrap
                        }

                        Text {
                            visible: root.expandConflicts && String(confCard.modelData.fix_hint || "").length > 0
                            text: String(confCard.modelData.fix_hint || "")
                            font.family: HKS.fontFamily
                            font.pixelSize: 11
                            color: HKS.muted
                            width: parent.width
                            wrapMode: Text.WordWrap
                        }

                        Rectangle {
                            visible: root.expandConflicts && !!(confCard.modelData.copy_text && String(confCard.modelData.copy_text).length > 0)
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
        DeviceCard {
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding
            title: "Wallpaper"
            detailText: ThemesService.wallpaper.path
                ? (String(ThemesService.wallpaper.path) + " (" + String(ThemesService.wallpaper.source || "none") + ")")
                : "No active wallpaper detected."
            actions: [
                ActionButton {
                    text: "Open wallpaper picker"
                    variant: "accent"
                    compact: true
                    enabled: !ThemesService.busy
                    onClicked: ThemesService.openWallpaperPicker()
                }
            ]
        }

        // GTK Theme & Color Scheme
        SectionCard {
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding

            Text {
                width: parent.width
                text: "GTK Theme (" + String(ThemesService.gtk.effective_theme || "unset") + ") · Color scheme: " + ThemesService.colorScheme
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSize
                font.weight: Font.DemiBold
                color: HKS.fg
                wrapMode: Text.WordWrap
            }

            ChipFlow {
                width: parent.width
                layoutClass: viewport.layoutClass
                layoutShort: viewport.layoutShort
                spacing: 6

                Repeater {
                    model: ThemesService.gtk.installed || []
                    delegate: ActionButton {
                        required property string modelData
                        text: modelData
                        width: Math.min(implicitWidth, viewport.innerWidth - viewport.cardPadding * 2)
                        variant: ThemesService.gtk.gsettings_theme === modelData ? "accent" : "neutral"
                        compact: true
                        enabled: !ThemesService.busy
                        onClicked: ThemesService.setGtkTheme(modelData)
                    }
                }
            }
        }

        // Icons
        SectionCard {
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding

            Item {
                id: iconHdrBox
                width: parent.width
                readonly property bool hasBtn: iconShowAllBtn.visible
                readonly property real btnW: hasBtn ? iconShowAllBtn.width : 0
                readonly property bool wrapped: hasBtn && ResponsiveLogic.shouldWrapHeaderActions(
                    iconHdrBox.width, iconLblMetrics.advanceWidth, btnW, HKS.space12
                )
                implicitHeight: wrapped
                    ? (iconLbl.implicitHeight + HKS.space8 + iconShowAllBtn.height)
                    : Math.max(iconLbl.implicitHeight, hasBtn ? iconShowAllBtn.height : 0)
                height: implicitHeight

                TextMetrics {
                    id: iconLblMetrics
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.DemiBold
                    text: iconLbl.text
                }

                Text {
                    id: iconLbl
                    x: 0
                    y: iconHdrBox.wrapped ? 0 : Math.max(0, Math.round((iconHdrBox.height - height) / 2))
                    width: iconHdrBox.wrapped
                        ? iconHdrBox.width
                        : Math.max(0, iconHdrBox.width - (iconHdrBox.hasBtn ? iconHdrBox.btnW + HKS.space12 : 0))
                    text: "Icon Theme (" + String(ThemesService.icons.gsettings_theme || "unset") + ") — " + themesLogic.iconBadgeText(ThemesService.icons.gsettings_theme)
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.DemiBold
                    color: HKS.fg
                    wrapMode: Text.WordWrap
                }

                ActionButton {
                    id: iconShowAllBtn
                    x: iconHdrBox.wrapped ? 0 : Math.max(0, iconHdrBox.width - width)
                    y: iconHdrBox.wrapped
                        ? (iconLbl.implicitHeight + HKS.space8)
                        : Math.max(0, Math.round((iconHdrBox.height - height) / 2))
                    visible: (ThemesService.icons.installed || []).length > themesLogic.visibleThemeChips(ThemesService.icons.installed || [], ThemesService.icons.gsettings_theme, false, 8).length || root.showAllIcons
                    text: root.showAllIcons ? "Show less" : ("Show all (" + (ThemesService.icons.installed || []).length + ")")
                    compact: true
                    variant: root.showAllIcons ? "accent" : "neutral"
                    onClicked: root.showAllIcons = !root.showAllIcons
                }
            }

            ChipFlow {
                width: parent.width
                layoutClass: viewport.layoutClass
                layoutShort: viewport.layoutShort
                spacing: 6

                Repeater {
                    model: themesLogic.visibleThemeChips(ThemesService.icons.installed || [], ThemesService.icons.gsettings_theme, root.showAllIcons, 8)
                    delegate: ActionButton {
                        required property string modelData
                        text: modelData === "Papirus-Dynamic" ? "Papirus-Dynamic ★" : modelData
                        width: Math.min(implicitWidth, viewport.innerWidth - viewport.cardPadding * 2)
                        variant: ThemesService.icons.gsettings_theme === modelData ? "accent" : "neutral"
                        compact: true
                        enabled: !ThemesService.busy
                        onClicked: ThemesService.setIconTheme(modelData)
                    }
                }
            }
        }

        // Cursor (live)
        SectionCard {
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding

            Item {
                id: curHdrBox
                width: parent.width
                readonly property bool wrapped: ResponsiveLogic.shouldWrapHeaderActions(
                    curHdrBox.width, curLblMetrics.advanceWidth, curSizeRow.implicitWidth, HKS.space12
                )
                implicitHeight: wrapped
                    ? (curLbl.implicitHeight + HKS.space8 + curSizeRow.height)
                    : Math.max(curLbl.implicitHeight, curSizeRow.height)
                height: implicitHeight

                TextMetrics {
                    id: curLblMetrics
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.DemiBold
                    text: curLbl.text
                }

                Text {
                    id: curLbl
                    x: 0
                    y: curHdrBox.wrapped ? 0 : Math.max(0, Math.round((curHdrBox.height - height) / 2))
                    width: curHdrBox.wrapped
                        ? curHdrBox.width
                        : Math.max(0, curHdrBox.width - curSizeRow.width - HKS.space12)
                    text: "Cursor (" + String(ThemesService.cursor.gsettings_theme || "unset") + ", size " + String(ThemesService.cursor.size || 24) + ") · Applies live"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.DemiBold
                    color: HKS.fg
                    wrapMode: Text.WordWrap
                }

                Row {
                    id: curSizeRow
                    x: curHdrBox.wrapped ? 0 : Math.max(0, curHdrBox.width - width)
                    y: curHdrBox.wrapped
                        ? (curLbl.implicitHeight + HKS.space8)
                        : Math.max(0, Math.round((curHdrBox.height - height) / 2))
                    spacing: 6

                    ActionButton {
                        text: "-"
                        compact: true
                        implicitWidth: 32
                        enabled: !ThemesService.busy && Number(ThemesService.cursor.size || 24) > 16
                        onClicked: ThemesService.setCursor(
                            ThemesService.cursor.gsettings_theme || "Pop",
                            themesLogic.clampCursorSize(Number(ThemesService.cursor.size || 24) - 4)
                        )
                    }

                    ActionButton {
                        text: "+"
                        compact: true
                        implicitWidth: 32
                        enabled: !ThemesService.busy && Number(ThemesService.cursor.size || 24) < 64
                        onClicked: ThemesService.setCursor(
                            ThemesService.cursor.gsettings_theme || "Pop",
                            themesLogic.clampCursorSize(Number(ThemesService.cursor.size || 24) + 4)
                        )
                    }
                }
            }

            ChipFlow {
                width: parent.width
                layoutClass: viewport.layoutClass
                layoutShort: viewport.layoutShort
                spacing: 6

                Repeater {
                    model: themesLogic.visibleThemeChips(ThemesService.cursor.installed || [], ThemesService.cursor.gsettings_theme, root.showAllCursors, 8)
                    delegate: ActionButton {
                        required property string modelData
                        text: modelData
                        width: Math.min(implicitWidth, viewport.innerWidth - viewport.cardPadding * 2)
                        variant: ThemesService.cursor.gsettings_theme === modelData ? "accent" : "neutral"
                        compact: true
                        enabled: !ThemesService.busy
                        onClicked: ThemesService.setCursor(modelData, Number(ThemesService.cursor.size || 24))
                    }
                }
            }

            Flow {
                visible: (ThemesService.cursor.installed || []).length > themesLogic.visibleThemeChips(ThemesService.cursor.installed || [], ThemesService.cursor.gsettings_theme, false, 8).length || root.showAllCursors
                width: parent.width

                ActionButton {
                    text: root.showAllCursors ? "Show less" : ("Show all (" + (ThemesService.cursor.installed || []).length + ")")
                    compact: true
                    variant: root.showAllCursors ? "accent" : "neutral"
                    onClicked: root.showAllCursors = !root.showAllCursors
                }
            }
        }

        // Qt6ct
        SectionCard {
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding

            Text {
                width: parent.width
                text: "Qt6ct Style (" + String(ThemesService.qt.style || "unset") + ") · Qt apps pick this up after restart"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSize
                font.weight: Font.DemiBold
                color: HKS.fg
                wrapMode: Text.WordWrap
            }

            ChipFlow {
                width: parent.width
                layoutClass: viewport.layoutClass
                layoutShort: viewport.layoutShort
                spacing: 6

                Repeater {
                    model: ThemesService.qt.installed_styles || []
                    delegate: ActionButton {
                        required property string modelData
                        text: modelData
                        width: Math.min(implicitWidth, viewport.innerWidth - viewport.cardPadding * 2)
                        variant: ThemesService.qt.style === modelData ? "accent" : "neutral"
                        compact: true
                        enabled: !ThemesService.busy
                        onClicked: ThemesService.setQt(modelData, null, null)
                    }
                }
            }

            Text {
                width: parent.width
                text: "Qt6ct Color Schemes"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.muted
                wrapMode: Text.WordWrap
            }

            ChipFlow {
                width: parent.width
                layoutClass: viewport.layoutClass
                layoutShort: viewport.layoutShort
                spacing: 6

                Repeater {
                    model: ThemesService.qt.installed_color_schemes || []
                    delegate: ActionButton {
                        required property var modelData
                        text: String(modelData.name || "")
                        width: Math.min(implicitWidth, viewport.innerWidth - viewport.cardPadding * 2)
                        variant: ThemesService.qt.color_scheme_path === modelData.path ? "accent" : "neutral"
                        compact: true
                        enabled: !ThemesService.busy
                        onClicked: ThemesService.setQt(null, null, modelData.path)
                    }
                }
            }
        }
    }
}
