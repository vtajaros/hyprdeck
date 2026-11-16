import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    BackupsLogic {
        id: logic
    }

    ResponsiveLogic {
        id: respLogic
    }

    property string activeFilter: "All"
    property var selectedRecord: null
    property bool compactDetailOpen: false
    property bool confirmOpen: false
    property var pendingRestoreRecord: null

    readonly property var fileFilters: logic.extractFileFilters(BackupsService.backups)
    readonly property var filteredBackups: logic.groupAndSortBackups(BackupsService.backups, root.activeFilter)
    readonly property string mode: logic.layoutMode(viewport.innerWidth)

    function hasBlockingModal() {
        return root.confirmOpen || root.compactDetailOpen;
    }

    function handleEscape() {
        if (root.confirmOpen) {
            root.confirmOpen = false;
            root.pendingRestoreRecord = null;
            return true;
        }
        if (root.compactDetailOpen) {
            root.compactDetailOpen = false;
            return true;
        }
        return false;
    }

    function selectRecord(rec) {
        if (!rec) return;
        root.selectedRecord = rec;
        BackupsService.loadDiff(rec.id);
        if (root.mode === "compact") {
            root.compactDetailOpen = true;
        }
    }

    function requestRestore(rec) {
        if (!logic.canRestore(rec, BackupsService.busy)) return;
        root.pendingRestoreRecord = rec;
        root.confirmOpen = true;
    }

    function _syncSelection() {
        var list = root.filteredBackups;
        if (!list || list.length === 0) {
            root.selectedRecord = null;
            return;
        }
        if (root.selectedRecord) {
            for (var i = 0; i < list.length; i++) {
                if (list[i].id === root.selectedRecord.id) {
                    root.selectedRecord = list[i];
                    return;
                }
            }
        }
        root.selectedRecord = list[0];
        if (BackupsService.selectedId !== list[0].id) {
            BackupsService.loadDiff(list[0].id);
        }
    }

    Connections {
        target: BackupsService
        function onBackupsChanged() {
            root._syncSelection();
        }
    }

    onFilteredBackupsChanged: root._syncSelection()

    PageViewport {
        id: viewport
        anchors.fill: parent

        header: PageHeader {
            title: "Backups"
            subtitle: "Inspect diffs and safely restore configuration snapshots."

            ActionButton {
                text: BackupsService.loading ? "Refreshing..." : "Refresh"
                compact: true
                enabled: !BackupsService.busy
                onClicked: BackupsService.reload()
            }
        }

        // Error / Rollback banner
        Rectangle {
            visible: BackupsService.error.length > 0
            width: viewport.innerWidth
            height: errCol.implicitHeight + 16
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.critical, 0.14)
            border.width: 1
            border.color: Deck.alpha(Deck.critical, 0.5)

            Column {
                id: errCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: 10
                spacing: 4

                Text {
                    width: parent.width
                    text: BackupsService.lastRolledBack ? "Restore rolled back automatically" : "Backup operation failed"
                    color: Deck.critical
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    font.bold: true
                    wrapMode: Text.WordWrap
                }

                Text {
                    width: parent.width
                    text: BackupsService.error
                    color: Deck.fg
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    wrapMode: Text.WordWrap
                }
            }
        }

        // Success + one-click Undo banner
        Rectangle {
            visible: BackupsService.statusMessage.length > 0 && BackupsService.error.length === 0
            width: viewport.innerWidth
            height: okRow.implicitHeight + 16
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.accent, 0.14)
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.5)

            RowLayout {
                id: okRow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: 10
                spacing: Deck.space8

                Column {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        width: parent.width
                        text: BackupsService.statusMessage
                        color: Deck.fg
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.bold: true
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        visible: BackupsService.lastNote.length > 0
                        width: parent.width
                        text: BackupsService.lastNote
                        color: Deck.muted
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        visible: BackupsService.lastWarnings && BackupsService.lastWarnings.length > 0
                        width: parent.width
                        text: BackupsService.lastWarnings.join(" ")
                        color: Deck.warning
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        wrapMode: Text.WordWrap
                    }
                }

                ActionButton {
                    visible: BackupsService.lastSnapshotId.length > 0
                    text: BackupsService.restoring ? "Undoing..." : "Undo"
                    compact: true
                    variant: "accent"
                    enabled: !BackupsService.busy
                    onClicked: BackupsService.undoLastRestore()
                }
            }
        }

        // File filter chips
        ChipFlow {
            width: viewport.innerWidth
            layoutClass: viewport.layoutClass
            layoutShort: viewport.layoutShort
            spacing: Deck.space8

            Repeater {
                model: root.fileFilters
                delegate: ActionButton {
                    required property string modelData
                    text: modelData
                    compact: true
                    variant: root.activeFilter === modelData ? "accent" : "neutral"
                    onClicked: root.activeFilter = modelData
                }
            }
        }

        // Empty state
        Rectangle {
            visible: !BackupsService.loading && root.filteredBackups.length === 0
            width: viewport.innerWidth
            height: emptyTxt.implicitHeight + 32
            radius: Deck.radius
            color: Deck.surface
            border.width: Deck.border
            border.color: Deck.borderColor

            Text {
                id: emptyTxt
                anchors.centerIn: parent
                width: Math.max(120, parent.width - 32)
                horizontalAlignment: Text.AlignHCenter
                text: "No backups recorded yet."
                color: Deck.muted
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSize
                wrapMode: Text.WordWrap
            }
        }

        // Main responsive container (split >= 1200, stacked 700..1199, compact < 700)
        GridLayout {
            visible: root.filteredBackups.length > 0
            width: viewport.innerWidth
            columns: root.mode === "split" ? 2 : 1
            columnSpacing: Deck.space12
            rowSpacing: Deck.space12

            // Snapshots list card
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredWidth: root.mode === "split" ? Math.round(viewport.innerWidth * 0.44) : viewport.innerWidth
                Layout.preferredHeight: root.mode === "split" ? 480 : (root.mode === "stacked" ? 260 : 380)
                radius: Deck.radius
                color: Deck.surface
                border.width: Deck.border
                border.color: Deck.borderColor
                clip: true

                ListView {
                    id: backupListView
                    anchors.fill: parent
                    anchors.margins: Deck.space8
                    spacing: Deck.space8
                    clip: true
                    model: root.filteredBackups

                    delegate: Rectangle {
                        id: rowItem
                        required property var modelData
                        readonly property bool selected: root.selectedRecord && root.selectedRecord.id === modelData.id

                        width: backupListView.width
                        height: rowCol.implicitHeight + 16
                        radius: Deck.radiusSmall
                        color: rowItem.selected ? Deck.alpha(Deck.accent, 0.16) : Deck.elevated
                        border.width: 1
                        border.color: rowItem.selected ? Deck.accent : Deck.alpha(Deck.muted, 0.25)

                        MouseArea {
                            anchors.fill: parent
                            onClicked: root.selectRecord(rowItem.modelData)
                        }

                        Column {
                            id: rowCol
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: 10
                            spacing: 4

                            RowLayout {
                                width: parent.width
                                spacing: Deck.space8

                                Text {
                                    Layout.fillWidth: true
                                    text: rowItem.modelData.file_name || rowItem.modelData.id
                                    color: Deck.fg
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSize
                                    font.bold: true
                                    elide: Text.ElideRight
                                }

                                Rectangle {
                                    visible: !!rowItem.modelData.is_current
                                    width: curBadge.implicitWidth + 10
                                    height: curBadge.implicitHeight + 4
                                    radius: Deck.radiusSmall
                                    color: Deck.alpha(Deck.accent, 0.22)

                                    Text {
                                        id: curBadge
                                        anchors.centerIn: parent
                                        text: "Current"
                                        color: Deck.accent
                                        font.family: Deck.fontFamily
                                        font.pixelSize: Deck.fontSizeSmall
                                    }
                                }

                                Rectangle {
                                    width: rsnBadge.implicitWidth + 10
                                    height: rsnBadge.implicitHeight + 4
                                    radius: Deck.radiusSmall
                                    color: Deck.alpha(Deck.muted, 0.18)

                                    Text {
                                        id: rsnBadge
                                        anchors.centerIn: parent
                                        text: logic.reasonLabel(rowItem.modelData.reason)
                                        color: Deck.muted
                                        font.family: Deck.fontFamily
                                        font.pixelSize: Deck.fontSizeSmall
                                    }
                                }
                            }

                            RowLayout {
                                width: parent.width
                                spacing: Deck.space8

                                Text {
                                    Layout.fillWidth: true
                                    text: rowItem.modelData.created_at + " · " + logic.formatBytes(rowItem.modelData.size)
                                    color: Deck.muted
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    elide: Text.ElideRight
                                }

                                Text {
                                    visible: !rowItem.modelData.available
                                    text: "Missing"
                                    color: Deck.critical
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                }
                            }
                        }
                    }
                }
            }

            // Detail + Diff panel (inline for split and stacked)
            Rectangle {
                visible: root.mode !== "compact"
                Layout.fillWidth: true
                Layout.preferredWidth: root.mode === "split" ? Math.round(viewport.innerWidth * 0.54) : viewport.innerWidth
                Layout.preferredHeight: 480
                radius: Deck.radius
                color: Deck.surface
                border.width: Deck.border
                border.color: Deck.borderColor
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Deck.space12
                    spacing: Deck.space8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Deck.space8

                        Column {
                            Layout.fillWidth: true
                            spacing: 2

                            Text {
                                width: parent.width
                                text: root.selectedRecord ? root.selectedRecord.file_name : "Select a snapshot"
                                color: Deck.fg
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeMedium
                                font.bold: true
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                text: root.selectedRecord ? root.selectedRecord.original_path : ""
                                color: Deck.muted
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                elide: Text.ElideMiddle
                            }
                        }

                        ActionButton {
                            text: BackupsService.restoring ? "Restoring..." : "Restore"
                            compact: true
                            variant: "accent"
                            enabled: logic.canRestore(root.selectedRecord, BackupsService.busy)
                            onClicked: root.requestRestore(root.selectedRecord)
                        }
                    }

                    Text {
                        visible: BackupsService.diffLoading
                        text: "Loading diff..."
                        color: Deck.muted
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                    }

                    Text {
                        visible: !BackupsService.diffLoading && BackupsService.activeDiff && BackupsService.activeDiff.identical
                        text: "Snapshot is identical to the current file on disk."
                        color: Deck.accent
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Text {
                        visible: !BackupsService.diffLoading && BackupsService.activeDiff && BackupsService.activeDiff.note && BackupsService.activeDiff.note.length > 0
                        text: BackupsService.activeDiff ? BackupsService.activeDiff.note : ""
                        color: Deck.warning
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Deck.radiusSmall
                        color: Deck.bg
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.2)
                        clip: true

                        Flickable {
                            id: diffFlick
                            anchors.fill: parent
                            anchors.margins: 8
                            contentWidth: Math.max(width, diffCol.implicitWidth)
                            contentHeight: diffCol.implicitHeight
                            clip: true

                            Column {
                                id: diffCol
                                spacing: 2

                                Repeater {
                                    model: (BackupsService.activeDiff && BackupsService.activeDiff.diff)
                                        ? String(BackupsService.activeDiff.diff).split("\n")
                                        : []
                                    delegate: Text {
                                        required property string modelData
                                        readonly property string kind: logic.classifyDiffLine(modelData)
                                        text: modelData
                                        font.family: Deck.fontFamily
                                        font.pixelSize: Deck.fontSizeSmall
                                        color: kind === "add" ? Deck.accent
                                            : (kind === "remove" ? Deck.critical
                                            : (kind === "hunk" ? Deck.warning
                                            : (kind === "meta" ? Deck.muted : Deck.fg)))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Compact detail/diff modal (< 700px)
    Rectangle {
        visible: root.compactDetailOpen && root.selectedRecord !== null
        anchors.fill: parent
        color: Deck.alpha(Deck.bg, 0.72)
        z: 30

        MouseArea {
            anchors.fill: parent
            onClicked: root.compactDetailOpen = false
        }

        Rectangle {
            readonly property var modalDims: respLogic.clampDialogSize(520, 420, root.width, root.height)
            width: modalDims.width
            height: modalDims.height
            anchors.centerIn: parent
            radius: Deck.radius
            color: Deck.surface
            border.width: Deck.border
            border.color: Deck.borderColor
            clip: true

            MouseArea {
                anchors.fill: parent
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Deck.space12
                spacing: Deck.space8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Deck.space8

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedRecord ? root.selectedRecord.file_name : ""
                        color: Deck.fg
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeMedium
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    ActionButton {
                        text: "Restore"
                        compact: true
                        variant: "accent"
                        enabled: logic.canRestore(root.selectedRecord, BackupsService.busy)
                        onClicked: {
                            root.compactDetailOpen = false;
                            root.requestRestore(root.selectedRecord);
                        }
                    }

                    ActionButton {
                        text: "Close"
                        compact: true
                        onClicked: root.compactDetailOpen = false
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: Deck.radiusSmall
                    color: Deck.bg
                    clip: true

                    Flickable {
                        anchors.fill: parent
                        anchors.margins: 8
                        contentWidth: Math.max(width, compactDiffCol.implicitWidth)
                        contentHeight: compactDiffCol.implicitHeight
                        clip: true

                        Column {
                            id: compactDiffCol
                            spacing: 2

                            Repeater {
                                model: (BackupsService.activeDiff && BackupsService.activeDiff.diff)
                                    ? String(BackupsService.activeDiff.diff).split("\n")
                                    : []
                                delegate: Text {
                                    required property string modelData
                                    readonly property string kind: logic.classifyDiffLine(modelData)
                                    text: modelData
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    color: kind === "add" ? Deck.accent
                                        : (kind === "remove" ? Deck.critical
                                        : (kind === "hunk" ? Deck.warning
                                        : (kind === "meta" ? Deck.muted : Deck.fg)))
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Restore confirmation modal
    Rectangle {
        visible: root.confirmOpen && root.pendingRestoreRecord !== null
        anchors.fill: parent
        color: Deck.alpha(Deck.bg, 0.72)
        z: 40

        MouseArea {
            anchors.fill: parent
            onClicked: {
                root.confirmOpen = false;
                root.pendingRestoreRecord = null;
            }
        }

        Rectangle {
            readonly property var modalDims: respLogic.clampDialogSize(420, 210, root.width, root.height)
            width: modalDims.width
            height: modalDims.height
            anchors.centerIn: parent
            radius: Deck.radius
            color: Deck.surface
            border.width: Deck.border
            border.color: Deck.borderColor

            MouseArea {
                anchors.fill: parent
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Deck.space16
                spacing: Deck.space12

                Text {
                    Layout.fillWidth: true
                    text: "Restore configuration snapshot?"
                    color: Deck.fg
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeMedium
                    font.bold: true
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: root.pendingRestoreRecord
                        ? ("Target: " + root.pendingRestoreRecord.original_path + "\nSnapshot: " + root.pendingRestoreRecord.id + "\nA pre-restore snapshot will be saved automatically.")
                        : ""
                    color: Deck.muted
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    wrapMode: Text.WordWrap
                }

                Item {
                    Layout.fillHeight: true
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Deck.space8

                    Item {
                        Layout.fillWidth: true
                    }

                    ActionButton {
                        text: "Cancel"
                        compact: true
                        onClicked: {
                            root.confirmOpen = false;
                            root.pendingRestoreRecord = null;
                        }
                    }

                    ActionButton {
                        text: "Restore"
                        compact: true
                        variant: "accent"
                        enabled: !BackupsService.busy
                        onClicked: {
                            var rec = root.pendingRestoreRecord;
                            root.confirmOpen = false;
                            root.pendingRestoreRecord = null;
                            if (rec) {
                                BackupsService.restoreBackup(rec.id);
                            }
                        }
                    }
                }
            }
        }
    }
}
