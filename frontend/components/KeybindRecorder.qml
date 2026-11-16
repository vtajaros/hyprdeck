import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../theme"
import "../services"
import "keymap.js" as KeyMap

Popup {
    id: root

    modal: true
    focus: true
    dim: true
    closePolicy: Popup.NoAutoClose

    anchors.centerIn: Overlay.overlay ? Overlay.overlay : parent
    width: Math.min(620, (Overlay.overlay ? Overlay.overlay.width : 800) - 48)
    height: cardCol.implicitHeight + 48

    signal accepted(int modmask, string key, string display)
    signal cancelled()

    property string recorderState: "preparing" // "preparing" | "listening" | "captured"
    property bool manualMode: false

    property int currentModmask: 0
    property int capturedModmask: 0
    property string capturedKey: ""
    property string capturedDisplay: ""

    property int manualModmask: 64 // default SUPER
    property string manualKeyText: ""

    property int watchdogSeconds: 15
    property bool unrecognisedKey: false
    property int lastRawKey: 0
    property int lastScanCode: 0

    background: Rectangle {
        color: Deck.bg
        radius: Deck.radiusMedium
        border.width: 1
        border.color: root.recorderState === "listening" ? Deck.alpha(Deck.accent, 0.6) : Deck.border

        Behavior on border.color {
            ColorAnimation { duration: 150 }
        }
    }

    Timer {
        id: watchdogTimer
        interval: 1000
        repeat: true
        running: root.opened && (root.recorderState === "listening" || root.recorderState === "preparing")
        onTriggered: {
            if (root.watchdogSeconds > 1) {
                root.watchdogSeconds -= 1;
            } else {
                root.watchdogSeconds = 0;
                root.leaveAndClose(true);
            }
        }
    }

    function openRecorder() {
        root.recorderState = "preparing";
        root.manualMode = false;
        root.unrecognisedKey = false;
        root.currentModmask = 0;
        root.capturedModmask = 0;
        root.capturedKey = "";
        root.capturedDisplay = "";
        root.manualKeyText = "";
        root.watchdogSeconds = 15;

        root.open();
        keyGrabber.forceActiveFocus();

        RecorderService.enter(function(res) {
            if (!root.opened) return;
            root.recorderState = "listening";
            root.watchdogSeconds = 15;
            keyGrabber.forceActiveFocus();
        });
    }

    function restartListening() {
        root.recorderState = "listening";
        root.unrecognisedKey = false;
        root.currentModmask = 0;
        root.capturedKey = "";
        root.capturedDisplay = "";
        root.watchdogSeconds = 15;
        keyGrabber.forceActiveFocus();
    }

    function leaveAndClose(isCancelled) {
        watchdogTimer.stop();
        RecorderService.leave(function(data) {
            RecorderService.status(function(sData) {
                if (sData && sData.submap && sData.submap !== "default") {
                    RecorderService.leave(function(retryData) {
                        RecorderService.status(function(finalData) {
                            if (finalData && finalData.submap && finalData.submap !== "default") {
                                EditService.showToast("Submap reset warning: still in '" + finalData.submap + "'. Run: hyprctl dispatch 'hl.dsp.submap(\"reset\")'", false);
                            }
                        });
                    });
                }
            });
        });
        root.close();
        if (isCancelled) {
            root.cancelled();
        }
    }

    function commitManual() {
        var cleanKey = root.manualKeyText.trim();
        if (!cleanKey) return;
        var display = KeyMap.formatDisplay(root.manualModmask, cleanKey);
        root.leaveAndClose(false);
        root.accepted(root.manualModmask, cleanKey, display);
    }

    function commitCaptured() {
        if (!root.capturedKey) return;
        var display = root.capturedDisplay || KeyMap.formatDisplay(root.capturedModmask, root.capturedKey);
        root.leaveAndClose(false);
        root.accepted(root.capturedModmask, root.capturedKey, display);
    }

    Component.onDestruction: {
        if (root.opened) {
            root.leaveAndClose(true);
        }
    }

    function handleKeyEvent(event) {
        root.watchdogSeconds = 15;

        // Plain Escape (no modifiers) cancels recorder
        if (event.key === Qt.Key_Escape && KeyMap.extractModmask(event.modifiers) === 0) {
            root.leaveAndClose(true);
            if (event.accepted !== undefined) event.accepted = true;
            return;
        }

        if (root.manualMode) {
            return;
        }

        if (root.recorderState === "captured") {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                root.commitCaptured();
                if (event.accepted !== undefined) event.accepted = true;
                return;
            }
            return;
        }

        var res = KeyMap.translateKeyEvent(event);

        if (res.isModifierOnly) {
            root.currentModmask = res.modmask;
            if (event.accepted !== undefined) event.accepted = true;
            return;
        }

        if (!res.recognized) {
            root.unrecognisedKey = true;
            root.lastRawKey = res.rawKey;
            root.lastScanCode = res.nativeScanCode;
            if (event.accepted !== undefined) event.accepted = true;
            return;
        }

        // Successfully captured a non-modifier key
        root.unrecognisedKey = false;
        root.capturedModmask = res.modmask;
        root.capturedKey = res.key;
        root.capturedDisplay = res.display;
        root.recorderState = "captured";
        if (event.accepted !== undefined) event.accepted = true;
    }

    Item {
        id: keyGrabber
        objectName: "keyGrabber"
        anchors.fill: parent
        focus: true

        Keys.onPressed: (event) => {
            root.handleKeyEvent(event);
        }

        Keys.onReleased: (event) => {
            if (root.recorderState === "listening") {
                root.currentModmask = KeyMap.extractModmask(event.modifiers);
            }
        }
    }

    Column {
        id: cardCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 24
        spacing: 16

        // 1. Header Row
        Row {
            width: parent.width
            spacing: 12

            Rectangle {
                width: 32
                height: 32
                radius: 6
                color: Deck.alpha(Deck.accent, 0.15)
                anchors.verticalCenter: parent.verticalCenter

                Text {
                    anchors.centerIn: parent
                    text: ""
                    font.family: Deck.fontFamily
                    font.pixelSize: 16
                    color: Deck.accent
                }
            }

            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2

                Text {
                    text: root.manualMode ? "Enter Keybinding Manually" : "Record Keybinding"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeMedium
                    font.weight: Font.Bold
                    color: Deck.fg
                }

                Text {
                    text: root.manualMode
                        ? "Select modifiers and type the key name"
                        : (root.recorderState === "captured" ? "Keybinding captured. Press Accept to apply." : "Press the desired key combination...")
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.muted
                }
            }

            Item { Layout.fillWidth: true; width: 1 }

            // Watchdog countdown chip
            Rectangle {
                visible: !root.manualMode && (root.recorderState === "listening" || root.recorderState === "preparing")
                width: timerLabel.implicitWidth + 14
                height: 22
                radius: 11
                color: Deck.alpha(Deck.muted, 0.15)
                anchors.verticalCenter: parent.verticalCenter

                Text {
                    id: timerLabel
                    anchors.centerIn: parent
                    text: root.watchdogSeconds + "s"
                    font.family: Deck.fontFamily
                    font.pixelSize: 11
                    color: Deck.muted
                }
            }
        }

        // 2. Limited Mode Banner (if compositor passthrough submap unavailable)
        Rectangle {
            visible: RecorderService.limited
            width: parent.width
            height: limitedRow.implicitHeight + 14
            radius: 6
            color: Deck.alpha(Deck.amber, 0.12)
            border.width: 1
            border.color: Deck.alpha(Deck.amber, 0.35)

            Row {
                id: limitedRow
                anchors.fill: parent
                anchors.margins: 7
                spacing: 8

                Text {
                    text: ""
                    font.family: Deck.fontFamily
                    font.pixelSize: 13
                    color: Deck.amber
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    text: "Limited mode: some global compositor shortcuts may be intercepted by Hyprland."
                    font.family: Deck.fontFamily
                    font.pixelSize: 11
                    color: Deck.fg
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        // 3. Central Recording Stage / Display Card
        Rectangle {
            width: parent.width
            height: 120
            radius: Deck.radius
            color: Deck.surface
            border.width: 1
            border.color: root.recorderState === "listening" ? Deck.alpha(Deck.accent, 0.4) : Deck.border

            // Unrecognised Key Notice
            Column {
                anchors.centerIn: parent
                visible: !root.manualMode && root.unrecognisedKey
                spacing: 6

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Unrecognized Key"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeMedium
                    font.weight: Font.Bold
                    color: Deck.amber
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Qt Key: " + root.lastRawKey + " | ScanCode: " + root.lastScanCode
                    font.family: Deck.fontFamily
                    font.pixelSize: 11
                    color: Deck.muted
                }
            }

            // Mode A: Interactive Capture Display
            Column {
                anchors.centerIn: parent
                visible: !root.manualMode && !root.unrecognisedKey
                spacing: 12

                // State indicator & Keycaps
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8

                    // When preparing
                    Row {
                        visible: root.recorderState === "preparing"
                        spacing: 8
                        Text {
                            text: "Preparing submap..."
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeMedium
                            color: Deck.muted
                        }
                    }

                    // When listening and no modifiers held yet
                    Row {
                        visible: root.recorderState === "listening" && root.currentModmask === 0
                        spacing: 8
                        Text {
                            text: "Listening for keys..."
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeMedium
                            color: Deck.muted
                        }
                    }

                    // When listening with live modifiers held
                    Row {
                        visible: root.recorderState === "listening" && root.currentModmask !== 0
                        spacing: 6

                        Repeater {
                            model: KeyMap.modmaskToParts(root.currentModmask)
                            delegate: Keycap {
                                text: modelData
                                active: true
                            }
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "+"
                            font.family: Deck.fontFamily
                            font.pixelSize: 14
                            color: Deck.muted
                        }

                        Rectangle {
                            width: 24
                            height: 24
                            radius: 4
                            color: Deck.alpha(Deck.muted, 0.15)
                            border.width: 1
                            border.color: Deck.alpha(Deck.accent, 0.5)

                            Text {
                                anchors.centerIn: parent
                                text: "?"
                                font.family: Deck.fontFamily
                                font.pixelSize: 13
                                color: Deck.accent
                            }
                        }
                    }

                    // When captured
                    Row {
                        visible: root.recorderState === "captured"
                        spacing: 6

                        Repeater {
                            model: KeyMap.modmaskToParts(root.capturedModmask)
                            delegate: Keycap {
                                text: modelData
                                active: true
                            }
                        }

                        Text {
                            visible: root.capturedModmask !== 0 && root.capturedKey !== ""
                            anchors.verticalCenter: parent.verticalCenter
                            text: "+"
                            font.family: Deck.fontFamily
                            font.pixelSize: 14
                            color: Deck.muted
                        }

                        Keycap {
                            visible: root.capturedKey !== ""
                            text: root.capturedKey
                            active: true
                        }
                    }
                }
            }

            // Mode B: Manual Entry
            Column {
                anchors.centerIn: parent
                visible: root.manualMode
                spacing: 12
                width: parent.width - 32

                // Modifier toggle chips
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8

                    Repeater {
                        model: [
                            { name: "SUPER", mask: 64 },
                            { name: "CTRL",  mask: 4 },
                            { name: "ALT",   mask: 8 },
                            { name: "SHIFT", mask: 1 }
                        ]
                        delegate: Rectangle {
                            id: modChip
                            readonly property bool isSelected: (root.manualModmask & modelData.mask) !== 0
                            width: chipText.implicitWidth + 18
                            height: 28
                            radius: 5
                            color: isSelected ? Deck.alpha(Deck.accent, 0.25) : Deck.surface
                            border.width: 1
                            border.color: isSelected ? Deck.accent : Deck.border

                            Text {
                                id: chipText
                                anchors.centerIn: parent
                                text: modelData.name
                                font.family: Deck.fontFamily
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                                color: modChip.isSelected ? Deck.accent : Deck.muted
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.manualModmask ^= modelData.mask;
                                }
                            }
                        }
                    }
                }

                // Key text input
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Key:"
                        font.family: Deck.fontFamily
                        font.pixelSize: 12
                        color: Deck.muted
                    }

                    Rectangle {
                        width: 180
                        height: 30
                        radius: 5
                        color: Deck.bg
                        border.width: 1
                        border.color: keyInput.activeFocus ? Deck.accent : Deck.border

                        TextInput {
                            id: keyInput
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            verticalAlignment: TextInput.AlignVCenter
                            font.family: Deck.fontFamily
                            font.pixelSize: 12
                            color: Deck.fg
                            text: root.manualKeyText
                            onTextChanged: {
                                root.manualKeyText = text;
                            }
                            onAccepted: {
                                root.commitManual();
                            }
                        }
                    }
                }
            }
        }

        // 4. Footnote & Mode Toggle
        Row {
            width: parent.width

            Text {
                text: "Bare Escape cancels. Combos with Escape (e.g. SUPER + Escape) are recordable."
                font.family: Deck.fontFamily
                font.pixelSize: 11
                color: Deck.muted
                anchors.verticalCenter: parent.verticalCenter
            }

            Item { Layout.fillWidth: true; width: 1 }

            Rectangle {
                width: toggleText.implicitWidth + 16
                height: 26
                radius: 4
                color: "transparent"
                border.width: 1
                border.color: Deck.alpha(Deck.muted, 0.3)
                anchors.verticalCenter: parent.verticalCenter

                Text {
                    id: toggleText
                    anchors.centerIn: parent
                    text: root.manualMode ? "Record keys" : "Type it instead"
                    font.family: Deck.fontFamily
                    font.pixelSize: 11
                    color: Deck.muted
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.manualMode = !root.manualMode;
                        if (!root.manualMode) {
                            root.restartListening();
                        }
                    }
                }
            }
        }

        // 5. Action Buttons Footer
        Row {
            anchors.right: parent.right
            spacing: 10

            // Re-record (visible when captured)
            Rectangle {
                visible: !root.manualMode && root.recorderState === "captured"
                width: rerecordText.implicitWidth + 20
                height: 32
                radius: 5
                color: Deck.surface
                border.width: 1
                border.color: Deck.border

                Text {
                    id: rerecordText
                    anchors.centerIn: parent
                    text: "Re-record"
                    font.family: Deck.fontFamily
                    font.pixelSize: 12
                    color: Deck.fg
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.restartListening();
                    }
                }
            }

            // Cancel
            Rectangle {
                width: cancelText.implicitWidth + 20
                height: 32
                radius: 5
                color: Deck.surface
                border.width: 1
                border.color: Deck.border

                Text {
                    id: cancelText
                    anchors.centerIn: parent
                    text: "Cancel"
                    font.family: Deck.fontFamily
                    font.pixelSize: 12
                    color: Deck.fg
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.leaveAndClose(true);
                    }
                }
            }

            // Accept (Primary)
            Rectangle {
                readonly property bool canAccept: root.manualMode
                    ? root.manualKeyText.trim().length > 0
                    : root.recorderState === "captured"
                width: acceptText.implicitWidth + 24
                height: 32
                radius: 5
                color: canAccept ? Deck.accent : Deck.alpha(Deck.muted, 0.2)

                Text {
                    id: acceptText
                    anchors.centerIn: parent
                    text: "Accept"
                    font.family: Deck.fontFamily
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    color: parent.canAccept ? "#ffffff" : Deck.muted
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: parent.canAccept
                    cursorShape: parent.canAccept ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (root.manualMode) {
                            root.commitManual();
                        } else {
                            root.commitCaptured();
                        }
                    }
                }
            }
        }
    }
}
