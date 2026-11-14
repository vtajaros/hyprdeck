import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    property string section: "appearance" // "appearance" | "desktop"
    property string pageTitle: ""
    property string searchQuery: ""

    readonly property var filteredOptions: {
        var all = SettingsService.options || [];
        var q = (root.searchQuery || "").trim().toLowerCase();
        var out = [];
        for (var i = 0; i < all.length; i++) {
            var o = all[i];
            if (!o || !o.capable) continue;
            if (q.length > 0) {
                var hay = ((o.label || "") + " " + (o.description || "") + " " + (o.group || "") + " " + (o.id || "")).toLowerCase();
                if (hay.indexOf(q) !== -1) out.push(o);
            } else if (o.section === root.section) {
                out.push(o);
            }
        }
        return out;
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
                width: parent.width - resetSectionBtn.width - HKS.space12
                spacing: 4

                Text {
                    text: root.searchQuery.trim().length > 0
                        ? ("Search Results (" + root.filteredOptions.length + ")")
                        : root.pageTitle
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: root.searchQuery.trim().length > 0
                        ? "Matching options across all Hyprland settings."
                        : (root.section === "appearance"
                            ? "Gaps, borders, rounding, blur, shadows, and animations."
                            : "Tiling layouts, dwindle/master behavior, misc flags, and cursor.")
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: HKS.muted
                }
            }

            ActionButton {
                id: resetSectionBtn
                visible: root.searchQuery.trim().length === 0
                text: "Reset section"
                variant: "danger"
                compact: true
                enabled: !SettingsService.busy && SettingsService.includeInstalled
                onClicked: SettingsService.resetSection(root.section)
            }
        }

        // Inline include-missing warning
        Rectangle {
            visible: !SettingsService.loading && !SettingsService.includeInstalled
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
                text: "Include block not installed in hyprland.lua. Live preview works, but Save/Reset require running: python3 -m backend.cli overrides install-include --apply --scan-sha256 <sha>"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.warning
                wrapMode: Text.WordWrap
            }
        }

        // Inline backend error banner
        Rectangle {
            visible: SettingsService.error.length > 0
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
                text: SettingsService.error
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.critical
                wrapMode: Text.WordWrap
            }
        }

        // Scrollable list of options
        ListView {
            id: listView
            width: parent.width
            height: Math.max(100, parent.height - y)
            clip: true
            spacing: HKS.space8
            model: root.filteredOptions

            delegate: SettingRow {
                required property var modelData
                width: listView.width
                option: modelData
                currentValue: SettingsService.effectiveValue(modelData)
                modified: SettingsService.isOptionModified(modelData)
                hasOverride: SettingsService.hasOverride(modelData)
                onValueEdited: function(optionId, newValue) {
                    SettingsService.setDraft(optionId, newValue);
                }
                onResetRequested: function(optionId) {
                    SettingsService.markReset(optionId);
                }
            }

            EmptyState {
                anchors.centerIn: parent
                visible: !SettingsService.loading && listView.count === 0
                title: "No matching options"
                message: "Try a different search query."
            }
        }
    }
}
