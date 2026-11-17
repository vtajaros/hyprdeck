pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../theme"

Singleton {
    id: root

    readonly property string rootPath: Deck.env("ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")

    property bool available: false
    property bool loading: true
    property bool busy: false
    property string error: ""
    property string statusMessage: ""
    property var categories: ["All", "Web", "Files", "Documents", "Images", "Video", "Audio", "Text", "Archives", "Other"]
    property var associations: []
    property var installedApps: []
    property var summary: ({})

    function reload() {
        if (stateProc.running) return;
        root.loading = true;
        root.error = "";
        stateProc.command = ["python3", "-m", "backend.cli", "settings", "apps", "state", "--json"];
        stateProc.running = true;
    }

    function setDefaultApp(mimeType, desktopId) {
        if (root.busy || setProc.running) return;
        if (!mimeType || !desktopId) return;
        root.busy = true;
        root.error = "";
        root.statusMessage = "";
        setProc.command = [
            "python3", "-m", "backend.cli", "settings", "apps", "set",
            "--mime", String(mimeType),
            "--desktop", String(desktopId),
            "--apply", "--json"
        ];
        setProc.running = true;
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
                    root.error = "Empty response from default applications probe.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    root.available = !!data.available;
                    root.categories = Array.isArray(data.categories) ? data.categories : root.categories;
                    root.associations = Array.isArray(data.associations) ? data.associations : [];
                    root.installedApps = Array.isArray(data.installed_apps) ? data.installed_apps : [];
                    root.summary = data.summary || ({});
                    root.error = "";
                } catch (e) {
                    root.available = false;
                    root.error = "Failed to parse default applications JSON: " + e.message;
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
                root.error = "Default applications probe exited with code " + exitCode;
            }
        }
    }

    Process {
        id: setProc
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.busy = false;
                var txt = (this.text || "").trim();
                if (txt.length === 0) {
                    root.error = "Empty response when setting default application.";
                    return;
                }
                try {
                    var res = JSON.parse(txt);
                    if (res.ok) {
                        root.statusMessage = "Default for " + (res.mime_type || "") + " set to " + (res.app_name || res.desktop_id || "") + ".";
                        root.reload();
                    } else {
                        root.error = res.error || "Failed to update default application.";
                    }
                } catch (e) {
                    root.error = "Failed to parse update response: " + e.message;
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
                root.error = "Update default application exited with code " + exitCode;
            }
        }
    }

    Component.onCompleted: {
        reload();
    }
}
