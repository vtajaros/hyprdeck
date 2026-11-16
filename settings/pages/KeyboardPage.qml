import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    KeyboardControlLogic {
        id: kbLogic
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
                    text: "Keyboard shortcuts"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: "Inspect, search, record, and edit Hyprland keybindings in Keybind Studio."
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
                    text: "Refresh"
                    compact: true
                    enabled: !KeyboardService.loading && !KeyboardService.busy
                    onClicked: KeyboardService.reload()
                }
            }
        }

        // Error banner (only when script is available and an action failed; missing script uses EmptyState)
        Rectangle {
            visible: !KeyboardService.loading && KeyboardService.available && KeyboardService.error.length > 0
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
                text: KeyboardService.error
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Status banner
        Rectangle {
            visible: KeyboardService.statusMessage.length > 0 && KeyboardService.error.length === 0
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
                text: KeyboardService.statusMessage
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.accent
                wrapMode: Text.WordWrap
            }
        }

        EmptyState {
            visible: !KeyboardService.loading && !KeyboardService.available
            width: parent.width
            height: 220
            icon: "󰌌"
            title: "Keybind Studio unavailable"
            message: KeyboardService.error || ("Launcher script not found or not executable: " + (KeyboardService.scriptPath || "scripts/hks-window"))
        }

        // Launcher card
        SectionCard {
            visible: KeyboardService.loading || KeyboardService.available
            width: parent.width
            cardPadding: HKS.space16
            spacing: HKS.space12

            Row {
                width: parent.width
                spacing: HKS.space12

                Column {
                    width: Math.max(200, parent.width - badgeRect.width - HKS.space12)
                    spacing: 4

                    Text {
                        text: "Hyprland Keybind Studio"
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSize
                        font.weight: Font.DemiBold
                        color: HKS.fg
                    }

                    Text {
                        width: parent.width
                        text: "Keybind Studio runs in its own isolated window to manage your Hyprland binds, chord recording, submaps, and conflict diagnostics."
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        color: HKS.muted
                        wrapMode: Text.WordWrap
                    }
                }

                Rectangle {
                    id: badgeRect
                    anchors.top: parent.top
                    width: badgeText.implicitWidth + 16
                    height: badgeText.implicitHeight + 8
                    radius: HKS.radiusSmall
                    color: KeyboardService.hksWindowOpen === true
                        ? HKS.alpha(HKS.accent, 0.18)
                        : HKS.alpha(HKS.muted, 0.14)
                    border.width: 1
                    border.color: KeyboardService.hksWindowOpen === true
                        ? HKS.alpha(HKS.accent, 0.45)
                        : HKS.alpha(HKS.muted, 0.28)

                    Text {
                        id: badgeText
                        anchors.centerIn: parent
                        text: KeyboardService.loading
                            ? "Checking..."
                            : kbLogic.windowStateBadge(KeyboardService.hksRunning, KeyboardService.hksWindowOpen)
                        font.family: HKS.fontFamily
                        font.pixelSize: HKS.fontSizeSmall
                        font.weight: Font.DemiBold
                        color: KeyboardService.hksWindowOpen === true ? HKS.accent : HKS.fg
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: HKS.alpha(HKS.muted, 0.14)
            }

            Text {
                width: parent.width
                text: "Status: " + (KeyboardService.loading
                    ? "Checking Keybind Studio status..."
                    : kbLogic.statusText(KeyboardService.available, KeyboardService.hksRunning, KeyboardService.hksWindowOpen))
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.fg
                wrapMode: Text.WordWrap
            }

            Text {
                visible: KeyboardService.scriptPath.length > 0
                width: parent.width
                text: "Launcher: " + KeyboardService.scriptPath
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.muted
                elide: Text.ElideMiddle
            }

            Row {
                spacing: HKS.space12

                ActionButton {
                    text: kbLogic.buttonLabel(KeyboardService.busy, KeyboardService.hksWindowOpen)
                    variant: "accent"
                    enabled: KeyboardService.available && !KeyboardService.loading && !KeyboardService.busy
                    onClicked: KeyboardService.openHks()
                }
            }
        }
    }
}
