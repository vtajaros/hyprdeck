import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    BluetoothControlLogic {
        id: btLogic
    }

    readonly property var pairedList: btLogic.pairedDevices(BluetoothService.devices)
    readonly property var discoveredList: btLogic.discoveredDevices(BluetoothService.devices)
    readonly property bool ctrlPowered: !!(BluetoothService.controller && BluetoothService.controller.powered)
    readonly property bool ctrlPairable: !!(BluetoothService.controller && BluetoothService.controller.pairable)

    PageViewport {
        id: viewport
        anchors.fill: parent
        allowTwoColumns: true

        header: PageHeader {
            title: "Bluetooth"
            subtitle: BluetoothService.controller
                ? ("Adapter: " + (BluetoothService.controller.alias || "hci0") + " (" + (BluetoothService.controller.address || "") + ")")
                : "Bluetooth controller, paired devices, and scanning."

            ActionButton {
                text: root.ctrlPowered ? "Power: On" : "Power: Off"
                variant: root.ctrlPowered ? "accent" : "neutral"
                compact: true
                enabled: BluetoothService.available && !BluetoothService.busy && !BluetoothService.rfkill.hard_blocked
                onClicked: BluetoothService.requestPower(!root.ctrlPowered)
            }

            ActionButton {
                text: root.ctrlPairable ? "Pairable: On" : "Pairable: Off"
                variant: root.ctrlPairable ? "accent" : "neutral"
                compact: true
                enabled: BluetoothService.available && root.ctrlPowered && !BluetoothService.busy
                onClicked: BluetoothService.setPairable(!root.ctrlPairable)
            }

            ActionButton {
                text: BluetoothService.busy ? "Working..." : "Refresh"
                compact: true
                enabled: !BluetoothService.busy
                onClicked: BluetoothService.reload(false)
            }
        }

        // rfkill blocked banner
        Rectangle {
            visible: !BluetoothService.loading && (BluetoothService.rfkill.hard_blocked || BluetoothService.rfkill.soft_blocked)
            width: viewport.innerWidth
            height: rfTxt.implicitHeight + 16
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.warning, 0.14)
            border.width: 1
            border.color: Deck.alpha(Deck.warning, 0.5)

            Text {
                id: rfTxt
                anchors.fill: parent
                anchors.margins: 8
                text: BluetoothService.rfkill.hard_blocked
                    ? "Bluetooth is hardware-blocked (rfkill hard block). Use your hardware switch to unblock."
                    : "Bluetooth is software-blocked (rfkill soft block). Click Power: On to unblock and power on."
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.warning
                wrapMode: Text.WordWrap
            }
        }

        // Error / daemon absent banner
        Rectangle {
            visible: !BluetoothService.loading && !BluetoothService.noController && (!BluetoothService.available || BluetoothService.error.length > 0)
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
                text: BluetoothService.error.length > 0
                    ? BluetoothService.error
                    : "Bluetooth daemon (bluetoothd) unavailable."
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.critical
                wrapMode: Text.WordWrap
            }
        }

        // Manual pairing (blueman-manager) fallback banner
        DeviceCard {
            visible: BluetoothService.needsManualPairing
            width: viewport.innerWidth
            cardPadding: Deck.space12
            highlighted: true
            subtitle: "This device requires passkey or PIN confirmation."
            actions: [
                ActionButton {
                    text: "Open Blueman Manager"
                    variant: "accent"
                    compact: true
                    onClicked: BluetoothService.launchBlueman()
                }
            ]
        }

        // Empty state: no controller
        EmptyState {
            visible: !BluetoothService.loading && BluetoothService.noController
            width: viewport.innerWidth
            height: 220
            icon: "󰂲"
            title: "No Bluetooth controller found"
            message: "Ensure a Bluetooth adapter is attached and bluetoothd is running."
        }

        // Paired Devices
        Column {
            visible: BluetoothService.available && !BluetoothService.noController
            width: viewport.innerWidth
            spacing: Deck.space8

            Text {
                width: parent.width
                text: "Paired Devices (" + root.pairedList.length + ")"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.Bold
                color: Deck.fg
                wrapMode: Text.WordWrap
            }

            Text {
                visible: root.pairedList.length === 0
                width: parent.width
                text: "No paired devices."
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }

            Flow {
                width: parent.width
                spacing: viewport.columnSpacing

                Repeater {
                    model: root.pairedList
                    delegate: DeviceCard {
                        id: pairedCard
                        required property var modelData
                        width: viewport.twoColumnCardWidth
                        cardPadding: viewport.cardPadding
                        highlighted: !!pairedCard.modelData.connected
                        title: String(pairedCard.modelData.alias || pairedCard.modelData.name || pairedCard.modelData.address)
                        badges: {
                            var b = [];
                            if (pairedCard.modelData.connected) {
                                b.push({
                                    text: pairedCard.modelData.is_default_sink ? "Connected · Default Audio" : "Connected",
                                    textColor: Deck.accent,
                                    bgColor: Deck.alpha(Deck.accent, 0.18),
                                    borderColor: Deck.alpha(Deck.accent, 0.4)
                                });
                            }
                            if (pairedCard.modelData.trusted) {
                                b.push({
                                    text: "Trusted",
                                    textColor: Deck.muted,
                                    bgColor: Deck.elevated
                                });
                            }
                            return b;
                        }
                        subtitle: String(pairedCard.modelData.address || "") + (pairedCard.modelData.is_audio ? " · Audio" : "")

                        actions: [
                            ActionButton {
                                text: pairedCard.modelData.connected ? "Disconnect" : "Connect"
                                variant: pairedCard.modelData.connected ? "neutral" : "accent"
                                compact: true
                                enabled: root.ctrlPowered && !BluetoothService.busy
                                onClicked: {
                                    if (pairedCard.modelData.connected) {
                                        BluetoothService.requestDisconnect(pairedCard.modelData);
                                    } else {
                                        BluetoothService.connect(pairedCard.modelData.address);
                                    }
                                }
                            },
                            ActionButton {
                                text: pairedCard.modelData.trusted ? "Untrust" : "Trust"
                                compact: true
                                enabled: !BluetoothService.busy
                                onClicked: BluetoothService.setTrusted(pairedCard.modelData.address, !pairedCard.modelData.trusted)
                            },
                            ActionButton {
                                text: "Remove"
                                variant: "danger"
                                compact: true
                                enabled: !BluetoothService.busy
                                onClicked: BluetoothService.requestRemove(pairedCard.modelData)
                            }
                        ]
                    }
                }
            }
        }

        // Scan & Discovered Devices
        Column {
            visible: BluetoothService.available && !BluetoothService.noController
            width: viewport.innerWidth
            spacing: Deck.space8

            Item {
                id: scanHdrBox
                width: parent.width
                readonly property bool wrapped: ResponsiveLogic.shouldWrapHeaderActions(
                    scanHdrBox.width, scanLblMetrics.advanceWidth, scanBtn.implicitWidth, Deck.space12
                )
                implicitHeight: wrapped
                    ? (scanLbl.implicitHeight + Deck.space8 + scanBtn.height)
                    : Math.max(scanLbl.implicitHeight, scanBtn.height)
                height: implicitHeight

                TextMetrics {
                    id: scanLblMetrics
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSize
                    font.weight: Font.Bold
                    text: scanLbl.text
                }

                Text {
                    id: scanLbl
                    x: 0
                    y: scanHdrBox.wrapped ? 0 : Math.max(0, Math.round((scanHdrBox.height - height) / 2))
                    width: scanHdrBox.wrapped ? scanHdrBox.width : Math.max(0, scanHdrBox.width - scanBtn.width - Deck.space12)
                    text: "Nearby Devices (" + root.discoveredList.length + ")" + (BluetoothService.scanning ? " — Scanning..." : "")
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSize
                    font.weight: Font.Bold
                    color: Deck.fg
                    wrapMode: Text.WordWrap
                }

                ActionButton {
                    id: scanBtn
                    x: scanHdrBox.wrapped ? 0 : Math.max(0, scanHdrBox.width - width)
                    y: scanHdrBox.wrapped ? (scanLbl.implicitHeight + Deck.space8) : Math.max(0, Math.round((scanHdrBox.height - height) / 2))
                    text: BluetoothService.scanning ? "Stop Scan" : "Scan"
                    variant: BluetoothService.scanning ? "neutral" : "accent"
                    compact: true
                    enabled: root.ctrlPowered && !BluetoothService.busy
                    onClicked: {
                        if (BluetoothService.scanning) {
                            BluetoothService.stopScan();
                        } else {
                            BluetoothService.startScan();
                        }
                    }
                }
            }

            Text {
                visible: root.discoveredList.length === 0
                width: parent.width
                text: BluetoothService.scanning
                    ? "Listening for nearby Bluetooth devices..."
                    : "Click Scan to discover nearby unpaired devices."
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }

            Flow {
                width: parent.width
                spacing: viewport.columnSpacing

                Repeater {
                    model: root.discoveredList
                    delegate: DeviceCard {
                        id: discCard
                        required property var modelData
                        width: viewport.twoColumnCardWidth
                        cardPadding: viewport.cardPadding
                        title: String(discCard.modelData.alias || discCard.modelData.name || discCard.modelData.address)
                        subtitle: {
                            var rssiTxt = btLogic.rssiLabel(discCard.modelData.rssi);
                            return String(discCard.modelData.address || "") + (rssiTxt.length > 0 ? (" · " + rssiTxt) : "");
                        }
                        actions: [
                            ActionButton {
                                text: "Pair"
                                variant: "accent"
                                compact: true
                                enabled: root.ctrlPowered && !BluetoothService.busy
                                onClicked: BluetoothService.pair(discCard.modelData.address)
                            }
                        ]
                    }
                }
            }
        }
    }

    // Confirmation Modal for disruptive/destructive actions
    Rectangle {
        anchors.fill: parent
        visible: BluetoothService.confirmOpen
        color: Deck.alpha(Deck.bg, 0.72)
        z: 30

        MouseArea { anchors.fill: parent }

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(440, parent.width - Deck.space24)
            height: modalCol.implicitHeight + 36
            radius: Deck.radius
            color: Deck.surface
            border.width: 1
            border.color: Deck.warning

            Column {
                id: modalCol
                anchors.fill: parent
                anchors.margins: 18
                spacing: Deck.space12

                Text {
                    text: BluetoothService.confirmTitle
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeMedium
                    font.weight: Font.Bold
                    color: Deck.fg
                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Text {
                    text: BluetoothService.confirmMessage
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.warning
                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Flow {
                    width: parent.width
                    layoutDirection: Qt.RightToLeft
                    spacing: Deck.space8

                    ActionButton {
                        text: "Confirm"
                        variant: "danger"
                        compact: true
                        onClicked: BluetoothService.confirmPending()
                    }

                    ActionButton {
                        text: "Cancel"
                        compact: true
                        onClicked: BluetoothService.cancelPending()
                    }
                }
            }
        }
    }
}
