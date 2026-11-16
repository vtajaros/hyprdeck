pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string rootPath: Quickshell.env("HKS_ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprland-keybind-studio")
    readonly property bool debugMode: Quickshell.env("HKS_SETTINGS_DEBUG") === "1"

    property bool available: false
    property var wallpaper: ({ path: "", exists: false, source: "none" })
    property var gtk: ({ gsettings_theme: "", gtk3_theme: "", gtk4_theme: "", env_theme: null, effective_theme: "", installed: [] })
    property var icons: ({ gsettings_theme: "", gtk3_theme: "", gtk4_theme: "", qt6ct_theme: "", is_dynamic: false, installed: [] })
    property var cursor: ({ gsettings_theme: "", gtk3_theme: "", gtk4_theme: "", env_theme: null, size: 24, installed: [] })
    property var qt: ({ style: "", icon_theme: "", color_scheme_path: "", platform_theme_env: null, installed_styles: [], installed_color_schemes: [] })
    property string colorScheme: "prefer-dark"
    property var conflicts: []

    property bool loading: true
    property bool busy: false
    property string error: ""
    property string statusMessage: ""
    property string warningMessage: ""
    property bool pollingEnabled: false

    // Session snapshot for "Revert to previous"
    property var _initialSnapshot: null
    property bool hasSessionChanges: false

    Timer {
        id: pollTimer
        interval: 1000
        repeat: true
        running: root.pollingEnabled && !root.busy && !stateProc.running
        onTriggered: root.reload(true)
    }

    function _applyState(data) {
        root.available = !!data.available;
        root.wallpaper = data.wallpaper || root.wallpaper;
        root.gtk = data.gtk || root.gtk;
        root.icons = data.icons || root.icons;
        root.cursor = data.cursor || root.cursor;
        root.qt = data.qt || root.qt;
        root.colorScheme = String(data.color_scheme || "prefer-dark");
        root.conflicts = data.conflicts || [];
        root.error = data.error ? String(data.error) : "";
        if (!root._initialSnapshot && root.available) {
            root._initialSnapshot = {
                gtk: root.gtk.gsettings_theme || root.gtk.gtk3_theme || "",
                icons: root.icons.gsettings_theme || root.icons.gtk3_theme || "",
                cursor: root.cursor.gsettings_theme || root.cursor.gtk4_theme || "Pop",
                cursorSize: Number(root.cursor.size || 24),
                qtStyle: root.qt.style || "",
                qtIcons: root.qt.icon_theme || "",
                qtColors: root.qt.color_scheme_path || ""
            };
        }
    }

    function reload(silent) {
        if (stateProc.running) return;
        if (!silent) {
            root.loading = true;
            root.error = "";
        }
        stateProc.command = ["python3", "-m", "backend.cli", "settings", "themes", "state", "--json"];
        stateProc.running = true;
    }

    function setGtkTheme(name) {
        root.hasSessionChanges = true;
        _runOp(["python3", "-m", "backend.cli", "settings", "themes", "gtk", String(name), "--json"]);
    }

    function setIconTheme(name) {
        root.hasSessionChanges = true;
        _runOp(["python3", "-m", "backend.cli", "settings", "themes", "icons", String(name), "--json"]);
    }

    function setCursor(name, size) {
        root.hasSessionChanges = true;
        var cmd = ["python3", "-m", "backend.cli", "settings", "themes", "cursor", String(name)];
        if (size !== undefined && size !== null) {
            cmd.push(String(Math.round(Number(size))));
        }
        cmd.push("--json");
        _runOp(cmd);
    }

    function setQt(style, iconTheme, colorSchemePath) {
        root.hasSessionChanges = true;
        var cmd = ["python3", "-m", "backend.cli", "settings", "themes", "qt"];
        if (style) cmd.push("--style", String(style));
        if (iconTheme) cmd.push("--icons", String(iconTheme));
        if (colorSchemePath) cmd.push("--colors", String(colorSchemePath));
        cmd.push("--json");
        _runOp(cmd);
    }

    function openWallpaperPicker() {
        _runOp(["python3", "-m", "backend.cli", "settings", "themes", "wallpaper", "open", "--json"]);
    }

    function revertToPrevious() {
        var snap = root._initialSnapshot;
        if (!snap) return;
        root.hasSessionChanges = false;
        if (snap.cursor) {
            setCursor(snap.cursor, snap.cursorSize);
        }
    }

    function _runOp(cmd) {
        root.busy = true;
        root.error = "";
        root.statusMessage = "";
        root.warningMessage = "";
        opProc.running = false;
        opProc.command = cmd;
        opProc.running = true;
    }

    Process {
        id: stateProc
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.loading = false;
                var txt = this.text || "";
                if (txt.trim().length === 0) {
                    root.available = false;
                    root.error = "Empty response from themes state probe.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    root._applyState(data);
                } catch (e) {
                    root.available = false;
                    root.error = "Failed to parse themes state JSON: " + e.message;
                }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: {
                var errTxt = (this.text || "").trim();
                if (errTxt.length > 0 && root.error.length === 0 && !root.available) {
                    root.error = errTxt;
                }
            }
        }
        onExited: function(exitCode) {
            root.loading = false;
            if (exitCode !== 0 && root.error.length === 0) {
                root.available = false;
                root.error = "Themes probe exited with code " + exitCode;
            }
        }
    }

    Process {
        id: opProc
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.busy = false;
                var txt = this.text || "";
                if (txt.trim().length === 0) {
                    root.error = "Empty response from theme operation.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    if (data.ok) {
                        var scope = data.apply_scope ? (" (" + data.apply_scope + ")") : "";
                        root.statusMessage = "Theme updated" + scope + ".";
                        root.warningMessage = data.warning ? String(data.warning) : "";
                        root.error = "";
                    } else {
                        root.error = String(data.error || "Theme operation failed.");
                    }
                    root.reload(true);
                } catch (e) {
                    root.error = "Failed to parse theme op response: " + e.message;
                }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: {
                var errTxt = (this.text || "").trim();
                if (errTxt.length > 0 && root.error.length === 0) {
                    root.error = errTxt;
                }
            }
        }
        onExited: function(exitCode) {
            root.busy = false;
            if (exitCode !== 0 && root.error.length === 0) {
                root.error = "Theme command exited with code " + exitCode;
            }
        }
    }
}
