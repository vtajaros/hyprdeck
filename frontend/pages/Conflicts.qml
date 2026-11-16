import QtQuick
import QtQuick.Controls.Basic
import Quickshell
import "../theme"
import "../services"
import "../components"

Item {
    id: root

    signal requestShowInList(string query)
    signal requestClose()

    readonly property int totalConflicts: KeybindData.conflicts ? KeybindData.conflicts.length : 0
    readonly property int duplicateCount: {
        if (!KeybindData.conflicts) return 0;
        var cnt = 0;
        for (var i = 0; i < KeybindData.conflicts.length; i++) {
            if (KeybindData.conflicts[i] && KeybindData.conflicts[i].kind === "duplicate") cnt++;
        }
        return cnt;
    }
    readonly property int stackedCount: {
        if (!KeybindData.conflicts) return 0;
        var cnt = 0;
        for (var i = 0; i < KeybindData.conflicts.length; i++) {
            if (KeybindData.conflicts[i] && KeybindData.conflicts[i].kind !== "duplicate") cnt++;
        }
        return cnt;
    }

    // Order: duplicates (warning) first, then stacked (info), each group in scan order
    readonly property var sortedConflicts: {
        if (!KeybindData.conflicts) return [];
        var dups = [];
        var stks = [];
        for (var i = 0; i < KeybindData.conflicts.length; i++) {
            var c = KeybindData.conflicts[i];
            if (!c) continue;
            if (c.kind === "duplicate") {
                dups.push(c);
            } else {
                stks.push(c);
            }
        }
        return dups.concat(stks);
    }

    function formatSource(file, line) {
        if (!file) return "-";
        var path = String(file);
        var home = Quickshell.env("HOME") || "";
        if (home && path.startsWith(home)) {
            path = "~" + path.slice(home.length);
        }
        if (line !== undefined && line !== null) {
            path += ":" + line;
        }
        return path;
    }

    focus: true

    Keys.onPressed: function(event) {
        if (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_R) {
            KeybindData.reload();
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Escape) {
            root.requestClose();
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Down) {
            listView.contentY = Math.min(listView.contentHeight - listView.height, listView.contentY + 120);
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Up) {
            listView.contentY = Math.max(0, listView.contentY - 120);
            event.accepted = true;
            return;
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: Deck.space16
        spacing: Deck.space12

        // Header Summary Area
        Column {
            width: parent.width
            spacing: 4

            Row {
                width: parent.width
                spacing: 12

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Keybinding Conflicts"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeLarge
                    font.weight: Font.Bold
                    color: Deck.fg
                }

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.totalConflicts > 0
                    height: 22
                    width: summaryBadge.implicitWidth + 12
                    radius: 4
                    color: root.duplicateCount > 0 ? Deck.alpha(Deck.critical, 0.2) : Deck.alpha(Deck.warning, 0.2)
                    border.width: 1
                    border.color: root.duplicateCount > 0 ? Deck.alpha(Deck.critical, 0.6) : Deck.alpha(Deck.warning, 0.6)

                    Text {
                        id: summaryBadge
                        anchors.centerIn: parent
                        text: root.totalConflicts + " conflicts: " + root.duplicateCount + " duplicate, " + root.stackedCount + " stacked"
                        font.family: Deck.fontFamily
                        font.pixelSize: 10
                        font.weight: Font.Bold
                        color: root.duplicateCount > 0 ? Deck.critical : Deck.warning
                    }
                }
            }

            Text {
                text: "Stacked binds are legal: Hyprland runs every bind that matches a keypress."
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.muted
            }
        }

        // Main Content Area
        Item {
            width: parent.width
            height: parent.height - y

            // Loading state
            Item {
                anchors.fill: parent
                visible: KeybindData.loading

                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 32
                        color: Deck.accent
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Loading conflicts..."
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSize
                        color: Deck.muted
                    }
                }
            }

            // Error state
            EmptyState {
                anchors.fill: parent
                visible: !KeybindData.loading && KeybindData.error.length > 0
                icon: ""
                title: "Failed to scan configuration"
                message: KeybindData.error
                buttonText: "Retry Scan"
                onButtonClicked: KeybindData.reload()
            }

            // Empty state (no conflicts)
            EmptyState {
                anchors.fill: parent
                visible: !KeybindData.loading && !KeybindData.error && root.totalConflicts === 0
                icon: ""
                title: "No conflicts found"
                message: "Every keybinding in this configuration has a unique key combination."
            }

            // Conflict Cards List
            ListView {
                id: listView
                anchors.fill: parent
                anchors.topMargin: 4
                visible: !KeybindData.loading && !KeybindData.error && root.totalConflicts > 0
                model: root.sortedConflicts
                clip: true
                spacing: 12
                boundsBehavior: Flickable.StopAtBounds

                ScrollBar.vertical: ScrollBar {
                    active: true
                    width: 6
                }

                delegate: Rectangle {
                    id: conflictCard
                    readonly property var conflictItem: modelData
                    readonly property bool isDuplicate: conflictItem && conflictItem.kind === "duplicate"
                    readonly property int bindCount: conflictItem && conflictItem.bind_ids ? conflictItem.bind_ids.length : 0

                    width: listView.width - (listView.ScrollBar.vertical.visible ? 10 : 0)
                    implicitHeight: cardCol.implicitHeight + 24
                    radius: Deck.radius
                    color: Deck.surface
                    border.width: 1
                    border.color: isDuplicate ? Deck.alpha(Deck.critical, 0.45) : Deck.alpha(Deck.warning, 0.45)

                    Column {
                        id: cardCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 12
                        spacing: 10

                        // 1. Top row: Shortcut keycaps, Kind badge, N binds, and "Show in list" button
                        Item {
                            width: parent.width
                            height: 28

                            // Left: Keycaps + Kind badge + Submap + Binds count
                            Row {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 8

                                // Keycaps
                                ShortcutKeys {
                                    anchors.verticalCenter: parent.verticalCenter
                                    parts: KeybindData.conflictShortcutParts(conflictItem)
                                }

                                // Kind badge (Duplicate in critical, Stacked in warning)
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    height: 20
                                    width: kindTxt.implicitWidth + 10
                                    radius: 4
                                    color: isDuplicate ? Deck.alpha(Deck.critical, 0.2) : Deck.alpha(Deck.warning, 0.2)
                                    border.width: 1
                                    border.color: isDuplicate ? Deck.alpha(Deck.critical, 0.6) : Deck.alpha(Deck.warning, 0.6)

                                    Text {
                                        id: kindTxt
                                        anchors.centerIn: parent
                                        text: isDuplicate ? "Duplicate" : "Stacked"
                                        font.family: Deck.fontFamily
                                        font.pixelSize: 9
                                        font.weight: Font.Bold
                                        color: isDuplicate ? Deck.critical : Deck.warning
                                    }
                                }

                                // Submap badge if present
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: !!(conflictItem && conflictItem.submap)
                                    height: 20
                                    width: submapTxt.implicitWidth + 8
                                    radius: 4
                                    color: Deck.alpha(Deck.muted, 0.15)
                                    border.width: 1
                                    border.color: Deck.alpha(Deck.muted, 0.3)

                                    Text {
                                        id: submapTxt
                                        anchors.centerIn: parent
                                        text: conflictItem && conflictItem.submap ? ("submap: " + conflictItem.submap) : ""
                                        font.family: Deck.fontFamily
                                        font.pixelSize: 9
                                        color: Deck.muted
                                    }
                                }

                                // N binds count
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: conflictCard.bindCount + " binds"
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    color: Deck.muted
                                }
                            }

                            // Right: Button "Show in list"
                            ActionButton {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                variant: "neutral"
                                compact: true
                                iconText: ""
                                text: "Show in list"
                                onClicked: {
                                    var q = KeybindData.conflictSearchQuery(conflictItem);
                                    root.requestShowInList(q);
                                }
                            }
                        }

                        // 2. Plain sentence explaining behavior
                        Text {
                            text: isDuplicate
                                ? "These binds do the same thing; one of them is redundant."
                                : ("Pressing this triggers all " + conflictCard.bindCount + " actions.")
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.alpha(Deck.muted, 0.85)
                        }

                        // 3. One row per bind in config order (with fixed columns across cards)
                        Column {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: conflictItem && conflictItem.bind_ids ? conflictItem.bind_ids : []
                                delegate: Rectangle {
                                    id: bindRowRec
                                    readonly property string bindId: String(modelData)
                                    readonly property var bindObj: KeybindData.getBindById(bindId)

                                    width: parent.width
                                    height: 32
                                    radius: 4
                                    color: Deck.alpha(Deck.bg, 0.5)
                                    border.width: 1
                                    border.color: Deck.alpha(Deck.muted, 0.12)

                                    Item {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10

                                        // Column 1: Description (primary) - fixed width 250px
                                        Text {
                                            id: descText
                                            anchors.left: parent.left
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 250
                                            text: bindObj ? KeybindData.descriptionText(bindObj) : ("(Unknown bind: " + bindId + ")")
                                            font.family: Deck.fontFamily
                                            font.pixelSize: Deck.fontSizeSmall
                                            font.weight: Font.DemiBold
                                            color: bindObj ? Deck.fg : Deck.muted
                                            elide: Text.ElideRight
                                        }

                                        // Column 3: Right group (loop badge + source file:line)
                                        Row {
                                            id: rightGroup
                                            anchors.right: parent.right
                                            anchors.verticalCenter: parent.verticalCenter
                                            spacing: 8

                                            // Loop badge when generated is true
                                            Rectangle {
                                                anchors.verticalCenter: parent.verticalCenter
                                                visible: !!(bindObj && bindObj.generated)
                                                height: 18
                                                width: loopBadgeTxt.implicitWidth + 8
                                                radius: 3
                                                color: Deck.alpha(Deck.muted, 0.15)
                                                border.width: 1
                                                border.color: Deck.alpha(Deck.muted, 0.3)

                                                Text {
                                                    id: loopBadgeTxt
                                                    anchors.centerIn: parent
                                                    text: "loop"
                                                    font.family: Deck.fontFamily
                                                    font.pixelSize: 9
                                                    color: Deck.muted
                                                }
                                            }

                                            // Source file:line with "~" path replacement
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: 240
                                                horizontalAlignment: Text.AlignRight
                                                text: root.formatSource(bindObj ? bindObj.source_file : "", bindObj ? bindObj.source_line : null)
                                                font.family: Deck.fontFamily
                                                font.pixelSize: Deck.fontSizeSmall
                                                color: Deck.alpha(Deck.muted, 0.8)
                                                elide: Text.ElideLeft
                                            }
                                        }

                                        // Column 2: Action text (mono, muted) - fills between Col 1 and Col 3
                                        Text {
                                            anchors.left: descText.right
                                            anchors.leftMargin: 12
                                            anchors.right: rightGroup.left
                                            anchors.rightMargin: 12
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: bindObj ? KeybindData.actionText(bindObj) : "-"
                                            font.family: Deck.fontFamily
                                            font.pixelSize: Deck.fontSizeSmall
                                            color: Deck.muted
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
