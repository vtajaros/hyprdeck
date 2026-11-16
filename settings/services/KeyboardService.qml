pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string rootPath: Quickshell.env("HKS_ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprland-keybind-studio")

    property bool available: false
    property string scriptPath: ""
    property var hksWindowOpen: null
    property bool hksRunning: false
    property bool loading: true
    property bool busy: false
    property string error: ""
    property string statusMessage: ""

    function _applyState(data) {
        root.available = !!data.available;
        root.scriptPath = String(data.script_path || "");
        root.hksWindowOpen = (data.hks_window_open === undefined) ? null : data.hks_window_open;
        root.hksRunning = !!data.hks_running;
        root.error = data.error ? String(data.error) : "";
    }

    function reload() {
        if (stateProc.running) return;
        root.loading = true;
        if (!root.busy) {
            root.error = "";
        }
        stateProc.command = ["python3", "-m", "backend.cli", "settings", "keyboard", "state", "--json"];
        stateProc.running = true;
    }

    function openHks() {
        if (!root.available || root.busy || opProc.running) return;
        root.busy = true;
        root.error = "";
        root.statusMessage = "";
        opProc.command = ["python3", "-m", "backend.cli", "settings", "keyboard", "open", "--json"];
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
                    root.error = "Empty response from keyboard launcher state probe.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    root._applyState(data);
                } catch (e) {
                    root.available = false;
                    root.error = "Failed to parse keyboard state JSON: " + e.message;
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
                root.error = "Keyboard state probe exited with code " + exitCode;
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
                    root.error = "Empty response from Keybind Studio launcher.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    if (data.ok) {
                        root.error = "";
                        if (data.window_open_after !== undefined && data.window_open_after !== null) {
                            root.hksWindowOpen = !!data.window_open_after;
                        }
                        root.statusMessage = "Keybind Studio window opened.";
                    } else {
                        root.error = String(data.error || "Failed to open Keybind Studio.");
                    }
                    root.reload();
                } catch (e) {
                    root.error = "Failed to parse launcher response: " + e.message;
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
                root.error = "Keybind Studio launcher exited with code " + exitCode;
            }
        }
    }
}
