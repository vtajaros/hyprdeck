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
                    text: "Display"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: "Monitors, resolution, scale, rotation, VRR, and backlight brightness."
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
        }

        // Inline include-missing warning
        Rectangle {
            visible: !DisplayService.loading && !DisplayService.includeInstalled
            width: parent.width
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
                text: DisplayService.error
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Scrollable body
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
                spacing: HKS.space12

                // Backlight Brightness Card
                Rectangle {
                    visible: !!(DisplayService.brightness && DisplayService.brightness.available)
                    width: parent.width
                    height: briCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: briCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: HKS.space8

                        Row {
                            width: parent.width
                            spacing: HKS.space12

                            Column {
                                width: Math.max(160, parent.width - briControls.width - HKS.space12)
                                spacing: 2
                                Text {
                                    text: "Display Brightness"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSize
                                    font.weight: Font.DemiBold
                                    color: HKS.fg
                                }
                                Text {
                                    text: "Device: " + (DisplayService.brightness.device || "backlight") + " (5% minimum floor)"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.muted
                                }
                            }

                            Row {
                                id: briControls
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 8

                                Rectangle {
                                    id: briTrack
                                    width: 180
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

                        width: contentCol.width
                        height: cardCol.implicitHeight + 24
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
                            Row {
                                width: parent.width
                                spacing: HKS.space12

                                Column {
                                    width: Math.max(160, parent.width - outHeaderRight.width - HKS.space12)
                                    spacing: 3

                                    Row {
                                        spacing: 8
                                        Text {
                                            text: outputCard.outName
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeMedium
                                            font.weight: Font.Bold
                                            color: HKS.fg
                                        }
                                        Rectangle {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: hdrBadgeTxt.implicitWidth + 12
                                            height: 18
                                            radius: 4
                                            color: HKS.elevated
                                            Text {
                                                id: hdrBadgeTxt
                                                anchors.centerIn: parent
                                                text: outputCard.outData && outputCard.outData.hdr_capable
                                                    ? "HDR supported"
                                                    : ("SDR (" + (outputCard.outData ? outputCard.outData.color_management_preset : "srgb") + ")")
                                                font.family: HKS.fontFamily
                                                font.pixelSize: 10
                                                color: HKS.muted
                                            }
                                        }
                                    }

                                    Text {
                                        text: outputCard.outData && outputCard.outData.description ? String(outputCard.outData.description) : "Connected display"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.muted
                                    }
                                }

                                Row {
                                    id: outHeaderRight
                                    anchors.verticalCenter: parent.verticalCenter
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
                                        text: "Resolution & Refresh Rate"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.muted
                                    }
                                    Flow {
                                        width: parent.width
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
                                    Row {
                                        spacing: 8
                                        Text {
                                            text: "Scale"
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            color: HKS.muted
                                        }
                                        Rectangle {
                                            visible: outputCard.scaleWarn.length > 0
                                            width: scaleWarnTxt.implicitWidth + 10
                                            height: 16
                                            radius: 4
                                            color: HKS.alpha(HKS.warning, 0.2)
                                            Text {
                                                id: scaleWarnTxt
                                                anchors.centerIn: parent
                                                text: outputCard.scaleWarn
                                                font.family: HKS.fontFamily
                                                font.pixelSize: 10
                                                color: HKS.warning
                                            }
                                        }
                                    }
                                    Flow {
                                        width: parent.width
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
                                        text: "Rotation"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.muted
                                    }
                                    Flow {
                                        width: parent.width
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
                                Row {
                                    width: parent.width
                                    spacing: HKS.space12

                                    Column {
                                        anchors.verticalCenter: parent.verticalCenter
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

                                    Row {
                                        spacing: HKS.space12
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: "Position (XxY)"
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            color: HKS.muted
                                        }
                                        Rectangle {
                                            width: 130
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

                                    Row {
                                        spacing: 6
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
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

            EmptyState {
                anchors.centerIn: parent
                visible: !DisplayService.loading && DisplayService.outputs.length === 0
                title: "No monitors detected"
                message: DisplayService.error.length > 0 ? DisplayService.error : "hyprctl monitors all returned no outputs."
            }
        }
    }
}
