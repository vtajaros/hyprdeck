pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    // Palette with dark graphite defaults and muted green fallback
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
        onFileChanged: root.loadColors()
    }

    function loadColors() {
        try {
            var raw = colorFile.text();
            if (raw && raw.trim().startsWith("{")) {
                var data = JSON.parse(raw);
                if (data.bg) bg = data.bg;
                if (data.surface) surface = data.surface;
                if (data.elevated) elevated = data.elevated;
                if (data.fg) fg = data.fg;
                if (data.muted) muted = data.muted;
                if (data.accent) accent = data.accent;
                if (data.secondary) secondary = data.secondary;
                if (data.warning) warning = data.warning;
                if (data.critical) critical = data.critical;
            }
        } catch(e) {
            // Silently retain defaults on error or missing file
        }
    }

    Component.onCompleted: loadColors()
}
