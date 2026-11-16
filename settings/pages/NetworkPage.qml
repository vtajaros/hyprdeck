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

    PageViewport {
        id: viewport
        anchors.fill: parent

        header: PageHeader {
            title: "Network"
            subtitle: (NetworkService.available
                ? ("Connectivity: " + netLogic.connectivityLabel(NetworkService.general.connectivity) + " · ")
                : "")
                + "Interfaces, Wi-Fi networks, and saved connection profiles."

            ActionButton {
                text: root.showDetails ? "Details: On" : "Details"
                compact: true
                variant: root.showDetails ? "accent" : "neutral"
                onClicked: root.showDetails = !root.showDetails
            }

            ActionButton {
                text: NetworkService.general.wifi_enabled ? "Wi-Fi: On" : "Wi-Fi: Off"
                variant: NetworkService.general.wifi_enabled ? "accent" : "neutral"
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

        // Error / NM down banner
        Rectangle {
            visible: !NetworkService.loading && (!NetworkService.available || NetworkService.error.length > 0)
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
            width: viewport.innerWidth
            height: 220
            icon: "󰖪"
            title: "NetworkManager unavailable"
            message: "Ensure NetworkManager is running and click Refresh."
        }

        // Devices
        Column {
            visible: NetworkService.available
            width: viewport.innerWidth
            spacing: HKS.space8

            Text {
                width: parent.width
                text: "Devices (" + NetworkService.devices.length + ")"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSize
                font.weight: Font.Bold
                color: HKS.fg
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: NetworkService.devices
                delegate: DeviceCard {
                    id: devCard
                    required property var modelData
                    width: viewport.innerWidth
                    cardPadding: viewport.cardPadding
                    highlighted: !!devCard.modelData.is_active
                    title: String(devCard.modelData.name || "") + " (" + String(devCard.modelData.type || "") + ")"
                    badges: {
                        var b = [
                            {
                                text: String(devCard.modelData.state || ""),
                                textColor: devCard.modelData.is_active ? HKS.accent : HKS.muted,
                                bgColor: HKS.elevated
                            }
                        ];
                        if (devCard.modelData.is_active) {
                            b.push({
                                text: "Active",
                                textColor: HKS.accent,
                                bgColor: HKS.alpha(HKS.accent, 0.16),
                                borderColor: HKS.alpha(HKS.accent, 0.45)
                            });
                        }
                        return b;
                    }
                    subtitle: {
                        var lines = [];
                        if (devCard.modelData.active_connection) {
                            var s = "Profile: " + String(devCard.modelData.active_connection || "");
                            if (devCard.modelData.ip4_address) s += " · IP: " + devCard.modelData.ip4_address;
                            if (devCard.modelData.ip4_gateway) s += " · GW: " + devCard.modelData.ip4_gateway;
                            lines.push(s);
                        }
                        if ((devCard.modelData.ip4_dns || []).length > 0) {
                            lines.push("DNS: " + (devCard.modelData.ip4_dns || []).join(", "));
                        }
                        return lines.join("\n");
                    }
                    actions: [
                        ActionButton {
                            text: "Disconnect"
                            compact: true
                            visible: !!devCard.modelData.is_active
                            enabled: !NetworkService.busy
                            onClicked: NetworkService.requestDisconnect(devCard.modelData)
                        }
                    ]
                }
            }
        }

        // Wi-Fi Section
        Column {
            visible: NetworkService.available
            width: viewport.innerWidth
            spacing: HKS.space8

            Item {
                id: wifiHdrBox
                width: parent.width
                readonly property bool wrapped: ResponsiveLogic.shouldWrapHeaderActions(
                    wifiHdrBox.width, wifiLblMetrics.advanceWidth, rescanBtn.implicitWidth, HKS.space12
                )
                implicitHeight: wrapped
                    ? (wifiLbl.implicitHeight + HKS.space8 + rescanBtn.height)
                    : Math.max(wifiLbl.implicitHeight, rescanBtn.height)
                height: implicitHeight

                TextMetrics {
                    id: wifiLblMetrics
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.Bold
                    text: wifiLbl.text
                }

                Text {
                    id: wifiLbl
                    x: 0
                    y: wifiHdrBox.wrapped ? 0 : Math.max(0, Math.round((wifiHdrBox.height - height) / 2))
                    width: wifiHdrBox.wrapped ? wifiHdrBox.width : Math.max(0, wifiHdrBox.width - rescanBtn.width - HKS.space12)
                    text: "Wi-Fi Networks (" + NetworkService.wifiNetworks.length + ")" + (NetworkService.scanning ? " — Scanning..." : "")
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSize
                    font.weight: Font.Bold
                    color: HKS.fg
                    wrapMode: Text.WordWrap
                }

                ActionButton {
                    id: rescanBtn
                    x: wifiHdrBox.wrapped ? 0 : Math.max(0, wifiHdrBox.width - width)
                    y: wifiHdrBox.wrapped ? (wifiLbl.implicitHeight + HKS.space8) : Math.max(0, Math.round((wifiHdrBox.height - height) / 2))
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
                width: parent.width
                text: banner
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.warning
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: NetworkService.wifiNetworks
                delegate: DeviceCard {
                    id: wifiCard
                    required property var modelData
                    width: viewport.innerWidth
                    cardPadding: viewport.cardPadding
                    highlighted: !!wifiCard.modelData.in_use
                    title: wifiCard.modelData.hidden ? "(Hidden network)" : String(wifiCard.modelData.ssid || "")
                    badges: {
                        var b = [];
                        if (wifiCard.modelData.in_use) {
                            b.push({
                                text: "Connected",
                                textColor: HKS.accent,
                                bgColor: HKS.alpha(HKS.accent, 0.18),
                                borderColor: HKS.alpha(HKS.accent, 0.4)
                            });
                        } else if (wifiCard.modelData.known) {
                            b.push({
                                text: "Saved",
                                textColor: HKS.muted,
                                bgColor: HKS.elevated
                            });
                        }
                        return b;
                    }
                    subtitle: "Signal: " + String(wifiCard.modelData.signal || 0) + "%"
                        + (wifiCard.modelData.security ? (" · " + wifiCard.modelData.security) : " · Open")

                    actions: [
                        ActionButton {
                            text: wifiCard.modelData.in_use ? "Connected" : "Connect"
                            variant: wifiCard.modelData.in_use ? "neutral" : "accent"
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
                    ]
                }
            }
        }

        // Saved Connections
        Column {
            visible: NetworkService.available
            width: viewport.innerWidth
            spacing: HKS.space8

            Text {
                width: parent.width
                text: "Saved Connections (" + root.savedConnections.length + ")"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSize
                font.weight: Font.Bold
                color: HKS.fg
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: NetworkService.warnings
                delegate: Rectangle {
                    id: warnBanner
                    required property var modelData
                    width: viewport.innerWidth
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
                delegate: DeviceCard {
                    id: connCard
                    required property var modelData
                    width: viewport.innerWidth
                    cardPadding: viewport.cardPadding
                    highlighted: !!connCard.modelData.active
                    title: String(connCard.modelData.name || connCard.modelData.uuid) + (connCard.modelData.active ? " (Active)" : "")
                    subtitle: root.showDetails ? "" : String(connCard.modelData.type || "")
                    detailText: root.showDetails ? (String(connCard.modelData.type || "") + " · " + String(connCard.modelData.uuid || "")) : ""

                    actions: [
                        ActionButton {
                            text: connCard.modelData.autoconnect ? "Auto: On" : "Auto: Off"
                            compact: true
                            enabled: !NetworkService.busy
                            onClicked: NetworkService.setAutoconnect(connCard.modelData.uuid, !connCard.modelData.autoconnect)
                        },
                        ActionButton {
                            text: "Connect"
                            variant: "accent"
                            compact: true
                            visible: !connCard.modelData.active && connCard.modelData.type !== "loopback"
                            enabled: !NetworkService.busy
                            onClicked: NetworkService.connectSaved(connCard.modelData.uuid)
                        },
                        ActionButton {
                            text: "Forget"
                            variant: "danger"
                            compact: true
                            visible: connCard.modelData.type !== "loopback"
                            enabled: !NetworkService.busy
                            onClicked: NetworkService.requestForget(connCard.modelData)
                        }
                    ]
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
            width: Math.min(420, parent.width - HKS.space24)
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
                    width: parent.width
                    text: "Connect to " + root.joinPromptSsid
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeMedium
                    font.weight: Font.Bold
                    color: HKS.fg
                    wrapMode: Text.WordWrap
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

                Flow {
                    width: parent.width
                    layoutDirection: Qt.RightToLeft
                    spacing: HKS.space8

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

                    ActionButton {
                        text: "Cancel"
                        compact: true
                        onClicked: root.closeJoinPrompt()
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
            width: Math.min(440, parent.width - HKS.space24)
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

                Flow {
                    width: parent.width
                    layoutDirection: Qt.RightToLeft
                    spacing: HKS.space8

                    ActionButton {
                        text: "Confirm"
                        variant: "danger"
                        compact: true
                        onClicked: NetworkService.confirmPending()
                    }

                    ActionButton {
                        text: "Cancel"
                        compact: true
                        onClicked: NetworkService.cancelPending()
                    }
                }
            }
        }
    }
}
