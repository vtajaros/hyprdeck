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

    PageViewport {
        id: viewport
        anchors.fill: parent

        header: PageHeader {
            title: "Power"
            subtitle: "Battery health, CPU performance profile, screen idle, and sleep info."

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

        // Error banner
        Rectangle {
            visible: !PowerService.loading && PowerService.error.length > 0
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
                text: PowerService.error
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.critical
                wrapMode: Text.WordWrap
            }
        }

        // Status banner
        Rectangle {
            visible: PowerService.statusMessage.length > 0 && PowerService.error.length === 0
            width: viewport.innerWidth
            height: stTxt.implicitHeight + 16
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.accent, 0.14)
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.45)

            Text {
                id: stTxt
                anchors.fill: parent
                anchors.margins: 8
                text: PowerService.statusMessage
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.accent
                wrapMode: Text.WordWrap
            }
        }

        EmptyState {
            visible: !PowerService.loading && !PowerService.available
            width: viewport.innerWidth
            height: 220
            icon: "󰁹"
            title: "Power controls unavailable"
            message: "No battery, CPU cpufreq, or hypridle backend detected."
        }

        // Battery Card
        SectionCard {
            visible: PowerService.available && !!PowerService.capabilities.has_battery
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding
            spacing: 6

            Text {
                width: parent.width
                text: "Battery (" + String(PowerService.battery.name || "BAT1") + ") — "
                    + String(PowerService.battery.percentage !== undefined && PowerService.battery.percentage !== null ? PowerService.battery.percentage : "?") + "% · "
                    + String(PowerService.battery.state || "unknown")
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.DemiBold
                color: Deck.fg
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                text: "Health: " + (PowerService.battery.health_percent !== null && PowerService.battery.health_percent !== undefined ? (PowerService.battery.health_percent + "%") : "Unknown")
                    + " · Rate: " + (PowerService.battery.energy_rate_w !== null && PowerService.battery.energy_rate_w !== undefined ? (PowerService.battery.energy_rate_w + " W") : "0 W")
                    + (PowerService.battery.ac_online !== null && PowerService.battery.ac_online !== undefined ? (" · AC: " + (PowerService.battery.ac_online ? "Online" : "Battery")) : "")
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }

            Text {
                visible: !!(PowerService.battery.time_to_empty || PowerService.battery.time_to_full)
                width: parent.width
                text: PowerService.battery.time_to_empty
                    ? ("Time to empty: " + PowerService.battery.time_to_empty)
                    : ("Time to full: " + (PowerService.battery.time_to_full || ""))
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }

            Text {
                visible: PowerService.battery.charge_cycles !== null && PowerService.battery.charge_cycles !== undefined
                width: parent.width
                text: "Charge cycles: " + String(PowerService.battery.charge_cycles || "")
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }

            Text {
                visible: PowerService.battery.charge_end_threshold !== null && PowerService.battery.charge_end_threshold !== undefined
                width: parent.width
                text: "Charge threshold: " + String(PowerService.battery.charge_end_threshold || "") + "%"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }
        }

        // Performance Card (EPP + Turbo)
        SectionCard {
            visible: PowerService.available && !!PowerService.cpu.available
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding

            Text {
                width: parent.width
                text: "Performance (" + String(PowerService.cpu.driver || "cpu") + ", " + String(PowerService.cpu.cpu_count || 0) + " threads)"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.DemiBold
                color: Deck.fg
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                text: "Session only, resets on reboot, asks for your password."
                font.family: Deck.fontFamily
                font.pixelSize: 11
                color: Deck.muted
                wrapMode: Text.WordWrap
            }

            ChipFlow {
                visible: !!PowerService.capabilities.can_write_epp
                width: parent.width
                layoutClass: viewport.layoutClass
                layoutShort: viewport.layoutShort
                spacing: 6

                Repeater {
                    model: PowerService.cpu.epp_available || []
                    delegate: ActionButton {
                        required property string modelData
                        text: pwrLogic.eppLabel(modelData)
                        variant: PowerService.cpu.epp_current === modelData ? "accent" : "neutral"
                        compact: true
                        enabled: !PowerService.busy
                        onClicked: PowerService.setEpp(modelData)
                    }
                }
            }

            Item {
                id: turboRowBox
                visible: !!PowerService.capabilities.can_write_turbo
                width: parent.width
                readonly property bool wrapped: ResponsiveLogic.shouldWrapHeaderActions(
                    turboRowBox.width, turboLblMetrics.advanceWidth, turboBtn.implicitWidth, Deck.space12
                )
                implicitHeight: wrapped
                    ? (turboLbl.implicitHeight + Deck.space8 + turboBtn.height)
                    : Math.max(turboLbl.implicitHeight, turboBtn.height)
                height: implicitHeight

                TextMetrics {
                    id: turboLblMetrics
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    text: turboLbl.text
                }

                Text {
                    id: turboLbl
                    x: 0
                    y: turboRowBox.wrapped ? 0 : Math.max(0, Math.round((turboRowBox.height - height) / 2))
                    width: turboRowBox.wrapped
                        ? turboRowBox.width
                        : Math.max(0, turboRowBox.width - turboBtn.width - Deck.space12)
                    text: "Intel Turbo Boost: " + (PowerService.cpu.turbo_enabled ? "Enabled" : "Disabled")
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.fg
                    wrapMode: Text.WordWrap
                }

                ActionButton {
                    id: turboBtn
                    x: turboRowBox.wrapped ? 0 : Math.max(0, turboRowBox.width - width)
                    y: turboRowBox.wrapped
                        ? (turboLbl.implicitHeight + Deck.space8)
                        : Math.max(0, Math.round((turboRowBox.height - height) / 2))
                    text: PowerService.cpu.turbo_enabled ? "Disable Turbo" : "Enable Turbo"
                    variant: PowerService.cpu.turbo_enabled ? "neutral" : "accent"
                    compact: true
                    enabled: !PowerService.busy
                    onClicked: PowerService.requestTurbo(!PowerService.cpu.turbo_enabled)
                }
            }
        }

        // Screen Idle Card (hypridle)
        SectionCard {
            visible: PowerService.available && !!PowerService.capabilities.hypridle_present
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding

            Item {
                id: idleHdrBox
                width: parent.width
                readonly property bool wrapped: ResponsiveLogic.shouldWrapHeaderActions(
                    idleHdrBox.width, idleLblMetrics.advanceWidth, idleActions.implicitWidth, Deck.space8
                )
                implicitHeight: wrapped
                    ? (idleLbl.implicitHeight + Deck.space8 + idleActions.height)
                    : Math.max(idleLbl.implicitHeight, idleActions.height)
                height: implicitHeight

                TextMetrics {
                    id: idleLblMetrics
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSize
                    font.weight: Font.DemiBold
                    text: idleLbl.text
                }

                Text {
                    id: idleLbl
                    x: 0
                    y: idleHdrBox.wrapped ? 0 : Math.max(0, Math.round((idleHdrBox.height - height) / 2))
                    width: idleHdrBox.wrapped
                        ? idleHdrBox.width
                        : Math.max(0, idleHdrBox.width - idleActions.width - Deck.space8)
                    text: "Screen Idle (hypridle: " + (PowerService.hypridle.running ? "running" : "stopped") + ")"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSize
                    font.weight: Font.DemiBold
                    color: Deck.fg
                    wrapMode: Text.WordWrap
                }

                Row {
                    id: idleActions
                    x: idleHdrBox.wrapped ? 0 : Math.max(0, idleHdrBox.width - width)
                    y: idleHdrBox.wrapped
                        ? (idleLbl.implicitHeight + Deck.space8)
                        : Math.max(0, Math.round((idleHdrBox.height - height) / 2))
                    spacing: Deck.space8

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
            Item {
                id: dimRowBox
                width: parent.width
                implicitHeight: Math.max(dimLbl.implicitHeight, dimCtrls.height)
                height: implicitHeight

                Text {
                    id: dimLbl
                    objectName: "elideOk"
                    x: 0
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(80, dimRowBox.width - dimCtrls.width - Deck.space8)
                    text: "Dim screen"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.fg
                    elide: Text.ElideRight
                }

                Row {
                    id: dimCtrls
                    x: dimRowBox.width - width
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Deck.space8

                    ActionButton {
                        text: "-"
                        compact: true
                        implicitWidth: 30
                        enabled: root.draftDimMin > 1
                        onClicked: { root.draftDimMin--; root.draftsDirty = true; }
                    }

                    Rectangle {
                        width: 68
                        height: 28
                        radius: Deck.radiusSmall
                        color: Deck.bg
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.3)

                        Text {
                            anchors.centerIn: parent
                            text: root.draftDimMin + " min"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.fg
                        }
                    }

                    ActionButton {
                        text: "+"
                        compact: true
                        implicitWidth: 30
                        enabled: root.draftDimMin < 1440
                        onClicked: { root.draftDimMin++; root.draftsDirty = true; }
                    }
                }
            }

            // Lock stepper
            Item {
                id: lockRowBox
                width: parent.width
                implicitHeight: Math.max(lockLbl.implicitHeight, lockCtrls.height)
                height: implicitHeight

                Text {
                    id: lockLbl
                    objectName: "elideOk"
                    x: 0
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(80, lockRowBox.width - lockCtrls.width - Deck.space8)
                    text: "Lock session"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.fg
                    elide: Text.ElideRight
                }

                Row {
                    id: lockCtrls
                    x: lockRowBox.width - width
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Deck.space8

                    ActionButton {
                        text: "-"
                        compact: true
                        implicitWidth: 30
                        enabled: root.draftLockMin > 1
                        onClicked: { root.draftLockMin--; root.draftsDirty = true; }
                    }

                    Rectangle {
                        width: 68
                        height: 28
                        radius: Deck.radiusSmall
                        color: Deck.bg
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.3)

                        Text {
                            anchors.centerIn: parent
                            text: root.draftLockMin + " min"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.fg
                        }
                    }

                    ActionButton {
                        text: "+"
                        compact: true
                        implicitWidth: 30
                        enabled: root.draftLockMin < 1440
                        onClicked: { root.draftLockMin++; root.draftsDirty = true; }
                    }
                }
            }

            // DPMS off stepper
            Item {
                id: dpmsRowBox
                width: parent.width
                implicitHeight: Math.max(dpmsLbl.implicitHeight, dpmsCtrls.height)
                height: implicitHeight

                Text {
                    id: dpmsLbl
                    objectName: "elideOk"
                    x: 0
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(80, dpmsRowBox.width - dpmsCtrls.width - Deck.space8)
                    text: "Turn off display"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.fg
                    elide: Text.ElideRight
                }

                Row {
                    id: dpmsCtrls
                    x: dpmsRowBox.width - width
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Deck.space8

                    ActionButton {
                        text: "-"
                        compact: true
                        implicitWidth: 30
                        enabled: root.draftDpmsMin > 1
                        onClicked: { root.draftDpmsMin--; root.draftsDirty = true; }
                    }

                    Rectangle {
                        width: 68
                        height: 28
                        radius: Deck.radiusSmall
                        color: Deck.bg
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.3)

                        Text {
                            anchors.centerIn: parent
                            text: root.draftDpmsMin + " min"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.fg
                        }
                    }

                    ActionButton {
                        text: "+"
                        compact: true
                        implicitWidth: 30
                        enabled: root.draftDpmsMin < 1440
                        onClicked: { root.draftDpmsMin++; root.draftsDirty = true; }
                    }
                }
            }

            Text {
                visible: root.idleValidationErr.length > 0
                text: root.idleValidationErr
                font.family: Deck.fontFamily
                font.pixelSize: 11
                color: Deck.critical
                width: parent.width
                wrapMode: Text.WordWrap
            }
        }

        // Read-only Lid and Sleep Card
        SectionCard {
            visible: PowerService.available && !!PowerService.lidSleep.available
            width: viewport.innerWidth
            cardPadding: viewport.cardPadding
            spacing: 4

            Text {
                width: parent.width
                text: "Lid & Sleep (Read-Only)"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                font.weight: Font.DemiBold
                color: Deck.fg
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                text: "Sleep mode: " + String(PowerService.lidSleep.mem_sleep || "unknown")
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                text: "Lid switch: battery=" + String(PowerService.lidSleep.handle_lid_switch || "suspend")
                    + " · ac=" + String(PowerService.lidSleep.handle_lid_switch_external_power || "suspend")
                    + " · docked=" + String(PowerService.lidSleep.handle_lid_switch_docked || "ignore")
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WordWrap
            }
        }
    }

    // Confirm Modal (only for turning Turbo Boost OFF)
    Rectangle {
        anchors.fill: parent
        visible: PowerService.confirmOpen
        color: Deck.alpha(Deck.bg, 0.72)
        z: 35

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
                    text: PowerService.confirmTitle
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeMedium
                    font.weight: Font.Bold
                    color: Deck.fg
                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Text {
                    text: PowerService.confirmMessage
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
                        text: "Disable Turbo"
                        variant: "danger"
                        compact: true
                        onClicked: PowerService.confirmPending()
                    }

                    ActionButton {
                        text: "Cancel"
                        compact: true
                        onClicked: PowerService.cancelPending()
                    }
                }
            }
        }
    }
}
