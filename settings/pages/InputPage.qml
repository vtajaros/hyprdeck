import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    property string activeTab: "keyboard" // "keyboard" | "mouse" | "touchpad" | "devices"
    property bool showVirtualDevices: false
    property bool xkbExpanded: false
    property bool xkbShowAllGroups: false
    property string xkbQuery: ""

    InputControlLogic {
        id: inputLogic
    }

    function _parseCsv(raw) {
        var s = String(raw || "").trim();
        if (s.length === 0) return [];
        var parts = s.split(",");
        var out = [];
        for (var i = 0; i < parts.length; i++) {
            out.push(parts[i].trim());
        }
        return out;
    }

    function _keyboardLayouts() {
        var arr = _parseCsv(InputService.effectiveOptionValue("input.kb_layout") || "us");
        return arr.length > 0 ? arr : ["us"];
    }

    function _keyboardVariants() {
        var layouts = _keyboardLayouts();
        var vars = _parseCsv(InputService.effectiveOptionValue("input.kb_variant") || "");
        while (vars.length < layouts.length) vars.push("");
        return vars.slice(0, layouts.length);
    }

    function _setLayoutPair(layouts, variants) {
        InputService.setOptionDraft("input.kb_layout", layouts.join(","));
        var hasVar = false;
        for (var i = 0; i < variants.length; i++) {
            if (String(variants[i] || "").trim().length > 0) {
                hasVar = true;
                break;
            }
        }
        InputService.setOptionDraft("input.kb_variant", hasVar ? variants.join(",") : "");
    }

    function _activeXkbOptions() {
        var arr = _parseCsv(InputService.effectiveOptionValue("input.kb_options") || "");
        var out = [];
        for (var i = 0; i < arr.length; i++) {
            if (arr[i].length > 0) out.push(arr[i]);
        }
        return out;
    }

    function _hasXkbOption(optId) {
        return _activeXkbOptions().indexOf(optId) !== -1;
    }

    function _toggleXkbOption(optId, exclusiveGroupIds) {
        var cur = _activeXkbOptions();
        var idx = cur.indexOf(optId);
        var next = [];
        if (idx !== -1) {
            for (var i = 0; i < cur.length; i++) {
                if (cur[i] !== optId) next.push(cur[i]);
            }
        } else {
            var excl = exclusiveGroupIds || [];
            for (var j = 0; j < cur.length; j++) {
                if (excl.indexOf(cur[j]) === -1) next.push(cur[j]);
            }
            next.push(optId);
        }
        InputService.setOptionDraft("input.kb_options", next.join(","));
    }

    function _groupOptions(groupName, excludeIds) {
        return inputLogic.groupOptions(InputService.options, groupName, excludeIds);
    }

    function _hiddenVirtualCount() {
        var all = InputService.devices || [];
        var n = 0;
        for (var i = 0; i < all.length; i++) {
            if (all[i] && all[i].virtual) n++;
        }
        return n;
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
                    text: "Input"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: "Keyboard layouts, XKB options, mouse, touchpad, and per-device rules."
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
                    enabled: !InputService.busy && !InputService.countdownActive
                    onClicked: InputService.reload()
                }

                ActionButton {
                    text: "Discard"
                    compact: true
                    visible: InputService.hasDraftChanges
                    enabled: !InputService.busy && !InputService.countdownActive
                    onClicked: InputService.discardDrafts()
                }

                ActionButton {
                    text: InputService.busy ? "Applying..." : "Apply"
                    variant: "accent"
                    compact: true
                    enabled: InputService.hasDraftChanges
                        && !InputService.busy
                        && !InputService.countdownActive
                        && InputService.includeInstalled
                    onClicked: InputService.applyChanges(null)
                }
            }
        }

        // Sub-tabs
        Row {
            spacing: HKS.space8

            Repeater {
                model: [
                    { id: "keyboard", label: "Keyboard" },
                    { id: "mouse", label: "Mouse" },
                    { id: "touchpad", label: "Touchpad" },
                    { id: "devices", label: "Devices" }
                ]
                delegate: ActionButton {
                    required property var modelData
                    text: modelData.label
                    compact: true
                    variant: root.activeTab === modelData.id ? "accent" : "secondary"
                    onClicked: root.activeTab = modelData.id
                }
            }
        }

        // Include missing warning
        Rectangle {
            visible: !InputService.loading && !InputService.includeInstalled
            width: parent.width
            height: incWarnTxt.implicitHeight + 16
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.warning, 0.14)
            border.width: 1
            border.color: HKS.alpha(HKS.warning, 0.5)

            Text {
                id: incWarnTxt
                anchors.fill: parent
                anchors.margins: 8
                text: "Include block not installed in hyprland.lua. Apply requires installing overrides include first."
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.warning
                wrapMode: Text.WordWrap
            }
        }

        // Error banner
        Rectangle {
            visible: InputService.error.length > 0
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
                text: InputService.error
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Non-blocking warnings banner
        Rectangle {
            visible: InputService.warningsText.length > 0
            width: parent.width
            height: warnTxt.implicitHeight + 16
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.warning, 0.14)
            border.width: 1
            border.color: HKS.alpha(HKS.warning, 0.5)

            Text {
                id: warnTxt
                anchors.fill: parent
                anchors.margins: 8
                text: InputService.warningsText
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.warning
                wrapMode: Text.WordWrap
            }
        }

        // Status banner
        Rectangle {
            visible: InputService.statusMessage.length > 0 && InputService.error.length === 0
            width: parent.width
            height: statusTxt.implicitHeight + 14
            radius: HKS.radiusSmall
            color: HKS.alpha(HKS.accent, 0.12)
            border.width: 1
            border.color: HKS.alpha(HKS.accent, 0.4)

            Text {
                id: statusTxt
                anchors.fill: parent
                anchors.margins: 7
                text: InputService.statusMessage
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.accent
                wrapMode: Text.WordWrap
            }
        }

        // Scrollable content area
        Flickable {
            width: parent.width
            height: Math.max(120, parent.height - y)
            contentWidth: width
            contentHeight: tabContentCol.implicitHeight + HKS.space16
            clip: true

            Column {
                id: tabContentCol
                width: parent.width
                spacing: HKS.space12

                // KEYBOARD TAB
                Column {
                    width: parent.width
                    spacing: HKS.space12
                    visible: root.activeTab === "keyboard"

                    // Layouts & Variants Card
                    Rectangle {
                        width: parent.width
                        height: layoutCol.implicitHeight + 24
                        radius: HKS.radiusMedium
                        color: HKS.surface
                        border.width: 1
                        border.color: HKS.alpha(HKS.muted, 0.16)

                        Column {
                            id: layoutCol
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 12
                            spacing: HKS.space8

                            Text {
                                text: "Keyboard Layouts & Variants"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSize
                                font.weight: Font.Medium
                                color: HKS.fg
                            }

                            Repeater {
                                model: root._keyboardLayouts()
                                delegate: RowLayout {
                                    required property string modelData
                                    required property int index
                                    width: parent.width
                                    spacing: HKS.space8

                                    Text {
                                        Layout.preferredWidth: 22
                                        Layout.alignment: Qt.AlignVCenter
                                        text: (index + 1) + "."
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.muted
                                    }

                                    Rectangle {
                                        Layout.preferredWidth: 72
                                        Layout.preferredHeight: 28
                                        Layout.alignment: Qt.AlignVCenter
                                        radius: HKS.radiusSmall
                                        color: HKS.elevated
                                        border.width: 1
                                        border.color: HKS.alpha(HKS.accent, 0.35)

                                        Text {
                                            anchors.centerIn: parent
                                            text: modelData
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            font.weight: Font.Medium
                                            color: HKS.fg
                                        }
                                    }

                                    TextField {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 80
                                        Layout.preferredHeight: 28
                                        Layout.alignment: Qt.AlignVCenter
                                        placeholderText: "variant (optional)"
                                        placeholderTextColor: HKS.alpha(HKS.muted, 0.6)
                                        text: root._keyboardVariants()[index] || ""
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.fg
                                        verticalAlignment: TextInput.AlignVCenter
                                        selectByMouse: true
                                        selectionColor: HKS.alpha(HKS.accent, 0.35)
                                        selectedTextColor: HKS.fg
                                        leftPadding: 8
                                        rightPadding: 8
                                        background: Rectangle {
                                            radius: HKS.radiusSmall
                                            color: HKS.bg
                                            border.width: 1
                                            border.color: parent.activeFocus ? HKS.accent : HKS.alpha(HKS.muted, 0.3)
                                        }
                                        onEditingFinished: {
                                            var ls = root._keyboardLayouts();
                                            var vs = root._keyboardVariants();
                                            vs[index] = text.trim();
                                            root._setLayoutPair(ls, vs);
                                        }
                                    }

                                    ActionButton {
                                        text: "↑"
                                        compact: true
                                        implicitWidth: 30
                                        Layout.preferredWidth: 30
                                        Layout.alignment: Qt.AlignVCenter
                                        enabled: index > 0
                                        onClicked: {
                                            var r = inputLogic.moveLayout(root._keyboardLayouts(), root._keyboardVariants(), index, -1);
                                            root._setLayoutPair(r.layouts, r.variants);
                                        }
                                    }

                                    ActionButton {
                                        text: "↓"
                                        compact: true
                                        implicitWidth: 30
                                        Layout.preferredWidth: 30
                                        Layout.alignment: Qt.AlignVCenter
                                        enabled: index < root._keyboardLayouts().length - 1
                                        onClicked: {
                                            var r = inputLogic.moveLayout(root._keyboardLayouts(), root._keyboardVariants(), index, 1);
                                            root._setLayoutPair(r.layouts, r.variants);
                                        }
                                    }

                                    ActionButton {
                                        text: "✕"
                                        compact: true
                                        implicitWidth: 30
                                        Layout.preferredWidth: 30
                                        Layout.alignment: Qt.AlignVCenter
                                        variant: "danger"
                                        enabled: root._keyboardLayouts().length > 1
                                        onClicked: {
                                            var r = inputLogic.removeLayout(root._keyboardLayouts(), root._keyboardVariants(), index);
                                            root._setLayoutPair(r.layouts, r.variants);
                                        }
                                    }
                                }
                            }

                            // Add layout row
                            RowLayout {
                                width: parent.width
                                spacing: HKS.space8

                                TextField {
                                    id: addLayoutInput
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 90
                                    Layout.preferredHeight: 28
                                    Layout.alignment: Qt.AlignVCenter
                                    placeholderText: "code (e.g. de)"
                                    placeholderTextColor: HKS.alpha(HKS.muted, 0.6)
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.fg
                                    verticalAlignment: TextInput.AlignVCenter
                                    selectByMouse: true
                                    selectionColor: HKS.alpha(HKS.accent, 0.35)
                                    selectedTextColor: HKS.fg
                                    leftPadding: 8
                                    rightPadding: 8
                                    background: Rectangle {
                                        radius: HKS.radiusSmall
                                        color: HKS.bg
                                        border.width: 1
                                        border.color: parent.activeFocus ? HKS.accent : HKS.alpha(HKS.muted, 0.3)
                                    }
                                }

                                TextField {
                                    id: addVariantInput
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 100
                                    Layout.preferredHeight: 28
                                    Layout.alignment: Qt.AlignVCenter
                                    placeholderText: "variant (optional)"
                                    placeholderTextColor: HKS.alpha(HKS.muted, 0.6)
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.fg
                                    verticalAlignment: TextInput.AlignVCenter
                                    selectByMouse: true
                                    selectionColor: HKS.alpha(HKS.accent, 0.35)
                                    selectedTextColor: HKS.fg
                                    leftPadding: 8
                                    rightPadding: 8
                                    background: Rectangle {
                                        radius: HKS.radiusSmall
                                        color: HKS.bg
                                        border.width: 1
                                        border.color: parent.activeFocus ? HKS.accent : HKS.alpha(HKS.muted, 0.3)
                                    }
                                }

                                ActionButton {
                                    text: "Add layout"
                                    compact: true
                                    Layout.alignment: Qt.AlignVCenter
                                    enabled: addLayoutInput.text.trim().length > 0
                                    onClicked: {
                                        var r = inputLogic.addLayout(
                                            root._keyboardLayouts(),
                                            root._keyboardVariants(),
                                            addLayoutInput.text,
                                            addVariantInput.text
                                        );
                                        root._setLayoutPair(r.layouts, r.variants);
                                        addLayoutInput.text = "";
                                        addVariantInput.text = "";
                                    }
                                }
                            }
                        }
                    }

                    // Remaining Keyboard catalog options (repeat_rate, repeat_delay, numlock_by_default, resolve_binds_by_sym)
                    Repeater {
                        model: root._groupOptions(inputLogic.keyboardGroupName(), ["input.kb_layout", "input.kb_variant", "input.kb_options"])
                        delegate: SettingRow {
                            required property var modelData
                            width: tabContentCol.width
                            option: modelData
                            currentValue: InputService.effectiveOptionValue(modelData.id)
                            modified: InputService.draftOptions.hasOwnProperty(modelData.id)
                            hasOverride: !!modelData.has_override
                            onValueEdited: function(optionId, newValue) {
                                InputService.setOptionDraft(optionId, newValue);
                            }
                            onResetRequested: function(optionId) {
                                var o = InputService.findOption(optionId);
                                if (o) {
                                    var baseVal = o.live_value !== undefined ? o.live_value : o.effective_value;
                                    if (baseVal !== undefined) InputService.setOptionDraft(optionId, baseVal);
                                }
                            }
                        }
                    }

                    // Collapsed-by-default Advanced: XKB Options
                    Rectangle {
                        width: parent.width
                        height: xkbCol.implicitHeight + 24
                        radius: HKS.radiusMedium
                        color: HKS.surface
                        border.width: 1
                        border.color: HKS.alpha(HKS.muted, 0.16)
                        visible: (InputService.xkb.option_groups || []).length > 0

                        Column {
                            id: xkbCol
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 12
                            spacing: HKS.space8

                            RowLayout {
                                width: parent.width
                                spacing: HKS.space8

                                Text {
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    text: "Advanced: XKB options (" + root._parseCsv(InputService.effectiveOptionValue("input.kb_options") || "").length + " selected)"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSize
                                    font.weight: Font.Medium
                                    color: HKS.fg
                                    elide: Text.ElideRight
                                }

                                ActionButton {
                                    text: root.xkbExpanded ? "Hide" : "Show"
                                    compact: true
                                    Layout.alignment: Qt.AlignVCenter
                                    onClicked: root.xkbExpanded = !root.xkbExpanded
                                }
                            }

                            Column {
                                visible: root.xkbExpanded
                                width: parent.width
                                spacing: HKS.space8

                                // Selected row
                                Column {
                                    width: parent.width
                                    spacing: 4
                                    visible: root._parseCsv(InputService.effectiveOptionValue("input.kb_options") || "").length > 0

                                    Text {
                                        text: "Selected"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        font.weight: Font.Medium
                                        color: HKS.accent
                                    }

                                    Flow {
                                        width: parent.width
                                        spacing: 6

                                        Repeater {
                                            model: root._parseCsv(InputService.effectiveOptionValue("input.kb_options") || "")
                                            delegate: ActionButton {
                                                required property string modelData
                                                text: modelData + " ✕"
                                                compact: true
                                                variant: "accent"
                                                onClicked: root._toggleXkbOption(modelData, [])
                                            }
                                        }
                                    }
                                }

                                // Search + Common/All toggle
                                RowLayout {
                                    width: parent.width
                                    spacing: HKS.space8

                                    TextField {
                                        id: xkbSearchField
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 28
                                        Layout.alignment: Qt.AlignVCenter
                                        placeholderText: "Search XKB options (e.g. caps, escape, grp)..."
                                        placeholderTextColor: HKS.alpha(HKS.muted, 0.6)
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.fg
                                        verticalAlignment: TextInput.AlignVCenter
                                        selectByMouse: true
                                        selectionColor: HKS.alpha(HKS.accent, 0.35)
                                        selectedTextColor: HKS.fg
                                        leftPadding: 8
                                        rightPadding: 8
                                        text: root.xkbQuery
                                        onTextChanged: root.xkbQuery = text
                                        background: Rectangle {
                                            radius: HKS.radiusSmall
                                            color: HKS.bg
                                            border.width: 1
                                            border.color: parent.activeFocus ? HKS.accent : HKS.alpha(HKS.muted, 0.3)
                                        }
                                    }

                                    ActionButton {
                                        visible: root.xkbQuery.trim().length === 0
                                        text: root.xkbShowAllGroups ? "Common only" : "All groups"
                                        compact: true
                                        Layout.alignment: Qt.AlignVCenter
                                        variant: root.xkbShowAllGroups ? "accent" : "neutral"
                                        onClicked: root.xkbShowAllGroups = !root.xkbShowAllGroups
                                    }
                                }

                                Repeater {
                                    model: {
                                        var groups = InputService.xkb.option_groups || [];
                                        if (root.xkbQuery.trim().length > 0) {
                                            return inputLogic.filterXkbOptionGroups(groups, root.xkbQuery);
                                        }
                                        return root.xkbShowAllGroups ? groups : inputLogic.commonXkbGroups(groups);
                                    }
                                    delegate: Column {
                                        required property var modelData
                                        width: parent.width
                                        spacing: 4

                                        Text {
                                            text: modelData.description || modelData.group || ""
                                            font.family: HKS.fontFamily
                                            font.pixelSize: HKS.fontSizeSmall
                                            font.weight: Font.Medium
                                            color: HKS.accent
                                        }

                                        Flow {
                                            id: xkbFlow
                                            width: parent.width
                                            spacing: 6

                                            Repeater {
                                                model: modelData.options || []
                                                delegate: ActionButton {
                                                    required property var modelData
                                                    readonly property string optCode: String(modelData.code || "")
                                                    readonly property string optLabel: String(modelData.description || modelData.code || "")
                                                    text: optLabel
                                                    compact: true
                                                    width: Math.min(implicitWidth, xkbFlow.width)
                                                    variant: root._hasXkbOption(optCode) ? "accent" : "neutral"
                                                    onClicked: root._toggleXkbOption(optCode, [])
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Test box
                    Rectangle {
                        width: parent.width
                        height: testCol.implicitHeight + 20
                        radius: HKS.radiusMedium
                        color: HKS.surface
                        border.width: 1
                        border.color: HKS.alpha(HKS.muted, 0.16)

                        Column {
                            id: testCol
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 10
                            spacing: 6

                            Text {
                                text: "Keyboard Test Area"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                font.weight: Font.Medium
                                color: HKS.muted
                            }

                            TextField {
                                width: parent.width
                                height: 32
                                placeholderText: "Type here to test layout, repeat rate, and delay..."
                                placeholderTextColor: HKS.alpha(HKS.muted, 0.6)
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSize
                                color: HKS.fg
                                verticalAlignment: TextInput.AlignVCenter
                                selectByMouse: true
                                selectionColor: HKS.alpha(HKS.accent, 0.35)
                                selectedTextColor: HKS.fg
                                leftPadding: 8
                                rightPadding: 8
                                background: Rectangle {
                                    radius: HKS.radiusSmall
                                    color: HKS.bg
                                    border.width: 1
                                    border.color: parent.activeFocus ? HKS.accent : HKS.alpha(HKS.muted, 0.3)
                                }
                            }
                        }
                    }
                }

                // MOUSE TAB
                Column {
                    width: parent.width
                    spacing: HKS.space8
                    visible: root.activeTab === "mouse"

                    EmptyState {
                        visible: !InputService.loading && root._groupOptions(inputLogic.mouseGroupName(), []).length === 0
                        width: parent.width
                        height: 180
                        icon: "󰍽"
                        title: "Mouse options unavailable"
                        message: "No capable mouse options were detected for this session."
                    }

                    Repeater {
                        model: root._groupOptions(inputLogic.mouseGroupName(), [])
                        delegate: SettingRow {
                            required property var modelData
                            width: tabContentCol.width
                            option: modelData
                            currentValue: InputService.effectiveOptionValue(modelData.id)
                            modified: InputService.draftOptions.hasOwnProperty(modelData.id)
                            hasOverride: !!modelData.has_override
                            onValueEdited: function(optionId, newValue) {
                                InputService.setOptionDraft(optionId, newValue);
                            }
                            onResetRequested: function(optionId) {
                                var o = InputService.findOption(optionId);
                                if (o) InputService.setOptionDraft(optionId, o.default);
                            }
                        }
                    }
                }

                // TOUCHPAD TAB
                Column {
                    width: parent.width
                    spacing: HKS.space8
                    visible: root.activeTab === "touchpad"

                    EmptyState {
                        visible: !InputService.loading && root._groupOptions(inputLogic.touchpadGroupName(), []).length === 0
                        width: parent.width
                        height: 180
                        icon: "󰟸"
                        title: "Touchpad options unavailable"
                        message: "No capable touchpad options were detected for this session."
                    }

                    Repeater {
                        model: root._groupOptions(inputLogic.touchpadGroupName(), [])
                        delegate: SettingRow {
                            required property var modelData
                            width: tabContentCol.width
                            option: modelData
                            currentValue: InputService.effectiveOptionValue(modelData.id)
                            modified: InputService.draftOptions.hasOwnProperty(modelData.id)
                            hasOverride: !!modelData.has_override
                            onValueEdited: function(optionId, newValue) {
                                InputService.setOptionDraft(optionId, newValue);
                            }
                            onResetRequested: function(optionId) {
                                var o = InputService.findOption(optionId);
                                if (o) InputService.setOptionDraft(optionId, o.default);
                            }
                        }
                    }
                }

                // DEVICES TAB
                Column {
                    width: parent.width
                    spacing: HKS.space8
                    visible: root.activeTab === "devices"

                    Row {
                        visible: root._hiddenVirtualCount() > 0 || root.showVirtualDevices
                        width: parent.width
                        spacing: HKS.space12

                        ActionButton {
                            text: root.showVirtualDevices
                                ? "Hide virtual devices"
                                : ("Show virtual devices (" + root._hiddenVirtualCount() + " hidden)")
                            compact: true
                            variant: root.showVirtualDevices ? "accent" : "neutral"
                            onClicked: root.showVirtualDevices = !root.showVirtualDevices
                        }
                    }

                    Repeater {
                        model: inputLogic.filterDevices(InputService.devices, root.showVirtualDevices)
                        delegate: Rectangle {
                            required property var modelData
                            width: tabContentCol.width
                            height: devRow.implicitHeight + 16
                            radius: HKS.radiusMedium
                            color: InputService.draftDevices.hasOwnProperty(modelData.name)
                                ? HKS.alpha(HKS.accent, 0.08) : HKS.surface
                            border.width: 1
                            border.color: InputService.draftDevices.hasOwnProperty(modelData.name)
                                ? HKS.alpha(HKS.accent, 0.45) : HKS.alpha(HKS.muted, 0.16)

                            RowLayout {
                                id: devRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                spacing: HKS.space12

                                Row {
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    spacing: HKS.space8

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: modelData.name
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSize
                                        font.weight: Font.Medium
                                        color: HKS.fg
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "[" + (modelData.category || "other") + (modelData.virtual ? ", virtual" : "") + "]"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.muted
                                    }
                                }

                                Item {
                                    Layout.preferredWidth: 270
                                    Layout.preferredHeight: devBtns.implicitHeight
                                    Layout.alignment: Qt.AlignVCenter

                                    Row {
                                        id: devBtns
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: HKS.space8

                                        ActionButton {
                                            visible: InputService.draftDevices.hasOwnProperty(modelData.name)
                                            text: "Discard"
                                            compact: true
                                            onClicked: InputService.clearDeviceDraft(modelData.name)
                                        }

                                        ActionButton {
                                            property bool curNat: !!InputService.effectiveDeviceField(modelData, "natural_scroll")
                                            visible: modelData.category === "mouse" || modelData.category === "touchpad"
                                            text: "Natural scroll: " + (curNat ? "On" : "Off")
                                            compact: true
                                            variant: curNat ? "accent" : "neutral"
                                            onClicked: InputService.setDeviceDraft(modelData.name, "natural_scroll", !curNat)
                                        }

                                        ActionButton {
                                            property bool curEnabled: InputService.effectiveDeviceField(modelData, "enabled") !== false
                                            property bool canDisable: inputLogic.canDisableDevice(InputService.devices, InputService.draftDevices, modelData.name)
                                            text: curEnabled ? "Enabled" : "Disabled"
                                            compact: true
                                            variant: curEnabled ? "accent" : "danger"
                                            enabled: !curEnabled || canDisable
                                            onClicked: InputService.setDeviceDraft(modelData.name, "enabled", !curEnabled)
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
