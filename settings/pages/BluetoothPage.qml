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
                    text: "Bluetooth"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: BluetoothService.controller
                        ? ("Adapter: " + (BluetoothService.controller.alias || "hci0") + " (" + (BluetoothService.controller.address || "") + ")")
                        : "Bluetooth controller, paired devices, and scanning."
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
                    text: root.ctrlPowered ? "Power: On" : "Power: Off"
                    variant: root.ctrlPowered ? "accent" : "secondary"
                    compact: true
                    enabled: BluetoothService.available && !BluetoothService.busy && !BluetoothService.rfkill.hard_blocked
                    onClicked: BluetoothService.requestPower(!root.ctrlPowered)
                }

                ActionButton {
                    text: root.ctrlPairable ? "Pairable: On" : "Pairable: Off"
                    variant: root.ctrlPairable ? "accent" : "secondary"
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
        }

        // rfkill blocked banner
        Rectangle {
            visible: !BluetoothService.loading && (BluetoothService.rfkill.hard_blocked || BluetoothService.rfkill.soft_blocked)
            width: parent.width
            height: rfTxt.implicitHeight + 16
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.warning, 0.14)
            border.width: 1
            border.color: HKS.alpha(HKS.warning, 0.5)

            Text {
                id: rfTxt
                anchors.fill: parent
                anchors.margins: 8
                text: BluetoothService.rfkill.hard_blocked
                    ? "Bluetooth is hardware-blocked (rfkill hard block). Use your hardware switch to unblock."
                    : "Bluetooth is software-blocked (rfkill soft block). Click Power: On to unblock and power on."
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.warning
                wrapMode: Text.WordWrap
            }
        }

        // Error / daemon absent banner
        Rectangle {
            visible: !BluetoothService.loading && !BluetoothService.noController && (!BluetoothService.available || BluetoothService.error.length > 0)
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
                text: BluetoothService.error.length > 0
                    ? BluetoothService.error
                    : "Bluetooth daemon (bluetoothd) unavailable."
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Manual pairing (blueman-manager) fallback banner
        Rectangle {
            visible: BluetoothService.needsManualPairing
            width: parent.width
            height: Math.max(manualTxt.implicitHeight + 16, 40)
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.accent, 0.12)
            border.width: 1
            border.color: HKS.alpha(HKS.accent, 0.45)

            Row {
                anchors.fill: parent
                anchors.margins: 8
                spacing: HKS.space12

                Text {
                    id: manualTxt
                    width: parent.width - bluemanBtn.width - HKS.space12
                    anchors.verticalCenter: parent.verticalCenter
                    text: "This device requires passkey or PIN confirmation."
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: HKS.fg
                    wrapMode: Text.WordWrap
                }

                ActionButton {
                    id: bluemanBtn
                    text: "Open Blueman Manager"
                    variant: "accent"
                    compact: true
                    onClicked: BluetoothService.launchBlueman()
                }
            }
        }

        // Empty state: no controller
        EmptyState {
            visible: !BluetoothService.loading && BluetoothService.noController
            width: parent.width
            height: 220
            icon: "󰂲"
            title: "No Bluetooth controller found"
            message: "Ensure a Bluetooth adapter is attached and bluetoothd is running."
        }

        // Scrollable content
        Flickable {
            id: flick
            visible: BluetoothService.available && !BluetoothService.noController
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

                // Paired Devices
                Column {
                    width: parent.width
                    spacing: HKS.space8

                    Text {
                        text: "Paired Devices (" + root.pairedList.length + ")"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Text {
                        visible: root.pairedList.length === 0
                        text: "No paired devices."
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                    }

                    Repeater {
                        model: root.pairedList
                        delegate: Rectangle {
                            id: pairedCard
                            required property var modelData
                            width: contentCol.width
                            height: pairedRow.implicitHeight + 24
                            radius: HKS.radiusMedium
                            color: HKS.surface
                            border.width: 1
                            border.color: modelData.connected ? HKS.accent : HKS.alpha(HKS.muted, 0.18)

                            Row {
                                id: pairedRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: HKS.space12
                                spacing: HKS.space12

                                Column {
                                    width: Math.max(180, parent.width - pairedActions.width - HKS.space12)
                                    spacing: 2

                                    Row {
                                        spacing: 8
                                        Text {
                                            text: String(pairedCard.modelData.alias || pairedCard.modelData.name || pairedCard.modelData.address)
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSize
                                            font.weight: Font.DemiBold
                                            color: HKS.fg
                                        }
                                        Rectangle {
                                            visible: !!pairedCard.modelData.connected
                                            width: connBadge.implicitWidth + 10
                                            height: 18
                                            radius: 4
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: HKS.alpha(HKS.accent, 0.18)
                                            Text {
                                                id: connBadge
                                                anchors.centerIn: parent
                                                text: pairedCard.modelData.is_default_sink ? "Connected · Default Audio" : "Connected"
                                                font.family: HKS.fontFamily
                                                font.pixelSize: 10
                                                color: HKS.accent
                                            }
                                        }
                                        Text {
                                            visible: !!pairedCard.modelData.trusted
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: "Trusted"
                                            font.family: HKS.fontFamily
                                            font.pixelSize: 10
                                            color: HKS.muted
                                        }
                                    }

                                    Text {
                                        text: String(pairedCard.modelData.address || "") + (pairedCard.modelData.is_audio ? " · Audio" : "")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.muted
                                    }
                                }

                                Row {
                                    id: pairedActions
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: HKS.space8

                                    ActionButton {
                                        text: pairedCard.modelData.connected ? "Disconnect" : "Connect"
                                        variant: pairedCard.modelData.connected ? "secondary" : "accent"
                                        compact: true
                                        enabled: root.ctrlPowered && !BluetoothService.busy
                                        onClicked: {
                                            if (pairedCard.modelData.connected) {
                                                BluetoothService.requestDisconnect(pairedCard.modelData);
                                            } else {
                                                BluetoothService.connect(pairedCard.modelData.address);
                                            }
                                        }
                                    }

                                    ActionButton {
                                        text: pairedCard.modelData.trusted ? "Untrust" : "Trust"
                                        compact: true
                                        enabled: !BluetoothService.busy
                                        onClicked: BluetoothService.setTrusted(pairedCard.modelData.address, !pairedCard.modelData.trusted)
                                    }

                                    ActionButton {
                                        text: "Remove"
                                        variant: "danger"
                                        compact: true
                                        enabled: !BluetoothService.busy
                                        onClicked: BluetoothService.requestRemove(pairedCard.modelData)
                                    }
                                }
                            }
                        }
                    }
                }

                // Scan & Discovered Devices
                Column {
                    width: parent.width
                    spacing: HKS.space8

                    Row {
                        width: parent.width
                        spacing: HKS.space12

                        Text {
                            width: Math.max(160, parent.width - scanBtn.width - HKS.space12)
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Nearby Devices (" + root.discoveredList.length + ")" + (BluetoothService.scanning ? " — Scanning..." : "")
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.Bold
                            color: HKS.fg
                        }

                        ActionButton {
                            id: scanBtn
                            text: BluetoothService.scanning ? "Stop Scan" : "Scan"
                            variant: BluetoothService.scanning ? "secondary" : "accent"
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
                        text: BluetoothService.scanning
                            ? "Listening for nearby Bluetooth devices..."
                            : "Click Scan to discover nearby unpaired devices."
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                    }

                    Repeater {
                        model: root.discoveredList
                        delegate: Rectangle {
                            id: discCard
                            required property var modelData
                            width: contentCol.width
                            height: discRow.implicitHeight + 20
                            radius: HKS.radiusSmall
                            color: HKS.surface
                            border.width: 1
                            border.color: HKS.alpha(HKS.muted, 0.14)

                            Row {
                                id: discRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: HKS.space12
                                spacing: HKS.space12

                                Column {
                                    width: Math.max(160, parent.width - pairBtn.width - HKS.space12)
                                    spacing: 2

                                    Text {
                                        text: String(discCard.modelData.alias || discCard.modelData.name || discCard.modelData.address)
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        font.weight: Font.DemiBold
                                        color: HKS.fg
                                    }

                                    Text {
                                        readonly property string rssiTxt: btLogic.rssiLabel(discCard.modelData.rssi)
                                        text: String(discCard.modelData.address || "") + (rssiTxt.length > 0 ? (" · " + rssiTxt) : "")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.muted
                                    }
                                }

                                ActionButton {
                                    id: pairBtn
                                    text: "Pair"
                                    variant: "accent"
                                    compact: true
                                    enabled: root.ctrlPowered && !BluetoothService.busy
                                    onClicked: BluetoothService.pair(discCard.modelData.address)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Confirmation Modal for disruptive/destructive actions
    Rectangle {
        anchors.fill: parent
        visible: BluetoothService.confirmOpen
        color: HKS.alpha(HKS.bg, 0.72)
        z: 30

        MouseArea { anchors.fill: parent }

        Rectangle {
            anchors.centerIn: parent
            width: 440
            height: modalCol.implicitHeight + 36
            radius: HKS.radius
            color: HKS.surface
            border.width: 1
            border.color: HKS.warning

            Column {
                id: modalCol
                anchors.fill: parent
                anchors.margins: 18
                spacing: HKS.space12

                Text {
                    text: BluetoothService.confirmTitle
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeMedium
                    font.weight: Font.Bold
                    color: HKS.fg
                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Text {
                    text: BluetoothService.confirmMessage
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: HKS.warning
                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Row {
                    anchors.right: parent.right
                    spacing: HKS.space8

                    ActionButton {
                        text: "Cancel"
                        compact: true
                        onClicked: BluetoothService.cancelPending()
                    }

                    ActionButton {
                        text: "Confirm"
                        variant: "danger"
                        compact: true
                        onClicked: BluetoothService.confirmPending()
                    }
                }
            }
        }
    }
}
