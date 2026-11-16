import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    PowerControlLogic {
        id: pwrLogic
    }

    property int draftDimMin: 5
    property int draftLockMin: 10
    property int draftDpmsMin: 15
    property bool draftsDirty: false

    function syncDraftsFromState() {
        var listeners = (PowerService.hypridle && PowerService.hypridle.listeners) ? PowerService.hypridle.listeners : [];
        for (var i = 0; i < listeners.length; i++) {
            var l = listeners[i];
            if (!l) continue;
            if (l.role === "dim") root.draftDimMin = pwrLogic.secToMin(l.timeout);
            else if (l.role === "lock") root.draftLockMin = pwrLogic.secToMin(l.timeout);
            else if (l.role === "dpms") root.draftDpmsMin = pwrLogic.secToMin(l.timeout);
        }
        root.draftsDirty = false;
    }

    readonly property string idleValidationErr: pwrLogic.validateIdleOrder(
        pwrLogic.minToSec(draftDimMin),
        pwrLogic.minToSec(draftLockMin),
        pwrLogic.minToSec(draftDpmsMin)
    )

    Connections {
        target: PowerService
        function onHypridleChanged() {
            if (!root.draftsDirty) {
                root.syncDraftsFromState();
            }
        }
    }

    Component.onCompleted: root.syncDraftsFromState()

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
                    text: "Power"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: "Battery health, CPU performance profile, screen idle, and sleep info."
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
                    text: PowerService.busy ? "Applying..." : "Refresh"
                    compact: true
                    enabled: !PowerService.busy
                    onClicked: {
                        root.draftsDirty = false;
                        PowerService.reload(false);
                    }
                }
            }
        }

        // Error banner
        Rectangle {
            visible: !PowerService.loading && PowerService.error.length > 0
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
                text: PowerService.error
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Status banner
        Rectangle {
            visible: PowerService.statusMessage.length > 0 && PowerService.error.length === 0
            width: parent.width
            height: stTxt.implicitHeight + 16
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.accent, 0.14)
            border.width: 1
            border.color: HKS.alpha(HKS.accent, 0.45)

            Text {
                id: stTxt
                anchors.fill: parent
                anchors.margins: 8
                text: PowerService.statusMessage
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.accent
                wrapMode: Text.WordWrap
            }
        }

        EmptyState {
            visible: !PowerService.loading && !PowerService.available
            width: parent.width
            height: 220
            icon: "󰁹"
            title: "Power controls unavailable"
            message: "No battery, CPU cpufreq, or hypridle backend detected."
        }

        Flickable {
            id: flick
            visible: PowerService.available
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

                // Battery Card
                Rectangle {
                    visible: !!PowerService.capabilities.has_battery
                    width: parent.width
                    height: batCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: batCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: 6

                        Text {
                            text: "Battery (" + String(PowerService.battery.name || "BAT1") + ") — "
                                + String(PowerService.battery.percentage !== undefined && PowerService.battery.percentage !== null ? PowerService.battery.percentage : "?") + "% · "
                                + String(PowerService.battery.state || "unknown")
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.DemiBold
                            color: HKS.fg
                        }

                        Text {
                            text: "Health: " + (PowerService.battery.health_percent !== null && PowerService.battery.health_percent !== undefined ? (PowerService.battery.health_percent + "%") : "Unknown")
                                + " · Rate: " + (PowerService.battery.energy_rate_w !== null && PowerService.battery.energy_rate_w !== undefined ? (PowerService.battery.energy_rate_w + " W") : "0 W")
                                + (PowerService.battery.ac_online !== null && PowerService.battery.ac_online !== undefined ? (" · AC: " + (PowerService.battery.ac_online ? "Online" : "Battery")) : "")
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                        }

                        Text {
                            visible: !!(PowerService.battery.time_to_empty || PowerService.battery.time_to_full)
                            text: PowerService.battery.time_to_empty
                                ? ("Time to empty: " + PowerService.battery.time_to_empty)
                                : ("Time to full: " + (PowerService.battery.time_to_full || ""))
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                        }

                        Text {
                            visible: PowerService.battery.charge_cycles !== null && PowerService.battery.charge_cycles !== undefined
                            text: "Charge cycles: " + String(PowerService.battery.charge_cycles || "")
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                        }

                        Text {
                            visible: PowerService.battery.charge_end_threshold !== null && PowerService.battery.charge_end_threshold !== undefined
                            text: "Charge threshold: " + String(PowerService.battery.charge_end_threshold || "") + "%"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                        }
                    }
                }

                // Performance Card (EPP + Turbo)
                Rectangle {
                    visible: !!PowerService.cpu.available
                    width: parent.width
                    height: perfCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: perfCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: HKS.space8

                        Text {
                            text: "Performance (" + String(PowerService.cpu.driver || "cpu") + ", " + String(PowerService.cpu.cpu_count || 0) + " threads)"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.DemiBold
                            color: HKS.fg
                        }

                        Text {
                            text: "Session only, resets on reboot, asks for your password."
                            font.family: HKS.fontFamily
                            font.pixelSize: 11
                            color: HKS.muted
                        }

                        Flow {
                            visible: !!PowerService.capabilities.can_write_epp
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: PowerService.cpu.epp_available || []
                                delegate: ActionButton {
                                    required property string modelData
                                    text: pwrLogic.eppLabel(modelData)
                                    variant: PowerService.cpu.epp_current === modelData ? "accent" : "secondary"
                                    compact: true
                                    enabled: !PowerService.busy
                                    onClicked: PowerService.setEpp(modelData)
                                }
                            }
                        }

                        Row {
                            visible: !!PowerService.capabilities.can_write_turbo
                            width: parent.width
                            spacing: HKS.space12

                            Text {
                                width: Math.max(160, parent.width - turboBtn.width - HKS.space12)
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Intel Turbo Boost: " + (PowerService.cpu.turbo_enabled ? "Enabled" : "Disabled")
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                color: HKS.fg
                            }

                            ActionButton {
                                id: turboBtn
                                text: PowerService.cpu.turbo_enabled ? "Disable Turbo" : "Enable Turbo"
                                variant: PowerService.cpu.turbo_enabled ? "secondary" : "accent"
                                compact: true
                                enabled: !PowerService.busy
                                onClicked: PowerService.requestTurbo(!PowerService.cpu.turbo_enabled)
                            }
                        }
                    }
                }

                // Screen Idle Card (hypridle)
                Rectangle {
                    visible: !!PowerService.capabilities.hypridle_present
                    width: parent.width
                    height: idleCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: idleCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: HKS.space8

                        Row {
                            width: parent.width
                            spacing: HKS.space8

                            Text {
                                width: Math.max(160, parent.width - idleActions.width - HKS.space8)
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Screen Idle (hypridle: " + (PowerService.hypridle.running ? "running" : "stopped") + ")"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSize
                                font.weight: Font.DemiBold
                                color: HKS.fg
                            }

                            Row {
                                id: idleActions
                                spacing: HKS.space8

                                ActionButton {
                                    text: "Revert"
                                    compact: true
                                    enabled: root.draftsDirty && !PowerService.busy
                                    onClicked: root.syncDraftsFromState()
                                }

                                ActionButton {
                                    text: "Apply"
                                    variant: "accent"
                                    compact: true
                                    enabled: root.draftsDirty && root.idleValidationErr.length === 0 && !PowerService.busy
                                    onClicked: {
                                        root.draftsDirty = false;
                                        PowerService.setIdleTimeouts(
                                            pwrLogic.minToSec(root.draftDimMin),
                                            pwrLogic.minToSec(root.draftLockMin),
                                            pwrLogic.minToSec(root.draftDpmsMin)
                                        );
                                    }
                                }
                            }
                        }

                        // Dim stepper
                        Row {
                            width: parent.width
                            spacing: HKS.space8
                            Text {
                                width: parent.width - 140
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Dim screen: " + root.draftDimMin + " min"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                color: HKS.fg
                            }
                            ActionButton {
                                text: "-"
                                compact: true
                                enabled: root.draftDimMin > 1
                                onClicked: { root.draftDimMin--; root.draftsDirty = true; }
                            }
                            ActionButton {
                                text: "+"
                                compact: true
                                enabled: root.draftDimMin < 1440
                                onClicked: { root.draftDimMin++; root.draftsDirty = true; }
                            }
                        }

                        // Lock stepper
                        Row {
                            width: parent.width
                            spacing: HKS.space8
                            Text {
                                width: parent.width - 140
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Lock session: " + root.draftLockMin + " min"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                color: HKS.fg
                            }
                            ActionButton {
                                text: "-"
                                compact: true
                                enabled: root.draftLockMin > 1
                                onClicked: { root.draftLockMin--; root.draftsDirty = true; }
                            }
                            ActionButton {
                                text: "+"
                                compact: true
                                enabled: root.draftLockMin < 1440
                                onClicked: { root.draftLockMin++; root.draftsDirty = true; }
                            }
                        }

                        // DPMS off stepper
                        Row {
                            width: parent.width
                            spacing: HKS.space8
                            Text {
                                width: parent.width - 140
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Turn off display: " + root.draftDpmsMin + " min"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                color: HKS.fg
                            }
                            ActionButton {
                                text: "-"
                                compact: true
                                enabled: root.draftDpmsMin > 1
                                onClicked: { root.draftDpmsMin--; root.draftsDirty = true; }
                            }
                            ActionButton {
                                text: "+"
                                compact: true
                                enabled: root.draftDpmsMin < 1440
                                onClicked: { root.draftDpmsMin++; root.draftsDirty = true; }
                            }
                        }

                        Text {
                            visible: root.idleValidationErr.length > 0
                            text: root.idleValidationErr
                            font.family: HKS.fontFamily
                            font.pixelSize: 11
                            color: HKS.critical
                            width: parent.width
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                // Read-only Lid and Sleep Card
                Rectangle {
                    visible: !!PowerService.lidSleep.available
                    width: parent.width
                    height: lidCol.implicitHeight + 24
                    radius: HKS.radiusMedium
                    color: HKS.surface
                    border.width: 1
                    border.color: HKS.alpha(HKS.muted, 0.18)

                    Column {
                        id: lidCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: HKS.space12
                        spacing: 4

                        Text {
                            text: "Lid & Sleep (Read-Only)"
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSize
                            font.weight: Font.DemiBold
                            color: HKS.fg
                        }
                        Text {
                            text: "Sleep mode: " + String(PowerService.lidSleep.mem_sleep || "unknown")
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                        }
                        Text {
                            text: "Lid switch: battery=" + String(PowerService.lidSleep.handle_lid_switch || "suspend")
                                + " · ac=" + String(PowerService.lidSleep.handle_lid_switch_external_power || "suspend")
                                + " · docked=" + String(PowerService.lidSleep.handle_lid_switch_docked || "ignore")
                            font.family: HKS.fontFamily
                            font.pixelSize: HKS.fontSizeSmall
                            color: HKS.muted
                            wrapMode: Text.WordWrap
                            width: parent.width
                        }
                    }
                }
            }
        }
    }

    // Confirm Modal (only for turning Turbo Boost OFF)
    Rectangle {
        anchors.fill: parent
        visible: PowerService.confirmOpen
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
                    text: PowerService.confirmTitle
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeMedium
                    font.weight: Font.Bold
                    color: HKS.fg
                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Text {
                    text: PowerService.confirmMessage
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
                        onClicked: PowerService.cancelPending()
                    }

                    ActionButton {
                        text: "Disable Turbo"
                        variant: "danger"
                        compact: true
                        onClicked: PowerService.confirmPending()
                    }
                }
            }
        }
    }
}
