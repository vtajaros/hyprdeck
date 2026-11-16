import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../theme"
import "../services"
import "keymap.js" as KeyMap

Item {
    id: root

    property string mode: EditService.dialogMode // "edit" | "add"
    readonly property bool isAddMode: mode === "add"

    property var bind: EditService.targetEditBind

    property var currentMods: []
    property string currentKey: ""
    property var newMods: []
    property string newKey: ""
    property string submap: ""

    property bool flagLocked: false
    property bool flagRepeating: false

    property bool preserveDispatcher: true
    property string selectedDispatcherId: ""
    property string selectedDispatcherLabel: ""
    property string selectedArgValue: ""
    property var selectedSchema: []
    property bool rawExpressionMode: false
    property string rawExpressionText: ""

    property string descriptionText: ""
    property string originalDescription: ""
    property string selectedCategory: "Apps"
    property string originalCategory: "Apps"
    property bool hasCustomOverride: false

    readonly property bool hasDescriptionChanged: descriptionText !== originalDescription
    readonly property bool hasCategoryChanged: selectedCategory !== originalCategory
    readonly property bool hasMetadataOnlyChanged: (hasDescriptionChanged || hasCategoryChanged) && !hasShortcutChanged && !hasDispatcherChanged

    // Number of other active binds sharing the exact same (mods, key, submap)
    readonly property int sharedShortcutCount: {
        if (!root.bind || !KeybindData.binds) return 0;
        var count = 0;
        var targetKey = (root.bind.key || "").toLowerCase();
        var targetMods = (root.bind.modifiers || []).slice().sort().join("+");
        var targetSubmap = root.bind.submap || "";
        for (var i = 0; i < KeybindData.binds.length; i++) {
            var b = KeybindData.binds[i];
            if (b && b.id !== root.bind.id) {
                var bKey = (b.key || "").toLowerCase();
                var bMods = (b.modifiers || []).slice().sort().join("+");
                var bSub = b.submap || "";
                if (bKey === targetKey && bMods === targetMods && bSub === targetSubmap) {
                    count++;
                }
            }
        }
        return count;
    }

    readonly property bool hasShortcutChanged: {
        if (!root.bind) return false;
        var oldModsStr = (root.currentMods || []).join("+");
        var newModsStr = (root.newMods || []).join("+");
        return (oldModsStr !== newModsStr) || (root.newKey !== root.currentKey);
    }

    readonly property bool hasDispatcherChanged: !root.preserveDispatcher

    readonly property bool canReview: {
        if (RecorderService.active || keybindRecorder.opened) return false;
        if (!root.newKey || !root.newKey.trim()) return false;
        if (root.descriptionText.length > 200) return false;
        if (root.isAddMode) {
            if (root.rawExpressionMode) {
                return !!(root.rawExpressionText && root.rawExpressionText.trim());
            }
            if (!root.selectedDispatcherId) return false;
            if (root.selectedSchema && root.selectedSchema.length > 0 && root.selectedSchema[0].required) {
                return !!(root.selectedArgValue && root.selectedArgValue.trim());
            }
            return true;
        } else {
            if (!root.bind) return false;
            return (root.hasShortcutChanged || root.hasDispatcherChanged || root.hasMetadataOnlyChanged);
        }
    }

    readonly property string validationHint: {
        if (root.descriptionText.length > 200) {
            return "Description must be 200 characters or less";
        }
        if (!root.newKey || !root.newKey.trim()) {
            return "Select or record a keyboard shortcut";
        }
        if (root.isAddMode) {
            if (root.rawExpressionMode && (!root.rawExpressionText || !root.rawExpressionText.trim())) {
                return "Enter a raw expression";
            }
            if (!root.selectedDispatcherId && !root.rawExpressionMode) {
                return "Choose an action / dispatcher";
            }
            if (root.selectedSchema && root.selectedSchema.length > 0 && root.selectedSchema[0].required && (!root.selectedArgValue || !root.selectedArgValue.trim())) {
                return "Enter required argument for " + root.selectedDispatcherLabel;
            }
        }
        return "";
    }

    onVisibleChanged: {
        if (visible) {
            if (root.isAddMode) {
                initAddMode();
            } else if (root.bind) {
                initFromBind(root.bind);
            }
        }
    }

    onBindChanged: {
        if (!root.isAddMode && root.bind) {
            initFromBind(root.bind);
        }
    }

    function initAddMode() {
        root.currentMods = [];
        root.currentKey = "";
        root.newMods = [];
        root.newKey = "";
        root.submap = "";
        root.flagLocked = false;
        root.flagRepeating = false;
        root.preserveDispatcher = false;
        root.rawExpressionMode = false;
        root.rawExpressionText = "";

        root.descriptionText = "";
        root.originalDescription = "";
        root.selectedCategory = (SidecarService.categories && SidecarService.categories.length > 0) ? SidecarService.categories[0] : "Apps";
        root.originalCategory = root.selectedCategory;
        root.hasCustomOverride = false;

        if (DispatcherCatalog.catalog && DispatcherCatalog.catalog.length > 0) {
            var item = DispatcherCatalog.catalog[0];
            root.selectedDispatcherId = item.id;
            root.selectedDispatcherLabel = item.label;
            root.selectedSchema = item.args_schema || [];
            if (item.args_schema && item.args_schema.length > 0 && item.args_schema[0].default !== undefined) {
                root.selectedArgValue = String(item.args_schema[0].default);
            } else {
                root.selectedArgValue = "";
            }
        } else {
            root.selectedDispatcherId = "exec_cmd";
            root.selectedDispatcherLabel = "Launch Application / Command";
            root.selectedSchema = [];
            root.selectedArgValue = "";
        }
        ConflictCheckService.reset();
    }

    function initFromBind(b) {
        root.currentMods = b.modifiers ? b.modifiers.slice() : [];
        root.currentKey = b.key || "";
        root.newMods = root.currentMods.slice();
        root.newKey = root.currentKey;
        root.submap = b.submap || "";
        root.flagLocked = !!(b.flags && b.flags.locked);
        root.flagRepeating = !!(b.flags && b.flags.repeating);

        var effDesc = (b.description_effective && b.description_effective.text) ? b.description_effective.text : (b.description || "");
        root.originalDescription = effDesc;
        root.descriptionText = effDesc;

        var effCat = b.category || "Apps";
        root.originalCategory = effCat;
        root.selectedCategory = effCat;

        root.hasCustomOverride = !!((b.description_effective && b.description_effective.source === "override") || (b.category_source === "override"));

        root.preserveDispatcher = true;
        root.rawExpressionMode = false;
        root.rawExpressionText = "";
        root.selectedArgValue = "";

        // Check if current dispatcher matches catalog
        var dspPath = (b.dispatcher && b.dispatcher.path) ? b.dispatcher.path : "";
        var catItem = DispatcherCatalog.getDispatcher(dspPath);
        if (catItem) {
            root.selectedDispatcherId = catItem.id;
            root.selectedDispatcherLabel = catItem.label;
            root.selectedSchema = catItem.args_schema || [];
            if (b.dispatcher && b.dispatcher.arg_summary) {
                root.selectedArgValue = b.dispatcher.arg_summary;
            } else if (b.args_raw) {
                root.selectedArgValue = b.args_raw;
            }
        } else {
            root.selectedDispatcherId = "custom";
            root.selectedDispatcherLabel = "Custom Expression";
            root.selectedSchema = [];
            root.rawExpressionText = b.original_line || dspPath;
        }

        // Run conflict pre-check
        ConflictCheckService.check(
            root.newMods.join(" + "),
            root.newKey,
            root.submap,
            b.id
        );
    }

    function modmaskToModifiers(mask) {
        var mods = [];
        if (mask & 64) mods.push("SUPER");
        if (mask & 4) mods.push("CTRL");
        if (mask & 8) mods.push("ALT");
        if (mask & 1) mods.push("SHIFT");
        if (mask & 16) mods.push("MOD2");
        if (mask & 32) mods.push("MOD3");
        if (mask & 128) mods.push("MOD5");
        return mods;
    }

    // Modal background overlay
    Rectangle {
        anchors.fill: parent
        color: "#b8090b0e"

        MouseArea {
            anchors.fill: parent
            onClicked: {
                if (!keybindRecorder.opened) {
                    EditService.closeEditDialog();
                }
            }
        }
    }

    // Center card
    Rectangle {
        id: card
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 640)
        height: Math.min(parent.height - 48, cardCol.implicitHeight + 40)
        radius: Deck.radius
        color: Deck.bg
        border.width: 1
        border.color: Deck.alpha(Deck.accent, 0.45)

        MouseArea {
            anchors.fill: parent
            // Prevent clicks inside card from closing modal
            onClicked: {}
        }

        Column {
            id: cardCol
            anchors.fill: parent
            anchors.margins: 20
            spacing: 14

            // Header Bar
            Item {
                width: parent.width
                height: 28

                Row {
                    spacing: 8
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.isAddMode ? "" : ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 16
                        color: Deck.accent
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.isAddMode ? "Add Keybinding" : "Edit Keybinding"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeLarge
                        font.weight: Font.Bold
                        color: Deck.fg
                    }

                    // Submap Tag (Read-only for edit mode)
                    Rectangle {
                        visible: !root.isAddMode && !!(root.submap && root.submap.length > 0)
                        anchors.verticalCenter: parent.verticalCenter
                        height: 20
                        width: submapTxt.implicitWidth + 10
                        radius: 4
                        color: Deck.alpha(Deck.warning, 0.15)
                        border.width: 1
                        border.color: Deck.alpha(Deck.warning, 0.4)

                        Text {
                            id: submapTxt
                            anchors.centerIn: parent
                            text: "Submap: " + root.submap
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            color: Deck.warning
                        }
                    }
                }

                // Close Button
                Rectangle {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24
                    height: 24
                    radius: 4
                    color: closeMa.containsMouse ? Deck.alpha(Deck.muted, 0.2) : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.family: Deck.fontFamily
                        font.pixelSize: 12
                        color: Deck.muted
                    }

                    MouseArea {
                        id: closeMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: EditService.closeEditDialog()
                    }
                }
            }

            // Submap selector (Add mode only, when submaps exist)
            Row {
                id: submapSection
                objectName: "submapSection"
                visible: root.isAddMode && KeybindData.submaps.length > 0
                width: parent.width
                spacing: 8

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Submap:"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    font.weight: Font.DemiBold
                    color: Deck.muted
                }

                ComboBox {
                    id: submapCombo
                    width: 200
                    height: 28
                    model: ["(Global / None)"].concat(KeybindData.submaps)
                    currentIndex: {
                        if (!root.submap) return 0;
                        var idx = KeybindData.submaps.indexOf(root.submap);
                        return idx !== -1 ? (idx + 1) : 0;
                    }
                    onActivated: (index) => {
                        root.submap = (index === 0) ? "" : KeybindData.submaps[index - 1];
                        ConflictCheckService.check(
                            root.newMods.join(" + "),
                            root.newKey,
                            root.submap,
                            root.bind ? root.bind.id : ""
                        );
                    }
                }
            }

            // Section 1: Shortcut Row
            Column {
                width: parent.width
                spacing: 6

                Text {
                    text: "Keyboard Shortcut"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    font.weight: Font.DemiBold
                    color: Deck.muted
                }

                Rectangle {
                    width: parent.width
                    height: 48
                    radius: 6
                    color: Deck.alpha(Deck.surface, 0.7)
                    border.width: 1
                    border.color: Deck.alpha(Deck.muted, 0.25)

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        ShortcutKeys {
                            id: liveShortcutKeys
                            anchors.verticalCenter: parent.verticalCenter
                            parts: root.newMods.concat(root.newKey ? [root.newKey] : [])
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !root.newKey
                            text: root.isAddMode ? "Click 'Record' or press a shortcut..." : "(No key selected)"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.muted
                            font.italic: true
                        }
                    }

                    Row {
                        anchors.right: parent.right
                        anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        // Manual Edit / Clear (Edit mode)
                        ActionButton {
                            variant: "neutral"
                            text: "Reset"
                            visible: !root.isAddMode && root.hasShortcutChanged
                            onClicked: {
                                root.newMods = root.currentMods.slice();
                                root.newKey = root.currentKey;
                                ConflictCheckService.check(
                                    root.newMods.join(" + "),
                                    root.newKey,
                                    root.submap,
                                    root.bind ? root.bind.id : ""
                                );
                            }
                        }

                        // Clear Button (Add mode)
                        ActionButton {
                            variant: "neutral"
                            text: "Clear"
                            visible: root.isAddMode && !!root.newKey
                            onClicked: {
                                root.newMods = [];
                                root.newKey = "";
                                ConflictCheckService.reset();
                            }
                        }

                        // Record Button
                        ActionButton {
                            variant: "accent"
                            iconText: ""
                            text: "Record"
                            onClicked: {
                                keybindRecorder.openRecorder();
                            }
                        }
                    }
                }
            }

            // Live Conflict Banner
            Rectangle {
                id: conflictBanner
                objectName: "conflictBanner"
                width: parent.width
                height: confBannerCol.implicitHeight + 12
                radius: 6
                color: Deck.alpha(Deck.warning, 0.12)
                border.width: 1
                border.color: Deck.alpha(Deck.warning, 0.45)
                visible: ConflictCheckService.hasConflicts || ConflictCheckService.disabledHeld

                Row {
                    id: confBannerCol
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    Text {
                        text: ""
                        font.family: Deck.fontFamily
                        font.pixelSize: 13
                        color: Deck.warning
                    }

                    Column {
                        width: parent.width - 24
                        spacing: 2

                        Text {
                            visible: ConflictCheckService.hasConflicts
                            text: "Conflict: This combo is already used by:"
                            font.family: Deck.fontFamily
                            font.pixelSize: 11
                            font.weight: Font.Bold
                            color: Deck.warning
                        }

                        Repeater {
                            model: ConflictCheckService.conflictsList
                            Text {
                                width: parent.width
                                text: "• " + modelData.shortcut + " — " + modelData.description + " (" + modelData.file + ":" + modelData.line + ")"
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: Deck.fg
                                elide: Text.ElideRight
                            }
                        }

                        Text {
                            visible: ConflictCheckService.disabledHeld
                            text: "Notice: Key is currently held by a disabled keybinding."
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            font.italic: true
                            color: Deck.warning
                        }
                    }
                }
            }

            // Section 2: Dispatcher & Action
            Column {
                width: parent.width
                spacing: 6

                Row {
                    width: parent.width
                    spacing: 8

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Action / Dispatcher"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.DemiBold
                        color: Deck.muted
                    }

                    // Mode switch (Guided vs Raw)
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !root.preserveDispatcher || root.isAddMode
                        height: 20
                        width: modeTxt.implicitWidth + 12
                        radius: 4
                        color: Deck.alpha(Deck.surface, 0.8)
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.3)

                        Text {
                            id: modeTxt
                            anchors.centerIn: parent
                            text: root.rawExpressionMode ? "Switch to Guided" : "Raw Expression"
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: Deck.muted
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.rawExpressionMode = !root.rawExpressionMode;
                            }
                        }
                    }
                }

                // If preserveDispatcher (edit mode only): Show "Keep current: <text>"
                Rectangle {
                    visible: !root.isAddMode && root.preserveDispatcher
                    width: parent.width
                    height: 44
                    radius: 6
                    color: Deck.alpha(Deck.surface, 0.6)
                    border.width: 1
                    border.color: Deck.alpha(Deck.muted, 0.2)

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.right: changeBtn.left
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        Text {
                            text: "Keep current action:"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.muted
                        }

                        Text {
                            text: (root.bind && root.bind.dispatcher)
                                ? (root.bind.dispatcher.path + (root.bind.dispatcher.arg_summary ? (" " + root.bind.dispatcher.arg_summary) : ""))
                                : (root.bind ? root.bind.original_line : "")
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            font.weight: Font.DemiBold
                            color: Deck.fg
                            elide: Text.ElideRight
                            width: Math.max(120, parent.width - 150)
                        }
                    }

                    ActionButton {
                        id: changeBtn
                        anchors.right: parent.right
                        anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        variant: "neutral"
                        text: "Change..."
                        onClicked: {
                            root.preserveDispatcher = false;
                        }
                    }
                }

                // If NOT preserveDispatcher (or Add mode): Show Dispatcher selection
                Column {
                    visible: root.isAddMode || !root.preserveDispatcher
                    width: parent.width
                    spacing: 8

                    // Guided mode: Dispatcher combo
                    Rectangle {
                        visible: !root.rawExpressionMode
                        width: parent.width
                        height: 36
                        radius: 6
                        color: Deck.alpha(Deck.surface, 0.8)
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.3)

                        ComboBox {
                            id: dispatcherCombo
                            anchors.fill: parent
                            model: DispatcherCatalog.catalog
                            textRole: "label"

                            currentIndex: {
                                for (var i = 0; i < DispatcherCatalog.catalog.length; i++) {
                                    if (DispatcherCatalog.catalog[i].id === root.selectedDispatcherId) {
                                        return i;
                                    }
                                }
                                return 0;
                            }

                            onActivated: (index) => {
                                var item = DispatcherCatalog.catalog[index];
                                if (item) {
                                    root.selectedDispatcherId = item.id;
                                    root.selectedDispatcherLabel = item.label;
                                    root.selectedSchema = item.args_schema || [];
                                    if (item.args_schema && item.args_schema.length > 0) {
                                        var field = item.args_schema[0];
                                        root.selectedArgValue = field.default !== undefined ? String(field.default) : "";
                                    } else {
                                        root.selectedArgValue = "";
                                    }
                                }
                            }
                        }
                    }

                    // Guided mode: Argument Schema Input
                    Rectangle {
                        visible: !root.rawExpressionMode && root.selectedSchema && root.selectedSchema.length > 0
                        width: parent.width
                        height: 36
                        radius: 6
                        color: Deck.alpha(Deck.surface, 0.8)
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.3)

                        TextField {
                            id: argField
                            anchors.fill: parent
                            anchors.margins: 4
                            placeholderText: (root.selectedSchema && root.selectedSchema.length > 0 && root.selectedSchema[0].placeholder)
                                ? root.selectedSchema[0].placeholder
                                : "Argument"
                            text: root.selectedArgValue
                            color: Deck.fg
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            background: Item {}
                            onTextChanged: {
                                root.selectedArgValue = text;
                            }
                        }
                    }

                    // Raw expression mode text input
                    Rectangle {
                        visible: root.rawExpressionMode
                        width: parent.width
                        height: 36
                        radius: 6
                        color: Deck.alpha(Deck.surface, 0.8)
                        border.width: 1
                        border.color: Deck.alpha(Deck.muted, 0.3)

                        TextField {
                            id: rawExprField
                            anchors.fill: parent
                            anchors.margins: 4
                            placeholderText: "Lua expression or Hyprlang args"
                            text: root.rawExpressionText
                            color: Deck.fg
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            background: Item {}
                            onTextChanged: {
                                root.rawExpressionText = text;
                            }
                        }
                    }

                    // Cancel change button (edit mode only)
                    Item {
                        visible: !root.isAddMode
                        width: parent.width
                        height: 22

                        Text {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            text: "↩ Revert to original action"
                            font.family: Deck.fontFamily
                            font.pixelSize: 10
                            color: Deck.accent

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.preserveDispatcher = true;
                                }
                            }
                        }
                    }
                }
            }

            // Section 3: Flags / Options (Locked, Repeating)
            Column {
                id: flagsSection
                objectName: "flagsSection"
                visible: root.isAddMode
                width: parent.width
                spacing: 6

                Text {
                    text: "Flags & Modifiers"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    font.weight: Font.DemiBold
                    color: Deck.muted
                }

                Row {
                    spacing: 24

                    // Locked Checkbox
                    Row {
                        spacing: 8
                        Rectangle {
                            width: 18
                            height: 18
                            radius: 4
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.flagLocked ? Deck.accent : "transparent"
                            border.width: 1
                            border.color: root.flagLocked ? Deck.accent : Deck.alpha(Deck.muted, 0.4)
                            Text {
                                anchors.centerIn: parent
                                text: "✓"
                                font.family: Deck.fontFamily
                                font.pixelSize: 12
                                font.bold: true
                                color: Deck.bg
                                visible: root.flagLocked
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.flagLocked = !root.flagLocked
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Locked (trigger while session locked)"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.fg
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.flagLocked = !root.flagLocked
                            }
                        }
                    }

                    // Repeating Checkbox
                    Row {
                        spacing: 8
                        Rectangle {
                            width: 18
                            height: 18
                            radius: 4
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.flagRepeating ? Deck.accent : "transparent"
                            border.width: 1
                            border.color: root.flagRepeating ? Deck.accent : Deck.alpha(Deck.muted, 0.4)
                            Text {
                                anchors.centerIn: parent
                                text: "✓"
                                font.family: Deck.fontFamily
                                font.pixelSize: 12
                                font.bold: true
                                color: Deck.bg
                                visible: root.flagRepeating
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.flagRepeating = !root.flagRepeating
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Repeat (repeat when key held)"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.fg
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.flagRepeating = !root.flagRepeating
                            }
                        }
                    }
                }
            }

            // Section 4: Description & Category
            Column {
                width: parent.width
                spacing: 6

                Item {
                    width: parent.width
                    height: 20

                    Row {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Description & Category"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            font.weight: Font.DemiBold
                            color: Deck.muted
                        }

                        // Indicator: (custom) vs (from config)
                        Rectangle {
                            visible: !root.isAddMode && !!root.bind
                            anchors.verticalCenter: parent.verticalCenter
                            height: 18
                            width: badgeText.implicitWidth + 8
                            radius: 3
                            color: root.hasCustomOverride ? Deck.alpha(Deck.accent, 0.15) : Deck.alpha(Deck.muted, 0.15)
                            border.width: 1
                            border.color: root.hasCustomOverride ? Deck.alpha(Deck.accent, 0.3) : Deck.alpha(Deck.muted, 0.3)

                            Text {
                                id: badgeText
                                anchors.centerIn: parent
                                text: root.hasCustomOverride ? "custom" : "from config"
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                                color: root.hasCustomOverride ? Deck.accent : Deck.muted
                            }
                        }

                        // Shared match indicator for duplicate/stacked binds
                        Rectangle {
                            visible: !root.isAddMode && root.sharedShortcutCount > 0
                            anchors.verticalCenter: parent.verticalCenter
                            height: 18
                            width: sharedText.implicitWidth + 8
                            radius: 3
                            color: Deck.alpha(Deck.warning, 0.15)
                            border.width: 1
                            border.color: Deck.alpha(Deck.warning, 0.4)

                            Text {
                                id: sharedText
                                anchors.centerIn: parent
                                text: "shared with " + root.sharedShortcutCount + (root.sharedShortcutCount === 1 ? " other bind" : " other binds")
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                                color: Deck.warning
                            }
                        }

                        // Reset to default link
                        Item {
                            visible: !root.isAddMode && root.hasCustomOverride
                            anchors.verticalCenter: parent.verticalCenter
                            width: resetLinkTxt.implicitWidth
                            height: 18

                            Text {
                                id: resetLinkTxt
                                anchors.centerIn: parent
                                text: "Reset to default"
                                font.family: Deck.fontFamily
                                font.pixelSize: 10
                                color: resetMa.containsMouse ? Deck.accent : Deck.muted
                                font.underline: true
                            }

                            MouseArea {
                                id: resetMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (!root.bind) return;
                                    SidecarService.clearOverride(root.bind.id, function(success, res, err) {
                                        if (success) {
                                            EditService.showToast("Override cleared, restored default description", false);
                                            EditService.closeEditDialog();
                                        } else {
                                            EditService.showToast("Failed to clear override: " + (err || "error"), false);
                                        }
                                    });
                                }
                            }
                        }
                    }

                    // Character count counter
                    Text {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.descriptionText.length + "/200"
                        font.family: Deck.fontFamily
                        font.pixelSize: 10
                        color: root.descriptionText.length > 200 ? Deck.critical : Deck.muted
                    }
                }

                Row {
                    width: parent.width
                    spacing: 10

                    // Description text input
                    Rectangle {
                        width: parent.width - 170
                        height: 34
                        radius: 6
                        color: Deck.alpha(Deck.surface, 0.7)
                        border.width: 1
                        border.color: descInput.activeFocus ? Deck.accent : Deck.alpha(Deck.muted, 0.25)

                        TextField {
                            id: descInput
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            placeholderText: "Enter custom description..."
                            placeholderTextColor: Deck.alpha(Deck.muted, 0.5)
                            color: Deck.fg
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            background: null
                            verticalAlignment: TextInput.AlignVCenter
                            maximumLength: 200
                            text: root.descriptionText
                            onTextChanged: root.descriptionText = text
                        }
                    }

                    // Category dropdown
                    ComboBox {
                        id: catCombo
                        width: 160
                        height: 34
                        model: SidecarService.categories
                        currentIndex: {
                            var idx = SidecarService.categories.indexOf(root.selectedCategory);
                            return idx !== -1 ? idx : 0;
                        }
                        onActivated: (index) => {
                            if (index >= 0 && index < SidecarService.categories.length) {
                                root.selectedCategory = SidecarService.categories[index];
                            }
                        }
                    }
                }
            }

            // Footer / Action Buttons Row
            Item {
                width: parent.width
                height: 36

                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.validationHint
                    visible: !root.canReview && root.validationHint.length > 0
                    font.family: Deck.fontFamily
                    font.pixelSize: 11
                    color: Deck.warning
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10

                    ActionButton {
                        variant: "neutral"
                        text: "Cancel"
                        onClicked: EditService.closeEditDialog()
                    }

                    ActionButton {
                        variant: "accent"
                        text: {
                            if (root.isAddMode) return "Review addition";
                            if (root.hasMetadataOnlyChanged) return "Save";
                            return "Review changes";
                        }
                        enabled: root.canReview
                        onClicked: {
                            if (!root.isAddMode && root.hasMetadataOnlyChanged) {
                                if (!root.bind) return;
                                SidecarService.setOverride(
                                    root.bind.id,
                                    root.descriptionText,
                                    root.selectedCategory,
                                    function(success, res, err) {
                                        if (success) {
                                            EditService.showToast("Description saved. Undo", true);
                                            EditService.closeEditDialog();
                                        } else {
                                            EditService.showToast("Failed to save description: " + (err || "error"), false);
                                        }
                                    }
                                );
                                return;
                            }

                            var newModsStr = root.newMods.join(" + ");
                            var newKeyStr = root.newKey;
                            var dspId = root.rawExpressionMode ? "custom" : root.selectedDispatcherId;
                            var dspArgs = root.rawExpressionMode ? root.rawExpressionText : root.selectedArgValue;

                            if (root.isAddMode) {
                                var flagList = [];
                                if (root.flagLocked) flagList.push("locked");
                                if (root.flagRepeating) flagList.push("repeating");
                                var flagsStr = flagList.join(",");

                                EditService.previewAdd(
                                    newModsStr,
                                    newKeyStr,
                                    dspId,
                                    dspArgs,
                                    flagsStr,
                                    root.submap,
                                    ConflictCheckService.conflictsList,
                                    root.descriptionText,
                                    root.selectedCategory
                                );
                            } else {
                                if (!root.bind) return;
                                EditService.previewReplace(
                                    root.bind,
                                    newModsStr,
                                    newKeyStr,
                                    dspId,
                                    dspArgs,
                                    root.preserveDispatcher,
                                    ConflictCheckService.conflictsList,
                                    root.descriptionText,
                                    root.selectedCategory
                                );
                            }
                        }
                    }
                }
            }
        }
    }

    // Inner KeybindRecorder instance
    KeybindRecorder {
        id: keybindRecorder
        onAccepted: (modmask, capturedKey, display) => {
            root.newMods = root.modmaskToModifiers(modmask);
            root.newKey = capturedKey;
            ConflictCheckService.check(
                root.newMods.join(" + "),
                root.newKey,
                root.submap,
                root.bind ? root.bind.id : ""
            );
        }
        onCancelled: {
            // Recorder closed without change
        }
    }
}
