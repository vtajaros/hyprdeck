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

    property bool showDetails: false
    property bool showInactiveOutputs: false
    property bool showInactiveInputs: false
    readonly property var outputParts: audioLogic.partitionDevices(AudioService.outputs)
    readonly property var inputParts: audioLogic.partitionDevices(AudioService.inputs)

    PageViewport {
        id: viewport
        anchors.fill: parent

        header: PageHeader {
            title: "Audio"
            subtitle: "Output sinks, input sources, default routing, and active playback streams."

            ActionButton {
                text: root.showDetails ? "Details: On" : "Details"
                compact: true
                variant: root.showDetails ? "accent" : "neutral"
                onClicked: root.showDetails = !root.showDetails
            }

            ActionButton {
                text: AudioService.busy ? "Applying..." : "Refresh"
                compact: true
                enabled: !AudioService.busy
                onClicked: AudioService.reload(false)
            }
        }

        // Error / daemon absent banner
        Rectangle {
            visible: !AudioService.loading && (!AudioService.available || AudioService.error.length > 0)
            width: viewport.innerWidth
            height: errTxt.implicitHeight + 16
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.critical, 0.14)
            border.width: 1
            border.color: Deck.alpha(Deck.critical, 0.5)

            Text {
                id: errTxt
                anchors.fill: parent
                anchors.margins: 8
                text: AudioService.error.length > 0
                    ? AudioService.error
                    : "Audio daemon unavailable (pactl failed)."
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.critical
                wrapMode: Text.WordWrap
            }
        }

        // Empty state when daemon is available but no devices exist
        EmptyState {
            visible: !AudioService.loading && AudioService.available
                && AudioService.outputs.length === 0 && AudioService.inputs.length === 0
            width: viewport.innerWidth
            height: 220
            icon: "󰕾"
            title: "No audio devices found"
            message: "Connect an output or input device and click Refresh."
        }

        // Output Sinks
        Column {
            visible: AudioService.outputs.length > 0 || AudioService.inputs.length > 0 || AudioService.streams.length > 0
            width: viewport.innerWidth
            spacing: Deck.space8

            Text {
                width: parent.width
                text: "Output Devices (" + AudioService.outputs.length + ")"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.Bold
                color: Deck.fg
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: root.showInactiveOutputs ? AudioService.outputs : root.outputParts.active
                delegate: DeviceCard {
                    id: outCard
                    required property var modelData
                    width: viewport.innerWidth
                    cardPadding: viewport.cardPadding
                    highlighted: !!outCard.modelData.is_default
                    title: String(outCard.modelData.description || outCard.modelData.name || "Output")
                    badges: [
                        {
                            text: audioLogic.kindLabel(outCard.modelData.kind),
                            textColor: Deck.accent,
                            bgColor: Deck.alpha(Deck.accent, 0.15),
                            borderColor: Deck.alpha(Deck.accent, 0.35)
                        },
                        {
                            text: String(outCard.modelData.running_state || ""),
                            textColor: Deck.muted,
                            bgColor: Deck.elevated
                        }
                    ]
                    detailText: root.showDetails ? String(outCard.modelData.name || "") : ""

                    actions: [
                        ActionButton {
                            text: outCard.modelData.is_default ? "Default" : "Set Default"
                            variant: outCard.modelData.is_default ? "accent" : "neutral"
                            compact: true
                            enabled: !outCard.modelData.is_default && !AudioService.busy
                            onClicked: AudioService.setDefault("sink", outCard.modelData.name)
                        },
                        ActionButton {
                            text: audioLogic.muteLabel(!!outCard.modelData.mute)
                            variant: outCard.modelData.mute ? "danger" : "neutral"
                            compact: true
                            enabled: !AudioService.busy
                            onClicked: AudioService.setMute("sink", outCard.modelData.name, "toggle")
                        }
                    ]

                    extraContent: [
                        Item {
                            width: parent.width
                            height: 22

                            Rectangle {
                                id: outTrack
                                x: 0
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.max(80, parent.width - 56 - Deck.space8)
                                height: 6
                                radius: 3
                                color: Deck.elevated

                                readonly property int pct: audioLogic.clampVolume(outCard.modelData.volume_percent, 100)
                                readonly property real ratio: Math.max(0, Math.min(1, pct / 100.0))

                                Rectangle {
                                    width: parent.width * parent.ratio
                                    height: parent.height
                                    radius: 3
                                    color: outCard.modelData.mute ? Deck.muted : Deck.accent
                                }

                                Rectangle {
                                    width: 14
                                    height: 14
                                    radius: 7
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: Math.max(0, Math.min(parent.width - width, parent.width * parent.ratio - width / 2))
                                    color: Deck.fg
                                    border.width: 1
                                    border.color: outCard.modelData.mute ? Deck.muted : Deck.accent
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
                                x: parent.width - width
                                width: 48
                                horizontalAlignment: Text.AlignRight
                                anchors.verticalCenter: parent.verticalCenter
                                text: audioLogic.clampVolume(outCard.modelData.volume_percent, 150) + "%"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                color: Deck.fg
                            }
                        },
                        Text {
                            visible: Number(outCard.modelData.balance_diff || 0) > 0
                            width: parent.width
                            text: audioLogic.balanceWarningText(outCard.modelData.balance_diff)
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.warning
                            wrapMode: Text.WordWrap
                        }
                    ]
                }
            }

            SectionCard {
                visible: root.outputParts.inactive.length > 0
                width: viewport.innerWidth
                cardPadding: viewport.cardPadding

                Item {
                    id: outInactBox
                    width: parent.width
                    implicitHeight: Math.max(outInactTxt.implicitHeight, outInactiveBtn.height)
                    height: implicitHeight

                    Text {
                        id: outInactTxt
                        x: 0
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.max(0, outInactBox.width - outInactiveBtn.width - Deck.space12)
                        text: root.outputParts.inactive.length + (root.outputParts.inactive.length === 1 ? " inactive output" : " inactive outputs")
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                        wrapMode: Text.WordWrap
                    }

                    ActionButton {
                        id: outInactiveBtn
                        x: outInactBox.width - width
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.showInactiveOutputs ? "Hide" : "Show"
                        compact: true
                        variant: root.showInactiveOutputs ? "accent" : "neutral"
                        onClicked: root.showInactiveOutputs = !root.showInactiveOutputs
                    }
                }
            }
        }

        // Input Sources
        Column {
            visible: AudioService.outputs.length > 0 || AudioService.inputs.length > 0 || AudioService.streams.length > 0
            width: viewport.innerWidth
            spacing: Deck.space8

            Text {
                width: parent.width
                text: "Input Devices (" + AudioService.inputs.length + ")"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.Bold
                color: Deck.fg
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: root.showInactiveInputs ? AudioService.inputs : root.inputParts.active
                delegate: DeviceCard {
                    id: inCard
                    required property var modelData
                    width: viewport.innerWidth
                    cardPadding: viewport.cardPadding
                    highlighted: !!inCard.modelData.is_default
                    title: String(inCard.modelData.description || inCard.modelData.name || "Input")
                    badges: [
                        {
                            text: audioLogic.kindLabel(inCard.modelData.kind),
                            textColor: Deck.accent,
                            bgColor: Deck.alpha(Deck.accent, 0.15),
                            borderColor: Deck.alpha(Deck.accent, 0.35)
                        },
                        {
                            text: String(inCard.modelData.running_state || ""),
                            textColor: Deck.muted,
                            bgColor: Deck.elevated
                        }
                    ]
                    detailText: root.showDetails ? String(inCard.modelData.name || "") : ""

                    actions: [
                        ActionButton {
                            text: inCard.modelData.is_default ? "Default" : "Set Default"
                            variant: inCard.modelData.is_default ? "accent" : "neutral"
                            compact: true
                            enabled: !inCard.modelData.is_default && !AudioService.busy
                            onClicked: AudioService.setDefault("source", inCard.modelData.name)
                        },
                        ActionButton {
                            text: audioLogic.muteLabel(!!inCard.modelData.mute)
                            variant: inCard.modelData.mute ? "danger" : "neutral"
                            compact: true
                            enabled: !AudioService.busy
                            onClicked: AudioService.setMute("source", inCard.modelData.name, "toggle")
                        }
                    ]

                    extraContent: [
                        Item {
                            width: parent.width
                            height: 22

                            Rectangle {
                                id: inTrack
                                x: 0
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.max(80, parent.width - 56 - Deck.space8)
                                height: 6
                                radius: 3
                                color: Deck.elevated

                                readonly property int pct: audioLogic.clampVolume(inCard.modelData.volume_percent, 100)
                                readonly property real ratio: Math.max(0, Math.min(1, pct / 100.0))

                                Rectangle {
                                    width: parent.width * parent.ratio
                                    height: parent.height
                                    radius: 3
                                    color: inCard.modelData.mute ? Deck.muted : Deck.accent
                                }

                                Rectangle {
                                    width: 14
                                    height: 14
                                    radius: 7
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: Math.max(0, Math.min(parent.width - width, parent.width * parent.ratio - width / 2))
                                    color: Deck.fg
                                    border.width: 1
                                    border.color: inCard.modelData.mute ? Deck.muted : Deck.accent
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
                                x: parent.width - width
                                width: 48
                                horizontalAlignment: Text.AlignRight
                                anchors.verticalCenter: parent.verticalCenter
                                text: audioLogic.clampVolume(inCard.modelData.volume_percent, 150) + "%"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                color: Deck.fg
                            }
                        }
                    ]
                }
            }

            SectionCard {
                visible: root.inputParts.inactive.length > 0
                width: viewport.innerWidth
                cardPadding: viewport.cardPadding

                Item {
                    id: inInactBox
                    width: parent.width
                    implicitHeight: Math.max(inInactTxt.implicitHeight, inInactiveBtn.height)
                    height: implicitHeight

                    Text {
                        id: inInactTxt
                        x: 0
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.max(0, inInactBox.width - inInactiveBtn.width - Deck.space12)
                        text: root.inputParts.inactive.length + (root.inputParts.inactive.length === 1 ? " inactive input" : " inactive inputs")
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                        wrapMode: Text.WordWrap
                    }

                    ActionButton {
                        id: inInactiveBtn
                        x: inInactBox.width - width
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.showInactiveInputs ? "Hide" : "Show"
                        compact: true
                        variant: root.showInactiveInputs ? "accent" : "neutral"
                        onClicked: root.showInactiveInputs = !root.showInactiveInputs
                    }
                }
            }
        }

        // Playback Streams (Read-Only)
        Column {
            visible: AudioService.outputs.length > 0 || AudioService.inputs.length > 0 || AudioService.streams.length > 0
            width: viewport.innerWidth
            spacing: Deck.space8

            Text {
                width: parent.width
                text: "Playback Streams (" + AudioService.streams.length + ")"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.Bold
                color: Deck.fg
                wrapMode: Text.WordWrap
            }

            Text {
                visible: AudioService.streams.length === 0
                width: parent.width
                text: "No active playback streams."
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: AudioService.streams
                delegate: DeviceCard {
                    id: streamRow
                    required property var modelData
                    width: viewport.innerWidth
                    cardPadding: viewport.cardPadding
                    title: String(streamRow.modelData.app || "Application")
                        + (streamRow.modelData.name ? (" — " + streamRow.modelData.name) : "")
                    subtitle: "Sink: " + String(streamRow.modelData.sink || "unknown")
                    badges: [
                        {
                            text: (streamRow.modelData.mute ? "Muted · " : "") + String(streamRow.modelData.volume || 0) + "%",
                            textColor: streamRow.modelData.mute ? Deck.warning : Deck.muted,
                            bgColor: Deck.elevated
                        }
                    ]
                }
            }
        }
    }
}
