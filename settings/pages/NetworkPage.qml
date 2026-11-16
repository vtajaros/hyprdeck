import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    NetworkControlLogic {
        id: netLogic
    }

    property string joinPromptSsid: ""
    property string joinPromptSecurity: ""
    property bool joinPromptOpen: false
    property bool showDetails: false
    readonly property var savedConnections: netLogic.savedConnectionsExcludingActiveDevices(NetworkService.connections, NetworkService.devices)

    function openJoinPrompt(ssid, security) {
        root.joinPromptSsid = String(ssid || "");
        root.joinPromptSecurity = String(security || "");
        pwInput.text = "";
        root.joinPromptOpen = true;
    }

    function closeJoinPrompt() {
        pwInput.text = "";
        root.joinPromptOpen = false;
        root.joinPromptSsid = "";
        root.joinPromptSecurity = "";
    }

    Column {
        anchors.fill: parent
        anchors.margins: HKS.space24
        spacing: HKS.space12

        // Status Header
        Row {
            width: parent.width
            spacing: HKS.space12

            Column {
                width: Math.max(200, parent.width - headerActions.width - HKS.space12)
                spacing: 4

                Row {
                    spacing: 10
                    Text {
                        text: "Network"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeTitle
                        font.weight: Font.Bold
                        color: HKS.fg
                    }
                    Rectangle {
                        visible: NetworkService.available
                        width: connPill.implicitWidth + 12
                        height: 20
                        radius: 4
                        anchors.verticalCenter: parent.verticalCenter
                        color: NetworkService.general.connectivity === "full"
                            ? HKS.alpha(HKS.accent, 0.18)
                            : HKS.alpha(HKS.warning, 0.18)
                        Text {
                            id: connPill
                            anchors.centerIn: parent
                            text: netLogic.connectivityLabel(NetworkService.general.connectivity)
                            font.family: HKS.fontFamily
                            font.pixelSize: 11
                            color: NetworkService.general.connectivity === "full" ? HKS.accent : HKS.warning
                        }
                    }
                }

                Text {
                    text: "Interfaces, Wi-Fi networks, and saved connection profiles."
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
                    text: root.showDetails ? "Details: On" : "Details"
                    compact: true
                    variant: root.showDetails ? "accent" : "neutral"
                    onClicked: root.showDetails = !root.showDetails
                }

                ActionButton {
                    text: NetworkService.general.wifi_enabled ? "Wi-Fi: On" : "Wi-Fi: Off"
                    variant: NetworkService.general.wifi_enabled ? "accent" : "secondary"
                    compact: true
                    enabled: NetworkService.available && NetworkService.hasWifiDevice && NetworkService.general.wifi_hw_enabled && !NetworkService.busy
                    onClicked: NetworkService.requestWifiEnabled(!NetworkService.general.wifi_enabled)
                }

                ActionButton {
                    text: NetworkService.busy ? "Working..." : "Refresh"
                    compact: true
                    enabled: !NetworkService.busy
                    onClicked: NetworkService.reload(false)
                }
            }
        }

        // Error / NM down banner
        Rectangle {
            visible: !NetworkService.loading && (!NetworkService.available || NetworkService.error.length > 0)
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
                text: NetworkService.error.length > 0
                    ? NetworkService.error
                    : "NetworkManager is unavailable."
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Empty state when NM is down
        EmptyState {
            visible: !NetworkService.loading && !NetworkService.available
            width: parent.width
            height: 220
            icon: "󰖪"
            title: "NetworkManager unavailable"
            message: "Ensure NetworkManager is running and click Refresh."
        }

        // Scrollable content
        Flickable {
            id: flick
            visible: NetworkService.available
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

                // Devices
                Column {
                    width: parent.width
                    spacing: HKS.space8

                    Text {
                        text: "Devices (" + NetworkService.devices.length + ")"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Repeater {
                        model: NetworkService.devices
                        delegate: Rectangle {
                            id: devCard
                            required property var modelData
                            width: contentCol.width
                            height: devRow.implicitHeight + 24
                            radius: HKS.radiusMedium
                            color: HKS.surface
                            border.width: 1
                            border.color: modelData.is_active ? HKS.accent : HKS.alpha(HKS.muted, 0.18)

                            Row {
                                id: devRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: HKS.space12
                                spacing: HKS.space12

                                Column {
                                    width: Math.max(180, parent.width - devActions.width - HKS.space12)
                                    spacing: 2

                                    Row {
                                        spacing: 8
                                        Text {
                                            text: String(devCard.modelData.name || "") + " (" + String(devCard.modelData.type || "") + ")"
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSize
                                            font.weight: Font.DemiBold
                                            color: HKS.fg
                                        }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: String(devCard.modelData.state || "")
                                            font.family: HKS.fontFamily
                                            font.pixelSize: 11
                                            color: devCard.modelData.is_active ? HKS.accent : HKS.muted
                                        }
                                        Rectangle {
                                            visible: !!devCard.modelData.is_active
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: activeTagTxt.implicitWidth + 10
                                            height: 18
                                            radius: 4
                                            color: HKS.alpha(HKS.accent, 0.16)
                                            border.width: 1
                                            border.color: HKS.alpha(HKS.accent, 0.45)
                                            Text {
                                                id: activeTagTxt
                                                anchors.centerIn: parent
                                                text: "Active"
                                                font.family: HKS.fontFamily
                                                font.pixelSize: 10
                                                color: HKS.accent
                                            }
                                        }
                                    }

                                    Text {
                                        visible: !!(devCard.modelData.active_connection)
                                        text: "Profile: " + String(devCard.modelData.active_connection || "")
                                            + (devCard.modelData.ip4_address ? (" · IP: " + devCard.modelData.ip4_address) : "")
                                            + (devCard.modelData.ip4_gateway ? (" · GW: " + devCard.modelData.ip4_gateway) : "")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.muted
                                    }

                                    Text {
                                        visible: (devCard.modelData.ip4_dns || []).length > 0
                                        text: "DNS: " + (devCard.modelData.ip4_dns || []).join(", ")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.muted
                                    }
                                }

                                Row {
                                    id: devActions
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: HKS.space8

                                    ActionButton {
                                        text: "Disconnect"
                                        compact: true
                                        visible: !!devCard.modelData.is_active
                                        enabled: !NetworkService.busy
                                        onClicked: NetworkService.requestDisconnect(devCard.modelData)
                                    }
                                }
                            }
                        }
                    }
                }

                // Wi-Fi Section
                Column {
                    width: parent.width
                    spacing: HKS.space8

                    Row {
                        width: parent.width
                        spacing: HKS.space12

                        Text {
                            width: Math.max(160, parent.width - rescanBtn.width - HKS.space12)
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Wi-Fi Networks (" + NetworkService.wifiNetworks.length + ")" + (NetworkService.scanning ? " — Scanning..." : "")
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.Bold
                            color: HKS.fg
                        }

                        ActionButton {
                            id: rescanBtn
                            text: NetworkService.scanning ? "Scanning..." : "Rescan"
                            variant: "accent"
                            compact: true
                            enabled: NetworkService.hasWifiDevice && NetworkService.general.wifi_enabled && NetworkService.general.wifi_hw_enabled && !NetworkService.busy
                            onClicked: NetworkService.rescan()
                        }
                    }

                    Text {
                        readonly property string banner: netLogic.wifiStateBanner(NetworkService.available, NetworkService.hasWifiDevice, NetworkService.general)
                        visible: banner.length > 0
                        text: banner
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.warning
                    }

                    Repeater {
                        model: NetworkService.wifiNetworks
                        delegate: Rectangle {
                            id: wifiCard
                            required property var modelData
                            width: contentCol.width
                            height: wifiRow.implicitHeight + 20
                            radius: HKS.radiusSmall
                            color: HKS.surface
                            border.width: 1
                            border.color: modelData.in_use ? HKS.accent : HKS.alpha(HKS.muted, 0.14)

                            Row {
                                id: wifiRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: HKS.space12
                                spacing: HKS.space12

                                Column {
                                    width: Math.max(160, parent.width - wifiBtn.width - HKS.space12)
                                    spacing: 2

                                    Row {
                                        spacing: 8
                                        Text {
                                            text: wifiCard.modelData.hidden ? "(Hidden network)" : String(wifiCard.modelData.ssid || "")
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            font.weight: Font.DemiBold
                                            color: HKS.fg
                                        }
                                        Text {
                                            visible: !!wifiCard.modelData.in_use
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: "Connected"
                                            font.family: HKS.fontFamily
                                            font.pixelSize: 10
                                            color: HKS.accent
                                        }
                                        Text {
                                            visible: !!wifiCard.modelData.known && !wifiCard.modelData.in_use
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: "Saved"
                                            font.family: HKS.fontFamily
                                            font.pixelSize: 10
                                            color: HKS.muted
                                        }
                                    }

                                    Text {
                                        text: "Signal: " + String(wifiCard.modelData.signal || 0) + "%"
                                            + (wifiCard.modelData.security ? (" · " + wifiCard.modelData.security) : " · Open")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.muted
                                    }
                                }

                                ActionButton {
                                    id: wifiBtn
                                    text: wifiCard.modelData.in_use ? "Connected" : "Connect"
                                    variant: wifiCard.modelData.in_use ? "secondary" : "accent"
                                    compact: true
                                    enabled: !wifiCard.modelData.in_use && !wifiCard.modelData.hidden && !NetworkService.busy
                                    onClicked: {
                                        var sec = String(wifiCard.modelData.security || "").trim();
                                        if (sec.length === 0 || sec === "--") {
                                            NetworkService.joinWifi(wifiCard.modelData.ssid, "", "");
                                        } else {
                                            root.openJoinPrompt(wifiCard.modelData.ssid, sec);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Saved Connections
                Column {
                    width: parent.width
                    spacing: HKS.space8

                    Text {
                        text: "Saved Connections (" + root.savedConnections.length + ")"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.Bold
                        color: HKS.fg
                    }

                    Repeater {
                        model: NetworkService.warnings
                        delegate: Rectangle {
                            id: warnBanner
                            required property var modelData
                            width: contentCol.width
                            height: warnTxt.implicitHeight + 16
                            radius: HKS.radiusSmall
                            color: HKS.alpha(HKS.warning, 0.14)
                            border.width: 1
                            border.color: HKS.alpha(HKS.warning, 0.5)

                            Text {
                                id: warnTxt
                                anchors.fill: parent
                                anchors.margins: 8
                                text: String(warnBanner.modelData.message || "")
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                color: HKS.warning
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    Repeater {
                        model: root.savedConnections
                        delegate: Rectangle {
                            id: connCard
                            required property var modelData
                            width: contentCol.width
                            height: connRow.implicitHeight + 20
                            radius: HKS.radiusSmall
                            color: HKS.surface
                            border.width: 1
                            border.color: modelData.active ? HKS.accent : HKS.alpha(HKS.muted, 0.14)

                            Row {
                                id: connRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: HKS.space12
                                spacing: HKS.space12

                                Column {
                                    width: Math.max(160, parent.width - connActions.width - HKS.space12)
                                    spacing: 2

                                    Text {
                                        text: String(connCard.modelData.name || connCard.modelData.uuid) + (connCard.modelData.active ? " (Active)" : "")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        font.weight: Font.DemiBold
                                        color: HKS.fg
                                    }

                                    Text {
                                        text: root.showDetails
                                            ? (String(connCard.modelData.type || "") + " · " + String(connCard.modelData.uuid || ""))
                                            : String(connCard.modelData.type || "")
                                        font.family: HKS.fontFamily
                                        font.pixelSize: 11
                                        color: HKS.muted
                                        elide: Text.ElideMiddle
                                        width: parent.width
                                    }
                                }

                                Row {
                                    id: connActions
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: HKS.space8

                                    ActionButton {
                                        text: connCard.modelData.autoconnect ? "Auto: On" : "Auto: Off"
                                        compact: true
                                        enabled: !NetworkService.busy
                                        onClicked: NetworkService.setAutoconnect(connCard.modelData.uuid, !connCard.modelData.autoconnect)
                                    }

                                    ActionButton {
                                        text: "Connect"
                                        variant: "accent"
                                        compact: true
                                        visible: !connCard.modelData.active && connCard.modelData.type !== "loopback"
                                        enabled: !NetworkService.busy
                                        onClicked: NetworkService.connectSaved(connCard.modelData.uuid)
                                    }

                                    ActionButton {
                                        text: "Forget"
                                        variant: "danger"
                                        compact: true
                                        visible: connCard.modelData.type !== "loopback"
                                        enabled: !NetworkService.busy
                                        onClicked: NetworkService.requestForget(connCard.modelData)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Masked Password Entry Modal (never persisted or echoed)
    Rectangle {
        anchors.fill: parent
        visible: root.joinPromptOpen
        color: HKS.alpha(HKS.bg, 0.72)
        z: 30

        MouseArea { anchors.fill: parent }

        Rectangle {
            anchors.centerIn: parent
            width: 420
            height: pwCol.implicitHeight + 36
            radius: HKS.radius
            color: HKS.surface
            border.width: 1
            border.color: HKS.accent

            Column {
                id: pwCol
                anchors.fill: parent
                anchors.margins: 18
                spacing: HKS.space12

                Text {
                    text: "Connect to " + root.joinPromptSsid
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeMedium
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Rectangle {
                    width: parent.width
                    height: 36
                    radius: HKS.radiusSmall
                    color: HKS.elevated
                    border.width: 1
                    border.color: HKS.alpha(HKS.accent, 0.5)

                    TextInput {
                        id: pwInput
                        anchors.fill: parent
                        anchors.margins: 8
                        echoMode: TextInput.Password
                        color: HKS.fg
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        clip: true
                    }
                }

                Row {
                    anchors.right: parent.right
                    spacing: HKS.space8

                    ActionButton {
                        text: "Cancel"
                        compact: true
                        onClicked: root.closeJoinPrompt()
                    }

                    ActionButton {
                        text: "Connect"
                        variant: "accent"
                        compact: true
                        onClicked: {
                            var ssid = root.joinPromptSsid;
                            var sec = root.joinPromptSecurity;
                            var pw = pwInput.text;
                            root.closeJoinPrompt();
                            NetworkService.joinWifi(ssid, sec, pw);
                        }
                    }
                }
            }
        }
    }

    // Confirmation Modal for disruptive/destructive actions
    Rectangle {
        anchors.fill: parent
        visible: NetworkService.confirmOpen
        color: HKS.alpha(HKS.bg, 0.72)
        z: 35

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
                    text: NetworkService.confirmTitle
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeMedium
                    font.weight: Font.Bold
                    color: HKS.fg
                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Text {
                    text: NetworkService.confirmMessage
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
                        onClicked: NetworkService.cancelPending()
                    }

                    ActionButton {
                        text: "Confirm"
                        variant: "danger"
                        compact: true
                        onClicked: NetworkService.confirmPending()
                    }
                }
            }
        }
    }
}
