pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string rootPath: Quickshell.env("HKS_ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprland-keybind-studio")

    property bool available: false
    property var info: ({})
    property bool loading: true
    property string error: ""

    function reload() {
        if (infoProc.running) return;
        root.loading = true;
        root.error = "";
        infoProc.command = ["python3", "-m", "backend.cli", "settings", "system", "info", "--json"];
        infoProc.running = true;
    }

    Process {
        id: infoProc
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.loading = false;
                var txt = this.text || "";
                if (txt.trim().length === 0) {
                    root.available = false;
                    root.error = "Empty response from system info probe.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    root.available = !!data.available;
                    root.info = data;
                    root.error = "";
                } catch (e) {
                    root.available = false;
                    root.error = "Failed to parse system info JSON: " + e.message;
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
                root.error = "System info probe exited with code " + exitCode;
            }
        }
    }
}
