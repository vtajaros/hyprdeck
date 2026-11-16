import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    DisplayControlLogic {
        id: dispLogic
    }

    function _normMode(m) {
        var s = String(m || "").trim();
        if (s.toLowerCase().slice(-2) === "hz") {
            return s.slice(0, -2).trim();
        }
        return s;
    }

    PageViewport {
        id: viewport
        anchors.fill: parent

        header: PageHeader {
            title: "Display"
            subtitle: "Monitors, resolution, scale, rotation, VRR, and backlight brightness."

            ActionButton {
                text: "Refresh"
                compact: true
                enabled: !DisplayService.busy && !DisplayService.countdownActive
                onClicked: DisplayService.reload()
            }

            ActionButton {
                text: "Discard"
                compact: true
                visible: DisplayService.hasDraftChanges
                enabled: !DisplayService.busy && !DisplayService.countdownActive
                onClicked: DisplayService.discardDrafts()
            }

            ActionButton {
                text: DisplayService.busy ? "Applying..." : "Apply"
                variant: "accent"
                compact: true
                enabled: DisplayService.hasDraftChanges
                    && !DisplayService.busy
                    && !DisplayService.countdownActive
                    && DisplayService.includeInstalled
                onClicked: DisplayService.applyChanges(null)
            }
        }

        // Inline include-missing warning
        Rectangle {
            visible: !DisplayService.loading && !DisplayService.includeInstalled
            width: viewport.innerWidth
            height: incWarnTxt.implicitHeight + 16
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.warning, 0.14)
            border.width: 1
            border.color: HKS.alpha(HKS.warning, 0.5)

            Text {
                id: incWarnTxt
                anchors.fill: parent
                anchors.margins: 8
                text: "Include block not installed in hyprland.lua. Applying display rules requires running: python3 -m backend.cli overrides install-include --apply --scan-sha256 <sha>"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.warning
                wrapMode: Text.WordWrap
            }
        }

        // Inline backend error banner
        Rectangle {
            visible: DisplayService.error.length > 0
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
                text: DisplayService.error
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Backlight Brightness Card
        Rectangle {
            visible: !!(DisplayService.brightness && DisplayService.brightness.available)
            width: viewport.innerWidth
            height: briInner.implicitHeight + HKS.space12 * 2
            radius: HKS.radiusMedium
            color: HKS.surface
            border.width: 1
            border.color: HKS.alpha(HKS.muted, 0.18)

            Item {
                id: briInner
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: HKS.space12

                // 180 track + 28 '-' + 52 box + 28 '+' + 3*8 spacing = 312
                readonly property real briNaturalW: 312
                readonly property bool stacked: ResponsiveLogic.shouldStackSettingRow(
                    briInner.width, 160, briNaturalW, HKS.space12
                )
                readonly property real inlineRowH: Math.max(briTitleCol.implicitHeight, briControls.implicitHeight)

                implicitHeight: stacked
                    ? (briTitleCol.implicitHeight + HKS.space8 + briControls.implicitHeight)
                    : inlineRowH
                height: implicitHeight

                Column {
                    id: briTitleCol
                    x: 0
                    y: briInner.stacked ? 0 : Math.max(0, Math.round((briInner.inlineRowH - height) / 2))
                    width: briInner.stacked
                        ? briInner.width
                        : Math.max(0, briInner.width - briInner.briNaturalW - HKS.space12)
                    spacing: 2

                    Text {
                        width: parent.width
                        text: "Display Brightness"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.DemiBold
                        color: HKS.fg
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: "Device: " + (DisplayService.brightness.device || "backlight") + " (5% minimum floor)"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                        wrapMode: Text.WordWrap
                    }
                }

                Row {
                    id: briControls
                    x: briInner.stacked ? 0 : Math.max(0, briInner.width - width)
                    y: briInner.stacked
                        ? (briTitleCol.implicitHeight + HKS.space8)
                        : Math.max(0, Math.round((briInner.inlineRowH - height) / 2))
                    spacing: 8

                    Rectangle {
                        id: briTrack
                        width: briInner.stacked
                            ? Math.min(180, Math.max(80, briInner.width - 132))
                            : 180
                        height: 6
                        radius: 3
                        anchors.verticalCenter: parent.verticalCenter
                        color: HKS.elevated

                        readonly property int pct: dispLogic.clampBrightness(DisplayService.brightness ? DisplayService.brightness.percent : 100)
                        readonly property real ratio: Math.max(0, Math.min(1, (pct - 5) / 95.0))

                        Rectangle {
                            width: parent.width * parent.ratio
                            height: parent.height
                            radius: 3
                            color: HKS.accent
                        }

                        Rectangle {
                            width: 14
                            height: 14
                            radius: 7
                            anchors.verticalCenter: parent.verticalCenter
                            x: Math.max(0, Math.min(parent.width - width, parent.width * parent.ratio - width / 2))
                            color: HKS.fg
                            border.width: 1
                            border.color: HKS.accent
                        }

                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -6
                            cursorShape: Qt.PointingHandCursor
                            function applyBriX(mx) {
                                var r = Math.max(0, Math.min(1, mx / briTrack.width));
                                var val = dispLogic.clampBrightness(5 + r * 95);
                                DisplayService.setBrightness(val);
                            }
                            onPressed: function(mouse) { applyBriX(mouse.x); }
                            onPositionChanged: function(mouse) {
                                if (pressed) applyBriX(mouse.x);
                            }
                        }
                    }

                    ActionButton {
                        text: "-"
                        compact: true
                        implicitWidth: 28
                        onClicked: DisplayService.setBrightness(dispLogic.clampBrightness(briTrack.pct - 5))
                    }

                    Rectangle {
                        width: 52
                        height: 28
                        radius: HKS.radiusSmall
                        color: HKS.bg
                        border.width: 1
                        border.color: HKS.alpha(HKS.muted, 0.3)

                        Text {
                            anchors.centerIn: parent
                            text: briTrack.pct + "%"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.fg
                        }
                    }

                    ActionButton {
                        text: "+"
                        compact: true
                        implicitWidth: 28
                        onClicked: DisplayService.setBrightness(dispLogic.clampBrightness(briTrack.pct + 5))
                    }
                }
            }
        }

        // Empty state
        EmptyState {
            visible: !DisplayService.loading && DisplayService.outputs.length === 0
            width: viewport.innerWidth
            height: 220
            title: "No monitors detected"
            message: DisplayService.error.length > 0 ? DisplayService.error : "hyprctl monitors all returned no outputs."
        }

        // Monitor Output Cards
        Repeater {
            model: DisplayService.outputs

            delegate: Rectangle {
                id: outputCard
                required property var modelData
                readonly property var outData: modelData
                readonly property string outName: outData ? String(outData.name || "") : ""
                readonly property bool effDisabled: !!DisplayService.effectiveField(outData, "disabled")
                readonly property string effMode: String(DisplayService.effectiveField(outData, "current_mode") || DisplayService.effectiveField(outData, "mode") || "")
                readonly property real effScale: Number(DisplayService.effectiveField(outData, "scale") || 1.0)
                readonly property int effTransform: Number(DisplayService.effectiveField(outData, "transform") || 0)
                readonly property int effVrr: Number(DisplayService.effectiveField(outData, "vrr") || 0)
                readonly property string effPosition: String(DisplayService.effectiveField(outData, "position") || "0x0")
                readonly property string effMirror: String(DisplayService.effectiveField(outData, "mirror_of") || "none")
                readonly property bool canToggleDisable: dispLogic.canDisableOutput(DisplayService.outputs, DisplayService.draftOutputs, outName)
                readonly property string scaleWarn: dispLogic.scaleWarningText(outData ? outData.width : 0, outData ? outData.height : 0, effScale)

                width: viewport.innerWidth
                height: cardCol.implicitHeight + HKS.space12 * 2
                radius: HKS.radiusMedium
                color: DisplayService.draftOutputs.hasOwnProperty(outName) ? HKS.alpha(HKS.accent, 0.08) : HKS.surface
                border.width: 1
                border.color: DisplayService.draftOutputs.hasOwnProperty(outName) ? HKS.alpha(HKS.accent, 0.45) : HKS.alpha(HKS.muted, 0.18)

                Column {
                    id: cardCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: HKS.space12
                    spacing: HKS.space12

                    // Output Header
                    Item {
                        id: outHdrBox
                        width: parent.width
                        readonly property real rightW: outHeaderRight.implicitWidth
                        readonly property bool wrapped: ResponsiveLogic.shouldWrapDeviceActions(
                            outHdrBox.width, 160, rightW, HKS.space12
                        )
                        readonly property real rowH: Math.max(outHdrLeft.implicitHeight, outHeaderRight.implicitHeight)

                        implicitHeight: wrapped
                            ? (outHdrLeft.implicitHeight + HKS.space8 + outHeaderRight.implicitHeight)
                            : rowH
                        height: implicitHeight

                        Column {
                            id: outHdrLeft
                            x: 0
                            y: outHdrBox.wrapped ? 0 : Math.max(0, Math.round((outHdrBox.rowH - height) / 2))
                            width: outHdrBox.wrapped
                                ? outHdrBox.width
                                : Math.max(0, outHdrBox.width - outHdrBox.rightW - HKS.space12)
                            spacing: 3

                            Flow {
                                width: parent.width
                                spacing: 8

                                Text {
                                    text: outputCard.outName
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeMedium
                                    font.weight: Font.Bold
                                    color: HKS.fg
                                }

                                Rectangle {
                                    width: Math.min(hdrBadgeTxt.implicitWidth + 12, outHdrLeft.width)
                                    height: 18
                                    radius: 4
                                    color: HKS.elevated

                                    Text {
                                        id: hdrBadgeTxt
                                        objectName: "elideOk"
                                        anchors.fill: parent
                                        anchors.leftMargin: 6
                                        anchors.rightMargin: 6
                                        verticalAlignment: Text.AlignVCenter
                                        text: outputCard.outData && outputCard.outData.hdr_capable
                                            ? "HDR supported"
                                            : ("SDR (" + (outputCard.outData ? outputCard.outData.color_management_preset : "srgb") + ")")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 10
                                        color: HKS.muted
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            Text {
                                width: parent.width
                                text: outputCard.outData && outputCard.outData.description ? String(outputCard.outData.description) : "Connected display"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                color: HKS.muted
                                wrapMode: Text.WordWrap
                            }
                        }

                        Row {
                            id: outHeaderRight
                            x: outHdrBox.wrapped ? 0 : Math.max(0, outHdrBox.width - width)
                            y: outHdrBox.wrapped
                                ? (outHdrLeft.implicitHeight + HKS.space8)
                                : Math.max(0, Math.round((outHdrBox.rowH - height) / 2))
                            spacing: 8

                            Text {
                                visible: !outputCard.canToggleDisable && !outputCard.effDisabled
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Last active monitor"
                                font.family: HKS.fontFamily
                                font.pixelSize: 10
                                color: HKS.muted
                            }

                            Rectangle {
                                width: 44
                                height: 24
                                radius: 12
                                anchors.verticalCenter: parent.verticalCenter
                                opacity: (outputCard.effDisabled || outputCard.canToggleDisable) ? 1.0 : 0.45
                                color: !outputCard.effDisabled ? HKS.accent : HKS.elevated
                                border.width: 1
                                border.color: !outputCard.effDisabled ? HKS.accent : HKS.alpha(HKS.muted, 0.4)

                                Rectangle {
                                    width: 18
                                    height: 18
                                    radius: 9
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: !outputCard.effDisabled ? parent.width - width - 3 : 3
                                    color: HKS.fg
                                    Behavior on x { NumberAnimation { duration: 110 } }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: outputCard.effDisabled || outputCard.canToggleDisable
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: DisplayService.setOutputDraft(outputCard.outName, "disabled", !outputCard.effDisabled)
                                }
                            }
                        }
                    }

                    // Controls body when output is enabled
                    Column {
                        visible: !outputCard.effDisabled
                        width: parent.width
                        spacing: HKS.space8

                        // Resolution & Refresh
                        Column {
                            width: parent.width
                            spacing: 4

                            Text {
                                width: parent.width
                                text: "Resolution & Refresh Rate"
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
                                    model: outputCard.outData && outputCard.outData.available_modes ? outputCard.outData.available_modes : []
                                    delegate: Rectangle {
                                        required property string modelData
                                        readonly property string normVal: root._normMode(modelData)
                                        readonly property bool selected: root._normMode(outputCard.effMode) === normVal
                                        width: modeTxt.implicitWidth + 16
                                        height: 28
                                        radius: HKS.radiusSmall
                                        color: selected ? HKS.alpha(HKS.accent, 0.22) : HKS.elevated
                                        border.width: 1
                                        border.color: selected ? HKS.accent : HKS.alpha(HKS.muted, 0.25)

                                        Text {
                                            id: modeTxt
                                            anchors.centerIn: parent
                                            text: modelData
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            color: selected ? HKS.accent : HKS.fg
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: DisplayService.setOutputDraft(outputCard.outName, "mode", normVal)
                                        }
                                    }
                                }
                            }
                        }

                        // Scale
                        Column {
                            width: parent.width
                            spacing: 4

                            Flow {
                                width: parent.width
                                spacing: 8

                                Text {
                                    text: "Scale"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.muted
                                }

                                Rectangle {
                                    id: scaleWarnBox
                                    visible: outputCard.scaleWarn.length > 0
                                    width: Math.min(scaleWarnTxt.implicitWidth + 10, parent.width)
                                    height: 16
                                    radius: 4
                                    color: HKS.alpha(HKS.warning, 0.2)

                                    Text {
                                        id: scaleWarnTxt
                                        objectName: "elideOk"
                                        anchors.fill: parent
                                        anchors.leftMargin: 5
                                        anchors.rightMargin: 5
                                        verticalAlignment: Text.AlignVCenter
                                        text: outputCard.scaleWarn
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 10
                                        color: HKS.warning
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            ChipFlow {
                                width: parent.width
                                layoutClass: viewport.layoutClass
                                layoutShort: viewport.layoutShort
                                spacing: 6

                                Repeater {
                                    model: outputCard.outData && outputCard.outData.scale_options ? outputCard.outData.scale_options : []
                                    delegate: Rectangle {
                                        required property var modelData
                                        readonly property real optScale: Number(modelData.scale)
                                        readonly property bool selected: Math.abs(outputCard.effScale - optScale) < 0.001
                                        readonly property bool clean: !!modelData.clean
                                        width: scaleTxt.implicitWidth + 16
                                        height: 28
                                        radius: HKS.radiusSmall
                                        color: selected ? HKS.alpha(clean ? HKS.accent : HKS.warning, 0.22) : HKS.elevated
                                        border.width: 1
                                        border.color: selected ? (clean ? HKS.accent : HKS.warning) : HKS.alpha(HKS.muted, 0.25)

                                        Text {
                                            id: scaleTxt
                                            anchors.centerIn: parent
                                            text: String(modelData.label) + (clean ? "" : " ~")
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            color: selected ? (clean ? HKS.accent : HKS.warning) : HKS.fg
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: DisplayService.setOutputDraft(outputCard.outName, "scale", optScale)
                                        }
                                    }
                                }
                            }
                        }

                        // Rotation (Transform)
                        Column {
                            width: parent.width
                            spacing: 4

                            Text {
                                width: parent.width
                                text: "Rotation"
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
                                    model: [0, 1, 2, 3, 4, 5, 6, 7]
                                    delegate: Rectangle {
                                        required property int modelData
                                        readonly property bool selected: outputCard.effTransform === modelData
                                        width: trTxt.implicitWidth + 16
                                        height: 28
                                        radius: HKS.radiusSmall
                                        color: selected ? HKS.alpha(HKS.accent, 0.22) : HKS.elevated
                                        border.width: 1
                                        border.color: selected ? HKS.accent : HKS.alpha(HKS.muted, 0.25)

                                        Text {
                                            id: trTxt
                                            anchors.centerIn: parent
                                            text: dispLogic.transformLabel(modelData)
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            color: selected ? HKS.accent : HKS.fg
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: DisplayService.setOutputDraft(outputCard.outName, "transform", modelData)
                                        }
                                    }
                                }
                            }
                        }

                        // VRR
                        Flow {
                            width: parent.width
                            spacing: HKS.space12

                            Column {
                                spacing: 2
                                Text {
                                    text: "Variable Refresh Rate (VRR)"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.muted
                                }
                                Text {
                                    visible: !(outputCard.outData && outputCard.outData.vrr_capable)
                                    text: "Not supported by panel"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: 10
                                    color: HKS.muted
                                }
                            }

                            Row {
                                spacing: 6
                                opacity: (outputCard.outData && outputCard.outData.vrr_capable) ? 1.0 : 0.4

                                Repeater {
                                    model: [
                                        { val: 0, label: "Off" },
                                        { val: 1, label: "On" },
                                        { val: 2, label: "Fullscreen" }
                                    ]
                                    delegate: Rectangle {
                                        required property var modelData
                                        readonly property bool selected: outputCard.effVrr === modelData.val
                                        width: vrrTxt.implicitWidth + 14
                                        height: 26
                                        radius: HKS.radiusSmall
                                        color: selected ? HKS.alpha(HKS.accent, 0.22) : HKS.elevated
                                        border.width: 1
                                        border.color: selected ? HKS.accent : HKS.alpha(HKS.muted, 0.25)

                                        Text {
                                            id: vrrTxt
                                            anchors.centerIn: parent
                                            text: modelData.label
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            color: selected ? HKS.accent : HKS.fg
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            enabled: !!(outputCard.outData && outputCard.outData.vrr_capable)
                                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                            onClicked: DisplayService.setOutputDraft(outputCard.outName, "vrr", modelData.val)
                                        }
                                    }
                                }
                            }
                        }

                        // Multi-monitor position & mirror (hidden in single-monitor setup)
                        Column {
                            visible: DisplayService.outputs.length > 1
                            width: parent.width
                            spacing: HKS.space8

                            Flow {
                                width: parent.width
                                spacing: HKS.space8

                                Text {
                                    height: 28
                                    verticalAlignment: Text.AlignVCenter
                                    text: "Position (XxY)"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.muted
                                }

                                Rectangle {
                                    width: Math.min(130, parent.width)
                                    height: 28
                                    radius: HKS.radiusSmall
                                    color: HKS.bg
                                    border.width: 1
                                    border.color: posInput.activeFocus ? HKS.accent : HKS.alpha(HKS.muted, 0.3)

                                    TextInput {
                                        id: posInput
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        verticalAlignment: TextInput.AlignVCenter
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.fg
                                        text: outputCard.effPosition
                                        onEditingFinished: DisplayService.setOutputDraft(outputCard.outName, "position", text.trim())
                                    }
                                }
                            }

                            ChipFlow {
                                width: parent.width
                                layoutClass: viewport.layoutClass
                                layoutShort: viewport.layoutShort
                                spacing: 6

                                Text {
                                    height: 26
                                    verticalAlignment: Text.AlignVCenter
                                    text: "Mirror of"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.muted
                                }

                                Rectangle {
                                    id: mirrorNoneChip
                                    readonly property bool selected: outputCard.effMirror === "" || outputCard.effMirror === "none"
                                    width: mirrorNoneTxt.implicitWidth + 14
                                    height: 26
                                    radius: HKS.radiusSmall
                                    color: mirrorNoneChip.selected ? HKS.alpha(HKS.accent, 0.22) : HKS.elevated
                                    border.width: 1
                                    border.color: mirrorNoneChip.selected ? HKS.accent : HKS.alpha(HKS.muted, 0.25)

                                    Text {
                                        id: mirrorNoneTxt
                                        anchors.centerIn: parent
                                        text: "None"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: mirrorNoneChip.selected ? HKS.accent : HKS.fg
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: DisplayService.setOutputDraft(outputCard.outName, "mirror_of", "none")
                                    }
                                }

                                Repeater {
                                    model: DisplayService.outputs
                                    delegate: Rectangle {
                                        required property var modelData
                                        readonly property string targetName: modelData && modelData.name ? String(modelData.name) : ""
                                        readonly property bool selected: outputCard.effMirror === targetName
                                        visible: targetName !== outputCard.outName
                                        width: visible ? mirrorOutTxt.implicitWidth + 14 : 0
                                        height: 26
                                        radius: HKS.radiusSmall
                                        color: selected ? HKS.alpha(HKS.accent, 0.22) : HKS.elevated
                                        border.width: 1
                                        border.color: selected ? HKS.accent : HKS.alpha(HKS.muted, 0.25)

                                        Text {
                                            id: mirrorOutTxt
                                            anchors.centerIn: parent
                                            text: targetName
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            color: selected ? HKS.accent : HKS.fg
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: DisplayService.setOutputDraft(outputCard.outName, "mirror_of", targetName)
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
}
