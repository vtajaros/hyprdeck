pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../theme"

Singleton {
    id: root

    property bool busy: false
    property var result: null
    property bool hasConflicts: false
    property var conflictsList: []
    property bool disabledHeld: false
    property var disabledBinds: []

    readonly property string rootPath: Deck.env("ROOT") || "."

    property var _pendingArgs: null

    Timer {
        id: debounceTimer
        interval: 250
        repeat: false
        onTriggered: {
            if (root._pendingArgs) {
                root._runCheck(root._pendingArgs);
            }
        }
    }

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
            root.busy = false;
            if (exitCode === 0) {
                var outStr = outCollector.text || "";
                var parsed = null;
                try {
                    parsed = JSON.parse(outStr);
                } catch (e) {
                    parsed = null;
                }
                if (parsed && parsed.ok) {
                    root.result = parsed;
                    root.hasConflicts = !!parsed.has_conflicts;
                    root.conflictsList = parsed.conflicts || [];
                    root.disabledHeld = !!parsed.disabled_held;
                    root.disabledBinds = parsed.disabled_binds || [];
                }
            }
        }
    }

    function check(mods, key, submap, excludeId) {
        if (!key || !key.trim()) {
            debounceTimer.stop();
            proc.running = false;
            root.busy = false;
            root.result = null;
            root.hasConflicts = false;
            root.conflictsList = [];
            root.disabledHeld = false;
            root.disabledBinds = [];
            return;
        }

        root._pendingArgs = {
            mods: mods || "",
            key: key.trim(),
            submap: submap || "",
            excludeId: excludeId || ""
        };
        debounceTimer.restart();
    }

    function _runCheck(args) {
        if (proc.running) {
            proc.running = false;
        }

        root.busy = true;
        var cmd = [
            "python3", "-m", "backend.cli", "conflicts", "check",
            "--mods", args.mods,
            "--key", args.key,
            "--json"
        ];
        if (args.submap) {
            cmd.push("--submap", args.submap);
        }
        if (args.excludeId) {
            cmd.push("--exclude-id", args.excludeId);
        }

        proc.command = cmd;
        proc.running = true;
    }

    function reset() {
        debounceTimer.stop();
        proc.running = false;
        root.busy = false;
        root.result = null;
        root.hasConflicts = false;
        root.conflictsList = [];
        root.disabledHeld = false;
        root.disabledBinds = [];
    }
}
