pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "ThemeLogic.js" as ThemeLogic

Singleton {
    id: root

    // Default fixed graphite palette (offline fallback / manual choice)
    readonly property var fallbackPalette: ({
        bg: "#141414",
        surface: "#1c1c1e",
        elevated: "#26262a",
        fg: "#e6e6e6",
        muted: "#9a9a9f",
        accent: "#7fae8b",
        secondary: "#85867c",
        warning: "#d79921",
        critical: "#e06c6c"
    })

    // Active theme mode: "system" ("Follow system (Matugen)") | "graphite" ("Fixed graphite")
    // Note: In-memory selection only for now; not persisted to disk.
    property string themeMode: "system"

    // Overridable colors.json path for isolated tests
    readonly property string colorsPath: Quickshell.env("HKS_THEME_COLORS_PATH")
        || (Quickshell.env("HOME") + "/.config/quickshell/theme/colors.json")

    // Internal state for atomic-replace diffing & partial-write protection
    property string _lastAppliedRaw: ""
    property bool _hasAppliedSystemPalette: false

    // Active palette colors
    property color bg: "#141414"
    property color surface: "#1c1c1e"
    property color elevated: "#26262a"
    property color fg: "#e6e6e6"
    property color foreground: fg
    property color muted: "#9a9a9f"
    property color accent: "#7fae8b"
    property color secondary: "#85867c"
    property color warning: "#d79921"
    property color amber: warning
    property color critical: "#e06c6c"
    property color borderColor: alpha(accent, 0.5)

    // Metrics
    readonly property int radius: 10
    readonly property int radiusMedium: 8
    readonly property int radiusSmall: 6
    readonly property int border: 1
    readonly property int fontSize: 13
    readonly property int fontSizeSmall: 11
    readonly property int fontSizeMedium: 14
    readonly property int fontSizeLarge: 15
    readonly property int fontSizeTitle: 18

    // Spacing scale: 4 / 8 / 12 / 16 / 24
    readonly property int space4: 4
    readonly property int space8: 8
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space24: 24

    // Typography
    readonly property var fontFamilies: [
        "JetBrainsMono Nerd Font",
        "JetBrainsMono Nerd Font Mono",
        "monospace"
    ]
    readonly property string fontFamily: "JetBrainsMono Nerd Font"

    function alpha(c, opacity) {
        var col = Qt.color(c);
        return Qt.rgba(col.r, col.g, col.b, opacity);
    }

    function _applyPalette(p) {
        bg = p.bg;
        surface = p.surface;
        elevated = p.elevated;
        fg = p.fg;
        muted = p.muted;
        accent = p.accent;
        secondary = p.secondary;
        warning = p.warning;
        critical = p.critical;
        borderColor = alpha(accent, 0.5);
    }

    function refreshTheme() {
        if (root.themeMode === "system") {
            colorFile.reload();
        }
    }

    FileView {
        id: colorFile
        path: root.colorsPath
        blockLoading: true
        watchChanges: true
        onFileChanged: root.refreshTheme()
        onLoaded: {
            if (root.themeMode === "system") {
                root.applyTheme();
            }
        }
    }

    // Poll every 1s while following system theme so atomic renames (write + mv) are detected
    Timer {
        id: atomicPollTimer
        interval: 1000
        repeat: true
        running: root.themeMode === "system"
        onTriggered: root.refreshTheme()
    }

    function applyTheme() {
        if (themeMode === "graphite") {
            _applyPalette(fallbackPalette);
            return;
        }

        // themeMode === "system": validate before applying; keep previous palette on partial/invalid writes
        var raw = (typeof colorFile.text === "function") ? colorFile.text() : String(colorFile.text || "");
        var res = ThemeLogic.evaluateThemeText(raw, root._lastAppliedRaw);
        if (!res.changed) {
            return;
        }
        if (res.valid && res.palette) {
            root._lastAppliedRaw = String(raw);
            root._hasAppliedSystemPalette = true;
            _applyPalette(res.palette);
            return;
        }

        if (!root._hasAppliedSystemPalette) {
            _applyPalette(fallbackPalette);
        }
    }

    onThemeModeChanged: {
        if (themeMode === "system") {
            _lastAppliedRaw = "";
            applyTheme();
            refreshTheme();
        } else {
            applyTheme();
        }
    }

    Component.onCompleted: applyTheme()
}
