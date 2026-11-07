pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

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
    property color critical: "#e06c6c"

    // Metrics
    readonly property int radius: 10
    readonly property int radiusSmall: 6
    readonly property int border: 1
    readonly property int fontSize: 13
    readonly property int fontSizeSmall: 11
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

    FileView {
        id: colorFile
        path: Quickshell.env("HOME") + "/.config/quickshell/theme/colors.json"
        blockLoading: true
        watchChanges: true
        onFileChanged: {
            if (root.themeMode === "system") {
                root.applyTheme();
            }
        }
    }

    function applyTheme() {
        if (themeMode === "graphite") {
            bg = fallbackPalette.bg;
            surface = fallbackPalette.surface;
            elevated = fallbackPalette.elevated;
            fg = fallbackPalette.fg;
            muted = fallbackPalette.muted;
            accent = fallbackPalette.accent;
            secondary = fallbackPalette.secondary;
            warning = fallbackPalette.warning;
            critical = fallbackPalette.critical;
            return;
        }

        // themeMode === "system": read live colors.json with fallback
        try {
            var raw = colorFile.text();
            if (raw && raw.trim().startsWith("{")) {
                var data = JSON.parse(raw);
                bg = data.bg || fallbackPalette.bg;
                surface = data.surface || fallbackPalette.surface;
                elevated = data.elevated || fallbackPalette.elevated;
                fg = data.fg || fallbackPalette.fg;
                muted = data.muted || fallbackPalette.muted;
                accent = data.accent || fallbackPalette.accent;
                secondary = data.secondary || fallbackPalette.secondary;
                warning = data.warning || fallbackPalette.warning;
                critical = data.critical || fallbackPalette.critical;
                return;
            }
        } catch(e) {
            // Silently fall back to defaults
        }

        bg = fallbackPalette.bg;
        surface = fallbackPalette.surface;
        elevated = fallbackPalette.elevated;
        fg = fallbackPalette.fg;
        muted = fallbackPalette.muted;
        accent = fallbackPalette.accent;
        secondary = fallbackPalette.secondary;
        warning = fallbackPalette.warning;
        critical = fallbackPalette.critical;
    }

    onThemeModeChanged: applyTheme()

    Component.onCompleted: applyTheme()
}
