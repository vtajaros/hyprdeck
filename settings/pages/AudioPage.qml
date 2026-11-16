import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    AudioControlLogic {
        id: audioLogic
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
                    text: "Audio"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: "Output sinks, input sources, default routing, and active playback streams."
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
                    text: AudioService.busy ? "Applying..." : "Refresh"
                    compact: true
                    enabled: !AudioService.busy
                    onClicked: AudioService.reload(false)
                }
            }
        }

        // Error / daemon absent banner
        Rectangle {
            visible: !AudioService.loading && (!AudioService.available || AudioService.error.length > 0)
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
                text: AudioService.error.length > 0
                    ? AudioService.error
                    : "Audio daemon unavailable (pactl failed)."
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Empty state when daemon is available but no devices exist
        EmptyState {
            visible: !AudioService.loading && AudioService.available
                && AudioService.outputs.length === 0 && AudioService.inputs.length === 0
            width: parent.width
            height: 220
            icon: "󰕾"
            title: "No audio devices found"
            subtitle: "Connect an output or input device and click Refresh."
        }

        // Scrollable content
        Flickable {
            id: flick
            visible: AudioService.outputs.length > 0 || AudioService.inputs.length > 0 || AudioService.streams.length > 0
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

                // Output Sinks
                Column {
                    width: parent.width
                    spacing: HKS.space8

                    Text {
                        text: "Output Devices (" + AudioService.outputs.length + ")"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Repeater {
                        model: AudioService.outputs
                        delegate: Rectangle {
                            id: outCard
                            required property var modelData
                            width: contentCol.width
                            height: outCol.implicitHeight + 24
                            radius: HKS.radiusMedium
                            color: HKS.surface
                            border.width: 1
                            border.color: modelData.is_default ? HKS.accent : HKS.alpha(HKS.muted, 0.18)

                            Column {
                                id: outCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: HKS.space12
                                spacing: HKS.space8

                                Row {
                                    width: parent.width
                                    spacing: HKS.space12

                                    Column {
                                        width: Math.max(180, parent.width - outActions.width - HKS.space12)
                                        spacing: 2

                                        Row {
                                            spacing: 8
                                            Text {
                                                text: String(outCard.modelData.description || outCard.modelData.name || "Output")
                                                font.family: HKS.fontFamily
                                                font.pixelSize: HKS.fontSize
                                                font.weight: Font.DemiBold
                                                color: HKS.fg
                                            }
                                            Rectangle {
                                                width: kindOutTxt.implicitWidth + 10
                                                height: 18
                                                radius: 4
                                                anchors.verticalCenter: parent.verticalCenter
                                                color: HKS.alpha(HKS.accent, 0.15)
                                                Text {
                                                    id: kindOutTxt
                                                    anchors.centerIn: parent
                                                    text: audioLogic.kindLabel(outCard.modelData.kind)
                                                    font.family: HKS.fontFamily
                                                    font.pixelSize: 10
                                                    color: HKS.accent
                                                }
                                            }
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: String(outCard.modelData.running_state || "")
                                                font.family: HKS.fontFamily
                                                font.pixelSize: 10
                                                color: HKS.muted
                                            }
                                        }

                                        Text {
                                            text: String(outCard.modelData.name || "")
                                            font.family: HKS.fontFamily
                                            font.pixelSize: 11
                                            color: HKS.muted
                                            elide: Text.ElideMiddle
                                            width: parent.width
                                        }
                                    }

                                    Row {
                                        id: outActions
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: HKS.space8

                                        ActionButton {
                                            text: outCard.modelData.is_default ? "Default" : "Set Default"
                                            variant: outCard.modelData.is_default ? "accent" : "secondary"
                                            compact: true
                                            enabled: !outCard.modelData.is_default && !AudioService.busy
                                            onClicked: AudioService.setDefault("sink", outCard.modelData.name)
                                        }

                                        ActionButton {
                                            text: audioLogic.muteLabel(!!outCard.modelData.mute)
                                            variant: outCard.modelData.mute ? "danger" : "secondary"
                                            compact: true
                                            enabled: !AudioService.busy
                                            onClicked: AudioService.setMute("sink", outCard.modelData.name, "toggle")
                                        }
                                    }
                                }

                                // Volume Slider Row
                                Row {
                                    width: parent.width
                                    spacing: HKS.space12

                                    Rectangle {
                                        id: outTrack
                                        width: Math.max(160, parent.width - 140)
                                        height: 6
                                        radius: 3
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: HKS.elevated

                                        readonly property int pct: audioLogic.clampVolume(outCard.modelData.volume_percent, 100)
                                        readonly property real ratio: Math.max(0, Math.min(1, pct / 100.0))

                                        Rectangle {
                                            width: parent.width * parent.ratio
                                            height: parent.height
                                            radius: 3
                                            color: outCard.modelData.mute ? HKS.muted : HKS.accent
                                        }

                                        Rectangle {
                                            width: 14
                                            height: 14
                                            radius: 7
                                            anchors.verticalCenter: parent.verticalCenter
                                            x: Math.max(0, Math.min(parent.width - width, parent.width * parent.ratio - width / 2))
                                            color: HKS.fg
                                            border.width: 1
                                            border.color: outCard.modelData.mute ? HKS.muted : HKS.accent
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            anchors.margins: -6
                                            enabled: !AudioService.busy
                                            cursorShape: Qt.PointingHandCursor
                                            onPressed: function(mouse) {
                                                var r = Math.max(0, Math.min(1, mouse.x / outTrack.width));
                                                var val = audioLogic.clampVolume(r * 100, 100);
                                                AudioService.setVolume("sink", outCard.modelData.name, val);
                                            }
                                        }
                                    }

                                    Text {
                                        width: 44
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: audioLogic.clampVolume(outCard.modelData.volume_percent, 150) + "%"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.fg
                                    }

                                    Text {
                                        visible: Number(outCard.modelData.balance_diff || 0) > 0
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: audioLogic.balanceWarningText(outCard.modelData.balance_diff)
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.warning
                                    }
                                }
                            }
                        }
                    }
                }

                // Input Sources
                Column {
                    width: parent.width
                    spacing: HKS.space8

                    Text {
                        text: "Input Devices (" + AudioService.inputs.length + ")"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Repeater {
                        model: AudioService.inputs
                        delegate: Rectangle {
                            id: inCard
                            required property var modelData
                            width: contentCol.width
                            height: inCol.implicitHeight + 24
                            radius: HKS.radiusMedium
                            color: HKS.surface
                            border.width: 1
                            border.color: modelData.is_default ? HKS.accent : HKS.alpha(HKS.muted, 0.18)

                            Column {
                                id: inCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: HKS.space12
                                spacing: HKS.space8

                                Row {
                                    width: parent.width
                                    spacing: HKS.space12

                                    Column {
                                        width: Math.max(180, parent.width - inActions.width - HKS.space12)
                                        spacing: 2

                                        Row {
                                            spacing: 8
                                            Text {
                                                text: String(inCard.modelData.description || inCard.modelData.name || "Input")
                                                font.family: HKS.fontFamily
                                                font.pixelSize: HKS.fontSize
                                                font.weight: Font.DemiBold
                                                color: HKS.fg
                                            }
                                            Rectangle {
                                                width: kindInTxt.implicitWidth + 10
                                                height: 18
                                                radius: 4
                                                anchors.verticalCenter: parent.verticalCenter
                                                color: HKS.alpha(HKS.accent, 0.15)
                                                Text {
                                                    id: kindInTxt
                                                    anchors.centerIn: parent
                                                    text: audioLogic.kindLabel(inCard.modelData.kind)
                                                    font.family: HKS.fontFamily
                                                    font.pixelSize: 10
                                                    color: HKS.accent
                                                }
                                            }
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: String(inCard.modelData.running_state || "")
                                                font.family: HKS.fontFamily
                                                font.pixelSize: 10
                                                color: HKS.muted
                                            }
                                        }

                                        Text {
                                            text: String(inCard.modelData.name || "")
                                            font.family: HKS.fontFamily
                                            font.pixelSize: 11
                                            color: HKS.muted
                                            elide: Text.ElideMiddle
                                            width: parent.width
                                        }
                                    }

                                    Row {
                                        id: inActions
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: HKS.space8

                                        ActionButton {
                                            text: inCard.modelData.is_default ? "Default" : "Set Default"
                                            variant: inCard.modelData.is_default ? "accent" : "secondary"
                                            compact: true
                                            enabled: !inCard.modelData.is_default && !AudioService.busy
                                            onClicked: AudioService.setDefault("source", inCard.modelData.name)
                                        }

                                        ActionButton {
                                            text: audioLogic.muteLabel(!!inCard.modelData.mute)
                                            variant: inCard.modelData.mute ? "danger" : "secondary"
                                            compact: true
                                            enabled: !AudioService.busy
                                            onClicked: AudioService.setMute("source", inCard.modelData.name, "toggle")
                                        }
                                    }
                                }

                                // Volume Slider Row
                                Row {
                                    width: parent.width
                                    spacing: HKS.space12

                                    Rectangle {
                                        id: inTrack
                                        width: Math.max(160, parent.width - 140)
                                        height: 6
                                        radius: 3
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: HKS.elevated

                                        readonly property int pct: audioLogic.clampVolume(inCard.modelData.volume_percent, 100)
                                        readonly property real ratio: Math.max(0, Math.min(1, pct / 100.0))

                                        Rectangle {
                                            width: parent.width * parent.ratio
                                            height: parent.height
                                            radius: 3
                                            color: inCard.modelData.mute ? HKS.muted : HKS.accent
                                        }

                                        Rectangle {
                                            width: 14
                                            height: 14
                                            radius: 7
                                            anchors.verticalCenter: parent.verticalCenter
                                            x: Math.max(0, Math.min(parent.width - width, parent.width * parent.ratio - width / 2))
                                            color: HKS.fg
                                            border.width: 1
                                            border.color: inCard.modelData.mute ? HKS.muted : HKS.accent
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            anchors.margins: -6
                                            enabled: !AudioService.busy
                                            cursorShape: Qt.PointingHandCursor
                                            onPressed: function(mouse) {
                                                var r = Math.max(0, Math.min(1, mouse.x / inTrack.width));
                                                var val = audioLogic.clampVolume(r * 100, 100);
                                                AudioService.setVolume("source", inCard.modelData.name, val);
                                            }
                                        }
                                    }

                                    Text {
                                        width: 44
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: audioLogic.clampVolume(inCard.modelData.volume_percent, 150) + "%"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.fg
                                    }
                                }
                            }
                        }
                    }
                }

                // Playback Streams (Read-Only)
                Column {
                    width: parent.width
                    spacing: HKS.space8

                    Text {
                        text: "Playback Streams (" + AudioService.streams.length + ")"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Text {
                        visible: AudioService.streams.length === 0
                        text: "No active playback streams."
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                    }

                    Repeater {
                        model: AudioService.streams
                        delegate: Rectangle {
                            id: streamRow
                            required property var modelData
                            width: contentCol.width
                            height: streamCol.implicitHeight + 16
                            radius: HKS.radiusSmall
                            color: HKS.surface
                            border.width: 1
                            border.color: HKS.alpha(HKS.muted, 0.14)

                            Row {
                                id: streamCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: HKS.space12
                                spacing: HKS.space12

                                Column {
                                    width: Math.max(160, parent.width - 140)
                                    spacing: 2

                                    Text {
                                        text: String(streamRow.modelData.app || "Application") + (streamRow.modelData.name ? (" — " + streamRow.modelData.name) : "")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        font.weight: Font.DemiBold
                                        color: HKS.fg
                                        elide: Text.ElideRight
                                        width: parent.width
                                    }

                                    Text {
                                        text: "Sink: " + String(streamRow.modelData.sink || "unknown")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.muted
                                        elide: Text.ElideMiddle
                                        width: parent.width
                                    }
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: (streamRow.modelData.mute ? "Muted · " : "") + String(streamRow.modelData.volume || 0) + "%"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: streamRow.modelData.mute ? HKS.warning : HKS.muted
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
