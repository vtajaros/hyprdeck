import QtQuick
import QtQuick.Layouts
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

    PageViewport {
        id: viewport
        anchors.fill: parent
        allowTwoColumns: true

        header: PageHeader {
            title: root.searchQuery.trim().length > 0
                ? ("Search Results (" + root.filteredOptions.length + ")")
                : root.pageTitle
            subtitle: root.searchQuery.trim().length > 0
                ? "Matching options across all Hyprland settings."
                : (root.section === "appearance"
                    ? "Gaps, borders, rounding, blur, shadows, and animations."
                    : "Tiling layouts, dwindle/master behavior, misc flags, and cursor.")

            ActionButton {
                id: resetSectionBtn
                visible: root.searchQuery.trim().length === 0
                text: "Reset to Defaults"
                variant: "danger"
                compact: true
                enabled: !SettingsService.busy && SettingsService.includeInstalled
                onClicked: SettingsService.resetSection(root.section)
            }
        }

        // Inline include-missing warning
        Rectangle {
            visible: !SettingsService.loading && !SettingsService.includeInstalled
            width: viewport.innerWidth
            height: incWarnTxt.implicitHeight + 16
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.warning, 0.14)
            border.width: 1
            border.color: Deck.alpha(Deck.warning, 0.5)

            Text {
                id: incWarnTxt
                anchors.fill: parent
                anchors.margins: 8
                text: "Include block not installed in hyprland.lua. Live preview works, but Save/Reset require running: python3 -m backend.cli overrides install-include --apply --scan-sha256 <sha>"
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.warning
                wrapMode: Text.WordWrap
            }
        }

        // Inline backend error banner
        Rectangle {
            visible: SettingsService.error.length > 0
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
                text: SettingsService.error
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.critical
                wrapMode: Text.WordWrap
            }
        }

        EmptyState {
            visible: !SettingsService.loading && root.filteredOptions.length === 0
            width: viewport.innerWidth
            height: 220
            title: "No matching options"
            message: "Try a different search query."
        }

        // Two columns at >= 1200px viewport width; single column below (equal row heights via GridLayout)
        GridLayout {
            visible: root.filteredOptions.length > 0
            width: viewport.innerWidth
            columns: viewport.twoColumns ? 2 : 1
            columnSpacing: viewport.columnSpacing
            rowSpacing: viewport.columnSpacing

            Repeater {
                model: root.filteredOptions
                delegate: SettingRow {
                    required property var modelData
                    Layout.preferredWidth: viewport.twoColumnCardWidth
                    Layout.fillWidth: true
                    Layout.fillHeight: true
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
            }
        }
    }
}
