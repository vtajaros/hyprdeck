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

    PageViewport {
        id: viewport
        anchors.fill: parent

        header: PageHeader {
            title: "Keyboard shortcuts"
            subtitle: "Inspect, search, record, and edit Hyprland keybindings in Keybind Studio."

            ActionButton {
                text: "Refresh"
                compact: true
                enabled: !KeyboardService.loading && !KeyboardService.busy
                onClicked: KeyboardService.reload()
            }
        }

        // Error banner (only when script is available and an action failed; missing script uses EmptyState)
        Rectangle {
            visible: !KeyboardService.loading && KeyboardService.available && KeyboardService.error.length > 0
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
                text: KeyboardService.error
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.critical
                wrapMode: Text.WordWrap
            }
        }

        // Status banner
        Rectangle {
            visible: KeyboardService.statusMessage.length > 0 && KeyboardService.error.length === 0
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
                text: KeyboardService.statusMessage
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.accent
                wrapMode: Text.WordWrap
            }
        }

        EmptyState {
            visible: !KeyboardService.loading && !KeyboardService.available
            width: viewport.innerWidth
            height: 220
            icon: "󰌌"
            title: "Keybind Studio unavailable"
            message: KeyboardService.error || ("Launcher script not found or not executable: " + (KeyboardService.scriptPath || "scripts/hks-window"))
        }

        // Launcher card
        SectionCard {
            visible: KeyboardService.loading || KeyboardService.available
            width: viewport.innerWidth
            cardPadding: Deck.space16
            spacing: Deck.space12

            Item {
                id: cardHdrBox
                width: parent.width
                readonly property bool badgeWrapped: (180 + Deck.space12 + badgeRect.width) > cardHdrBox.width
                implicitHeight: badgeWrapped
                    ? (cardTitleCol.implicitHeight + Deck.space8 + badgeRect.height)
                    : Math.max(cardTitleCol.implicitHeight, badgeRect.height)
                height: implicitHeight

                Column {
                    id: cardTitleCol
                    x: 0
                    y: 0
                    width: cardHdrBox.badgeWrapped
                        ? cardHdrBox.width
                        : Math.max(0, cardHdrBox.width - badgeRect.width - Deck.space12)
                    spacing: 4

                    Text {
                        width: parent.width
                        text: "HyprDeck Keybind Studio"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSize
                        font.weight: Font.DemiBold
                        color: Deck.fg
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: "Keybind Studio runs in its own isolated window to manage your Hyprland binds, chord recording, submaps, and conflict diagnostics."
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                        wrapMode: Text.WordWrap
                    }
                }

                TextMetrics {
                    id: badgeMetrics
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    font.weight: Font.DemiBold
                    text: KeyboardService.loading
                        ? "Checking..."
                        : kbLogic.windowStateBadge(KeyboardService.hksRunning, KeyboardService.hksWindowOpen)
                }

                Rectangle {
                    id: badgeRect
                    x: cardHdrBox.badgeWrapped ? 0 : Math.max(0, cardHdrBox.width - width)
                    y: cardHdrBox.badgeWrapped ? (cardTitleCol.implicitHeight + Deck.space8) : 0
                    width: Math.min(Math.ceil(badgeMetrics.advanceWidth) + 16, Math.max(40, cardHdrBox.width))
                    height: badgeText.implicitHeight + 8
                    radius: Deck.radiusSmall
                    color: KeyboardService.hksWindowOpen === true
                        ? Deck.alpha(Deck.accent, 0.18)
                        : Deck.alpha(Deck.muted, 0.14)
                    border.width: 1
                    border.color: KeyboardService.hksWindowOpen === true
                        ? Deck.alpha(Deck.accent, 0.45)
                        : Deck.alpha(Deck.muted, 0.28)

                    Text {
                        id: badgeText
                        objectName: "elideOk"
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        verticalAlignment: Text.AlignVCenter
                        text: badgeMetrics.text
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.DemiBold
                        color: KeyboardService.hksWindowOpen === true ? Deck.accent : Deck.fg
                        elide: Text.ElideRight
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Deck.alpha(Deck.muted, 0.14)
            }

            Text {
                width: parent.width
                text: "Status: " + (KeyboardService.loading
                    ? "Checking Keybind Studio status..."
                    : kbLogic.statusText(KeyboardService.available, KeyboardService.hksRunning, KeyboardService.hksWindowOpen))
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.fg
                wrapMode: Text.WordWrap
            }

            Text {
                visible: KeyboardService.scriptPath.length > 0
                width: parent.width
                text: "Launcher: " + KeyboardService.scriptPath
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
                wrapMode: Text.WrapAnywhere
            }

            Flow {
                width: parent.width
                spacing: Deck.space12

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
