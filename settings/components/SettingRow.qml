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
    width: parent ? parent.width : implicitWidth
    implicitHeight: visible ? (inner.implicitHeight + Deck.space12 * 2) : 0
    height: implicitHeight
    radius: Deck.radiusMedium
    color: root.modified ? Deck.alpha(Deck.accent, 0.08) : Deck.surface
    border.width: 1
    border.color: root.modified ? Deck.alpha(Deck.accent, 0.45) : Deck.alpha(Deck.muted, 0.16)

    SettingControlLogic {
        id: logic
        optionType: root.optType
        value: root.currentValue
        minValue: root.option && root.option.min !== undefined ? Number(root.option.min) : 0
        maxValue: root.option && root.option.max !== undefined ? Number(root.option.max) : 100
        stepValue: root.option && root.option.step !== undefined ? Number(root.option.step) : 1
    }

    Item {
        id: inner
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Deck.space12

        readonly property real enumNaturalWidth: {
            var total = 0;
            var count = 0;
            var kids = enumFlow.children;
            for (var i = 0; i < kids.length; i++) {
                var c = kids[i];
                if (c && c.visible && c.implicitWidth > 0) {
                    if (count > 0) total += enumFlow.spacing;
                    total += c.implicitWidth;
                    count++;
                }
            }
            return total;
        }

        readonly property real controlsNaturalWidth: {
            var resetW = 84;
            if (root.optType === "bool") {
                return 44 + Deck.space8 + resetW;
            }
            if (root.optType === "int" || root.optType === "float") {
                // 130 slider + 28 '-' + 56 box + 28 '+' + 3*6 spacing = 260
                return 260 + Deck.space8 + resetW;
            }
            if (root.optType === "enum") {
                return enumNaturalWidth + Deck.space8 + resetW;
            }
            var swatchW = root.optType === "color" ? 30 : 0;
            return swatchW + 130 + Deck.space8 + resetW;
        }

        readonly property bool stacked: ResponsiveLogic.shouldStackSettingRow(
            inner.width, 200, inner.controlsNaturalWidth, Deck.space12
        )
        readonly property real controlsColWidth: stacked
            ? inner.width
            : Math.min(inner.controlsNaturalWidth, Math.max(0, inner.width))
        readonly property real inlineRowHeight: Math.max(leftCol.implicitHeight, controlsFlow.implicitHeight)

        implicitHeight: stacked
            ? (leftCol.implicitHeight + Deck.space8 + controlsFlow.implicitHeight)
            : inlineRowHeight
        height: implicitHeight

        // Left: label + override badge + description
        Column {
            id: leftCol
            x: 0
            y: inner.stacked ? 0 : Math.max(0, Math.round((inner.inlineRowHeight - height) / 2))
            width: inner.stacked
                ? inner.width
                : Math.max(0, inner.width - inner.controlsColWidth - Deck.space12)
            spacing: 3

            TextMetrics {
                id: labelMetrics
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.DemiBold
                text: root.option && root.option.label ? root.option.label : ""
            }

            Flow {
                width: parent.width
                spacing: 8

                Text {
                    id: optLabelTxt
                    objectName: "elideOk"
                    width: Math.min(Math.ceil(labelMetrics.advanceWidth) + 2, Math.max(40, leftCol.width))
                    text: root.option && root.option.label ? root.option.label : ""
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSize
                    font.weight: Font.DemiBold
                    color: Deck.fg
                    elide: Text.ElideRight
                }

                Rectangle {
                    visible: root.hasOverride || root.modified
                    width: badgeTxt.implicitWidth + 10
                    height: 16
                    radius: 4
                    color: root.modified ? Deck.alpha(Deck.warning, 0.22) : Deck.alpha(Deck.accent, 0.18)

                    Text {
                        id: badgeTxt
                        anchors.centerIn: parent
                        text: root.modified ? "unsaved" : "override"
                        font.family: Deck.fontFamily
                        font.pixelSize: 10
                        color: root.modified ? Deck.warning : Deck.accent
                    }
                }
            }

            Text {
                width: parent.width
                text: root.option && root.option.description ? root.option.description : ""
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }
        }

        // Right / bottom: generic type control + per-option reset
        Flow {
            id: controlsFlow
            x: inner.stacked ? 0 : Math.max(0, inner.width - width)
            y: inner.stacked
                ? (leftCol.implicitHeight + Deck.space8)
                : Math.max(0, Math.round((inner.inlineRowHeight - height) / 2))
            width: inner.controlsColWidth
            spacing: Deck.space8

            // BOOL: Switch
            Rectangle {
                visible: root.optType === "bool"
                width: 44
                height: 24
                radius: 12
                color: !!root.currentValue ? Deck.accent : Deck.elevated
                border.width: 1
                border.color: !!root.currentValue ? Deck.accent : Deck.alpha(Deck.muted, 0.4)

                Rectangle {
                    width: 18
                    height: 18
                    radius: 9
                    anchors.verticalCenter: parent.verticalCenter
                    x: !!root.currentValue ? parent.width - width - 3 : 3
                    color: Deck.fg
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
                spacing: 6

                Rectangle {
                    id: track
                    width: inner.stacked
                        ? Math.min(130, Math.max(76, inner.width - 224))
                        : 130
                    height: 6
                    radius: 3
                    anchors.verticalCenter: parent.verticalCenter
                    color: Deck.elevated

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
                        color: Deck.accent
                    }

                    Rectangle {
                        width: 14
                        height: 14
                        radius: 7
                        anchors.verticalCenter: parent.verticalCenter
                        x: Math.max(0, Math.min(parent.width - width, parent.width * parent.ratio - width / 2))
                        color: Deck.fg
                        border.width: 1
                        border.color: Deck.accent
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
                    radius: Deck.radiusSmall
                    color: Deck.bg
                    border.width: 1
                    border.color: Deck.alpha(Deck.muted, 0.3)

                    Text {
                        anchors.centerIn: parent
                        text: logic.formatDisplay(root.currentValue)
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.fg
                    }
                }

                ActionButton {
                    text: "+"
                    compact: true
                    implicitWidth: 28
                    onClicked: root.valueEdited(root.option.id, logic.stepBy(1))
                }
            }

            // ENUM: Pill selector (wraps cleanly when narrow)
            Flow {
                id: enumFlow
                visible: root.optType === "enum"
                width: inner.stacked
                    ? Math.min(inner.enumNaturalWidth, inner.width)
                    : inner.enumNaturalWidth
                spacing: 4

                Repeater {
                    model: root.option && root.option.enum_values ? root.option.enum_values : []
                    delegate: Rectangle {
                        required property string modelData
                        readonly property bool selected: String(root.currentValue) === modelData

                        TextMetrics {
                            id: enumMetrics
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            text: logic.enumOptionLabel(modelData)
                        }

                        implicitWidth: Math.ceil(enumMetrics.advanceWidth) + 16
                        width: Math.min(implicitWidth, Math.max(48, inner.width))
                        height: 28
                        radius: Deck.radiusSmall
                        color: selected ? Deck.alpha(Deck.accent, 0.22) : Deck.elevated
                        border.width: 1
                        border.color: selected ? Deck.accent : Deck.alpha(Deck.muted, 0.25)

                        Text {
                            id: enumTxt
                            objectName: "elideOk"
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            verticalAlignment: Text.AlignVCenter
                            horizontalAlignment: Text.AlignHCenter
                            text: logic.enumOptionLabel(modelData)
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: selected ? Deck.accent : Deck.fg
                            elide: Text.ElideRight
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
                spacing: 6

                Rectangle {
                    visible: root.optType === "color"
                    width: 24
                    height: 24
                    radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    border.width: 1
                    border.color: Deck.alpha(Deck.muted, 0.4)
                    color: {
                        var s = String(root.currentValue || "");
                        if (s.indexOf("0x") === 0 && s.length === 10) {
                            return "#" + s.slice(4);
                        }
                        if (s.indexOf("#") === 0) return s;
                        return Deck.elevated;
                    }
                }

                Rectangle {
                    width: inner.stacked
                        ? Math.min(130, Math.max(84, inner.width - 130))
                        : 130
                    height: 28
                    radius: Deck.radiusSmall
                    color: Deck.bg
                    border.width: 1
                    border.color: colorInput.activeFocus ? Deck.accent : Deck.alpha(Deck.muted, 0.3)

                    TextInput {
                        id: colorInput
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        verticalAlignment: TextInput.AlignVCenter
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.fg
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
                id: resetBtn
                text: "Reset"
                compact: true
                enabled: root.hasOverride || root.modified
                onClicked: root.resetRequested(root.option.id)
            }
        }
    }
}
