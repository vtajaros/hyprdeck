pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../theme"

Singleton {
    id: root

    property bool busy: false
    property string error: ""
    property var categories: ["Apps", "Windows", "Workspaces", "Media & Hardware", "System", "Mouse", "Other"]
    property var orphans: []
    property int overrideCount: 0
    property int orphanCount: 0

    readonly property string rootPath: Deck.env("ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")

    property var _queue: []
    property var _currentTask: null

    Process {
        id: proc
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            id: outCollector
            waitForEnd: true
        }
        stderr: StdioCollector {
            id: errCollector
            waitForEnd: true
        }
        onExited: (exitCode, exitStatus) => {
            timeoutTimer.stop();
            var task = root._currentTask;
            root._currentTask = null;
            root.busy = false;

            if (task && task.callback) {
                var outStr = outCollector.text || "";
                var errStr = errCollector.text || "";
                var parsed = null;
                try {
                    parsed = JSON.parse(outStr);
                } catch (e) {
                    parsed = null;
                }
                task.callback(exitCode === 0, parsed, errStr || outStr);
            }

            root._dequeue();
        }
    }

    Timer {
        id: timeoutTimer
        interval: 15000
        repeat: false
        onTriggered: {
            if (root.busy) {
                proc.running = false;
                root.busy = false;
                var task = root._currentTask;
                root._currentTask = null;
                if (task && task.callback) {
                    task.callback(false, null, "Operation timed out.");
                }
                root._dequeue();
            }
        }
    }

    function _runCommand(cmdList, callback) {
        root._queue.push({ cmd: cmdList, callback: callback });
        if (!root.busy) {
            root._dequeue();
        }
    }

    function _dequeue() {
        if (root.busy || root._queue.length === 0) return;
        var task = root._queue.shift();
        root._currentTask = task;
        root.busy = true;
        root.error = "";
        proc.command = task.cmd;
        proc.running = true;
        timeoutTimer.restart();
    }

    function loadCategories(cb) {
        _runCommand(["python3", "-m", "backend.cli", "categories", "--json"], function(success, data, err) {
            if (success && Array.isArray(data) && data.length > 0) {
                root.categories = data;
            }
            if (cb) cb(success, root.categories, err);
        });
    }

    function getOverride(bindId, cb) {
        _runCommand(["python3", "-m", "backend.cli", "sidecar", "get", "--id", bindId, "--json"], function(success, data, err) {
            if (cb) cb(success, data, err);
        });
    }

    function setOverride(bindId, desc, cat, cb) {
        var cmd = ["python3", "-m", "backend.cli", "sidecar", "set", "--id", bindId, "--json"];
        if (desc !== undefined && desc !== null) {
            cmd.push("--desc");
            cmd.push(desc);
        }
        if (cat) {
            cmd.push("--cat");
            cmd.push(cat);
        }
        _runCommand(cmd, function(success, data, err) {
            if (success) {
                KeybindData.reload();
                root.loadOrphans();
                root.loadAllOverrides();
            }
            if (cb) cb(success, data, err);
        });
    }

    function clearOverride(bindId, cb) {
        _runCommand(["python3", "-m", "backend.cli", "sidecar", "clear", "--id", bindId, "--json"], function(success, data, err) {
            if (success) {
                KeybindData.reload();
                root.loadOrphans();
                root.loadAllOverrides();
            }
            if (cb) cb(success, data, err);
        });
    }

    function loadOrphans(cb) {
        _runCommand(["python3", "-m", "backend.cli", "sidecar", "list", "--orphans", "--json"], function(success, data, err) {
            if (success && data && Array.isArray(data.orphans)) {
                root.orphans = data.orphans;
                root.orphanCount = data.orphans.length;
            }
            if (cb) cb(success, root.orphans, err);
        });
    }

    function loadAllOverrides(cb) {
        _runCommand(["python3", "-m", "backend.cli", "sidecar", "list", "--json"], function(success, data, err) {
            if (success && data && Array.isArray(data.overrides)) {
                root.overrideCount = data.overrides.length;
            }
            if (cb) cb(success, data, err);
        });
    }

    function deleteOrphan(match, cb) {
        var cmd = ["python3", "-m", "backend.cli", "sidecar", "clear", "--json"];
        if (match && match.key) {
            cmd.push("--key");
            cmd.push(match.key);
            if (match.modifiers && match.modifiers.length > 0) {
                cmd.push("--mods");
                cmd.push(match.modifiers.join("+"));
            }
            if (match.submap) {
                cmd.push("--submap");
                cmd.push(match.submap);
            }
            if (match.dispatcher) {
                cmd.push("--dispatcher");
                cmd.push(match.dispatcher);
            }
        }
        _runCommand(cmd, function(success, data, err) {
            if (success) {
                root.loadOrphans();
                root.loadAllOverrides();
                KeybindData.reload();
            }
            if (cb) cb(success, data, err);
        });
    }

    Component.onCompleted: {
        root.loadCategories();
        root.loadOrphans();
        root.loadAllOverrides();
    }
}
