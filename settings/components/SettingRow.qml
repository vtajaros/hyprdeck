import QtQuick
import "../theme"
import "../shared_components"

Rectangle {
    id: root

    property var option: ({})
    property var currentValue: null
    property bool modified: false
    property bool hasOverride: false

    signal valueEdited(string optionId, var newValue)
    signal resetRequested(string optionId)

    readonly property string optType: option && option.type ? option.type : "string"
    visible: !!(option && option.capable)
    implicitHeight: visible ? rowLayout.implicitHeight + 24 : 0
    radius: HKS.radiusMedium
    color: root.modified ? HKS.alpha(HKS.accent, 0.08) : HKS.surface
    border.width: 1
    border.color: root.modified ? HKS.alpha(HKS.accent, 0.45) : HKS.alpha(HKS.muted, 0.16)

    SettingControlLogic {
        id: logic
        optionType: root.optType
        value: root.currentValue
        minValue: root.option && root.option.min !== undefined ? Number(root.option.min) : 0
        maxValue: root.option && root.option.max !== undefined ? Number(root.option.max) : 100
        stepValue: root.option && root.option.step !== undefined ? Number(root.option.step) : 1
    }

    Row {
        id: rowLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: HKS.space12
        spacing: HKS.space12

        // Left: label + description
        Column {
            width: Math.max(180, parent.width - controlsRow.width - HKS.space12)
            anchors.verticalCenter: parent.verticalCenter
            spacing: 3

            Row {
                spacing: 8
                Text {
                    text: root.option && root.option.label ? root.option.label : ""
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.DemiBold
                    color: HKS.fg
                }
                Rectangle {
                    visible: root.hasOverride || root.modified
                    anchors.verticalCenter: parent.verticalCenter
                    width: badgeTxt.implicitWidth + 10
                    height: 16
                    radius: 4
                    color: root.modified ? HKS.alpha(HKS.warning, 0.22) : HKS.alpha(HKS.accent, 0.18)
                    Text {
                        id: badgeTxt
                        anchors.centerIn: parent
                        text: root.modified ? "unsaved" : "override"
                        font.family: HKS.fontFamily
                        font.pixelSize: 10
                        color: root.modified ? HKS.warning : HKS.accent
                    }
                }
            }

            Text {
                width: parent.width
                text: root.option && root.option.description ? root.option.description : ""
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.muted
                wrapMode: Text.WordWrap
            }
        }

        // Right: generic type control + per-option reset
        Row {
            id: controlsRow
            anchors.verticalCenter: parent.verticalCenter
            spacing: HKS.space8

            // BOOL: Switch
            Rectangle {
                visible: root.optType === "bool"
                width: 44
                height: 24
                radius: 12
                anchors.verticalCenter: parent.verticalCenter
                color: !!root.currentValue ? HKS.accent : HKS.elevated
                border.width: 1
                border.color: !!root.currentValue ? HKS.accent : HKS.alpha(HKS.muted, 0.4)

                Rectangle {
                    width: 18
                    height: 18
                    radius: 9
                    anchors.verticalCenter: parent.verticalCenter
                    x: !!root.currentValue ? parent.width - width - 3 : 3
                    color: HKS.fg
                    Behavior on x { NumberAnimation { duration: 110 } }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.valueEdited(root.option.id, !root.currentValue)
                }
            }

            // INT / FLOAT: Slider track + stepper + numeric readout
            Row {
                visible: root.optType === "int" || root.optType === "float"
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Rectangle {
                    id: track
                    width: 130
                    height: 6
                    radius: 3
                    anchors.verticalCenter: parent.verticalCenter
                    color: HKS.elevated

                    readonly property real ratio: {
                        var span = logic.maxValue - logic.minValue;
                        if (span <= 0) return 0;
                        var r = (Number(root.currentValue) - logic.minValue) / span;
                        return Math.max(0, Math.min(1, r));
                    }

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
                        function applyX(mx) {
                            var r = Math.max(0, Math.min(1, mx / track.width));
                            var raw = logic.minValue + r * (logic.maxValue - logic.minValue);
                            var snapped = Math.round((raw - logic.minValue) / logic.stepValue) * logic.stepValue + logic.minValue;
                            root.valueEdited(root.option.id, logic.clampNumber(snapped));
                        }
                        onPressed: function(mouse) { applyX(mouse.x); }
                        onPositionChanged: function(mouse) {
                            if (pressed) applyX(mouse.x);
                        }
                    }
                }

                ActionButton {
                    text: "-"
                    compact: true
                    implicitWidth: 28
                    onClicked: root.valueEdited(root.option.id, logic.stepBy(-1))
                }

                Rectangle {
                    width: 56
                    height: 28
                    radius: HKS.radiusSmall
                    color: HKS.bg
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.3)
                    Text {
                        anchors.centerIn: parent
                        text: logic.formatDisplay(root.currentValue)
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.fg
                    }
                }

                ActionButton {
                    text: "+"
                    compact: true
                    implicitWidth: 28
                    onClicked: root.valueEdited(root.option.id, logic.stepBy(1))
                }
            }

            // ENUM: Pill selector
            Row {
                visible: root.optType === "enum"
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4

                Repeater {
                    model: root.option && root.option.enum_values ? root.option.enum_values : []
                    delegate: Rectangle {
                        required property string modelData
                        readonly property bool selected: String(root.currentValue) === modelData
                        width: enumTxt.implicitWidth + 16
                        height: 28
                        radius: HKS.radiusSmall
                        color: selected ? HKS.alpha(HKS.accent, 0.22) : HKS.elevated
                        border.width: 1
                        border.color: selected ? HKS.accent : HKS.alpha(HKS.muted, 0.25)

                        Text {
                            id: enumTxt
                            anchors.centerIn: parent
                            text: modelData
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: selected ? HKS.accent : HKS.fg
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.valueEdited(root.option.id, modelData)
                        }
                    }
                }
            }

            // COLOR / STRING: Hex input + swatch
            Row {
                visible: root.optType === "color" || root.optType === "string"
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Rectangle {
                    visible: root.optType === "color"
                    width: 24
                    height: 24
                    radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.4)
                    color: {
                        var s = String(root.currentValue || "");
                        if (s.indexOf("0x") === 0 && s.length === 10) {
                            return "#" + s.slice(4);
                        }
                        if (s.indexOf("#") === 0) return s;
                        return HKS.elevated;
                    }
                }

                Rectangle {
                    width: 130
                    height: 28
                    radius: HKS.radiusSmall
                    color: HKS.bg
                    border.width: 1
                    border.color: colorInput.activeFocus ? HKS.accent : HKS.alpha(HKS.muted, 0.3)

                    TextInput {
                        id: colorInput
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        verticalAlignment: TextInput.AlignVCenter
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.fg
                        text: String(root.currentValue !== null && root.currentValue !== undefined ? root.currentValue : "")
                        onEditingFinished: {
                            if (root.optType !== "color" || logic.isValidColor(text)) {
                                root.valueEdited(root.option.id, text.trim());
                            }
                        }
                    }
                }
            }

            // Per-option Reset button
            ActionButton {
                text: "Reset"
                compact: true
                enabled: root.hasOverride || root.modified
                onClicked: root.resetRequested(root.option.id)
            }
        }
    }
}
