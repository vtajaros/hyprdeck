import QtQuick
import QtQuick.Controls
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    property string activeTab: "keyboard" // "keyboard" | "mouse" | "touchpad" | "devices"
    property bool showVirtualDevices: false

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
        var all = InputService.options || [];
        var excl = excludeIds || [];
        var out = [];
        for (var i = 0; i < all.length; i++) {
            var o = all[i];
            if (!o || !o.capable) continue;
            if (o.group !== groupName) continue;
            if (excl.indexOf(o.id) !== -1) continue;
            out.push(o);
        }
        return out;
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
                                font.pixelSize: HKS.fontSizeBody
                                font.weight: Font.Medium
                                color: HKS.fg
                            }

                            Repeater {
                                model: root._keyboardLayouts()
                                delegate: Row {
                                    required property string modelData
                                    required property int index
                                    width: parent.width
                                    spacing: HKS.space8

                                    Text {
                                        width: 24
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: (index + 1) + "."
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.muted
                                    }

                                    Rectangle {
                                        width: 80
                                        height: 28
                                        radius: HKS.radiusSmall
                                        color: HKS.surfaceAlt
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
                                        width: Math.max(120, parent.width - 250)
                                        height: 28
                                        placeholderText: "variant (optional)"
                                        text: root._keyboardVariants()[index] || ""
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.fg
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
                                        enabled: index > 0
                                        onClicked: {
                                            var r = inputLogic.moveLayout(root._keyboardLayouts(), root._keyboardVariants(), index, -1);
                                            root._setLayoutPair(r.layouts, r.variants);
                                        }
                                    }

                                    ActionButton {
                                        text: "↓"
                                        compact: true
                                        enabled: index < root._keyboardLayouts().length - 1
                                        onClicked: {
                                            var r = inputLogic.moveLayout(root._keyboardLayouts(), root._keyboardVariants(), index, 1);
                                            root._setLayoutPair(r.layouts, r.variants);
                                        }
                                    }

                                    ActionButton {
                                        text: "✕"
                                        compact: true
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
                            Row {
                                width: parent.width
                                spacing: HKS.space8

                                TextField {
                                    id: addLayoutInput
                                    width: 120
                                    height: 28
                                    placeholderText: "code (e.g. de)"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.fg
                                }

                                TextField {
                                    id: addVariantInput
                                    width: 140
                                    height: 28
                                    placeholderText: "variant (optional)"
                                    font.family: HKS.fontFamily
                                    font.pixelSize: HKS.fontSizeSmall
                                    color: HKS.fg
                                }

                                ActionButton {
                                    text: "Add layout"
                                    compact: true
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

                    // XKB Option Groups Card
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

                            Text {
                                text: "XKB Options"
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeBody
                                font.weight: Font.Medium
                                color: HKS.fg
                            }

                            Repeater {
                                model: InputService.xkb.option_groups || []
                                delegate: Column {
                                    required property var modelData
                                    width: parent.width
                                    spacing: 4

                                    Text {
                                        text: modelData.label || modelData.id || ""
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        font.weight: Font.Medium
                                        color: HKS.accent
                                    }

                                    Flow {
                                        width: parent.width
                                        spacing: 6

                                        Repeater {
                                            model: modelData.options || []
                                            delegate: ActionButton {
                                                required property var modelData
                                                property var groupOpts: []
                                                text: modelData.label || modelData.id
                                                compact: true
                                                variant: root._hasXkbOption(modelData.id) ? "accent" : "secondary"
                                                onClicked: {
                                                    var ids = [];
                                                    if (parent && parent.parent) {
                                                        // no-op; group exclusivity handled below
                                                    }
                                                    root._toggleXkbOption(modelData.id, []);
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Remaining Keyboard catalog options (repeat_rate, repeat_delay, numlock_by_default, resolve_binds_by_sym)
                    Repeater {
                        model: root._groupOptions("keyboard", ["input.kb_layout", "input.kb_variant", "input.kb_options"])
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
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeBody
                                color: HKS.fg
                            }
                        }
                    }
                }

                // MOUSE TAB
                Column {
                    width: parent.width
                    spacing: HKS.space8
                    visible: root.activeTab === "mouse"

                    Repeater {
                        model: root._groupOptions("mouse", [])
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

                    Repeater {
                        model: root._groupOptions("touchpad", [])
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
                    spacing: HKS.space12
                    visible: root.activeTab === "devices"

                    Row {
                        width: parent.width
                        spacing: HKS.space12

                        ActionButton {
                            text: root.showVirtualDevices
                                ? "Hide virtual devices"
                                : ("Show virtual devices (" + root._hiddenVirtualCount() + " hidden)")
                            compact: true
                            variant: root.showVirtualDevices ? "accent" : "secondary"
                            onClicked: root.showVirtualDevices = !root.showVirtualDevices
                        }
                    }

                    Repeater {
                        model: inputLogic.filterDevices(InputService.devices, root.showVirtualDevices)
                        delegate: Rectangle {
                            required property var modelData
                            width: tabContentCol.width
                            height: devCol.implicitHeight + 24
                            radius: HKS.radiusMedium
                            color: InputService.draftDevices.hasOwnProperty(modelData.name)
                                ? HKS.alpha(HKS.accent, 0.08) : HKS.surface
                            border.width: 1
                            border.color: InputService.draftDevices.hasOwnProperty(modelData.name)
                                ? HKS.alpha(HKS.accent, 0.45) : HKS.alpha(HKS.muted, 0.16)

                            Column {
                                id: devCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: HKS.space8

                                Row {
                                    width: parent.width
                                    spacing: HKS.space8

                                    Text {
                                        text: modelData.name
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeBody
                                        font.weight: Font.Medium
                                        color: HKS.fg
                                    }

                                    Text {
                                        text: "[" + (modelData.category || "other") + (modelData.virtual ? ", virtual" : "") + "]"
                                        font.family: HKS.fontFamily
                                        font.pixelSize: HKS.fontSizeSmall
                                        color: HKS.muted
                                    }
                                }

                                Row {
                                    spacing: HKS.space12

                                    ActionButton {
                                        property bool curEnabled: InputService.effectiveDeviceField(modelData, "enabled") !== false
                                        property bool canDisable: inputLogic.canDisableDevice(InputService.devices, InputService.draftDevices, modelData.name)
                                        text: curEnabled ? "Enabled" : "Disabled"
                                        compact: true
                                        variant: curEnabled ? "accent" : "danger"
                                        enabled: !curEnabled || canDisable
                                        onClicked: InputService.setDeviceDraft(modelData.name, "enabled", !curEnabled)
                                    }

                                    ActionButton {
                                        property bool curNat: !!InputService.effectiveDeviceField(modelData, "natural_scroll")
                                        visible: modelData.category === "mouse" || modelData.category === "touchpad"
                                        text: "Natural scroll: " + (curNat ? "On" : "Off")
                                        compact: true
                                        variant: curNat ? "accent" : "secondary"
                                        onClicked: InputService.setDeviceDraft(modelData.name, "natural_scroll", !curNat)
                                    }

                                    ActionButton {
                                        visible: InputService.draftDevices.hasOwnProperty(modelData.name)
                                        text: "Discard"
                                        compact: true
                                        onClicked: InputService.clearDeviceDraft(modelData.name)
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
