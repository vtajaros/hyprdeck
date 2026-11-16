import QtQuick

QtObject {
    id: root

    function secToMin(sec) {
        var s = Number(sec);
        if (isNaN(s) || s <= 0) return 1;
        return Math.max(1, Math.min(1440, Math.round(s / 60)));
    }

    function minToSec(minVal) {
        var m = Number(minVal);
        if (isNaN(m) || m <= 0) return 30;
        return Math.max(30, Math.min(86400, Math.round(m * 60)));
    }

    function validateIdleOrder(dimSec, lockSec, dpmsSec) {
        var d = Math.round(Number(dimSec) || 0);
        var l = Math.round(Number(lockSec) || 0);
        var p = Math.round(Number(dpmsSec) || 0);
        if (d < 30 || d > 86400 || l < 30 || l > 86400 || p < 30 || p > 86400) {
            return "All idle timeouts must be between 1 and 1440 minutes (30s..86400s).";
        }
        if (d >= l) {
            return "Dim timeout must be shorter than Lock timeout.";
        }
        if (l >= p) {
            return "Lock timeout must be shorter than Display Off timeout.";
        }
        return "";
    }

    function roleLabel(role) {
        var r = String(role || "").toLowerCase();
        if (r === "dim") return "Dim screen";
        if (r === "lock") return "Lock session";
        if (r === "dpms") return "Turn off display";
        if (r === "suspend") return "Suspend";
        return "Custom listener";
    }

    function eppLabel(epp) {
        var e = String(epp || "").toLowerCase();
        if (e === "performance") return "Performance";
        if (e === "balance_performance") return "Balanced";
        if (e === "balance_power") return "Power Saver";
        if (e === "power") return "Max Saver";
        if (e === "default") return "Default";
        return String(epp || "");
    }

    function needsTurboConfirm(targetEnabled) {
        return targetEnabled === false;
    }

    function formatCopyAllText(info) {
        if (!info) return "";
        var lines = [];
        var add = function(label, val) {
            if (val !== undefined && val !== null && String(val).length > 0) {
                lines.push(label + ": " + String(val));
            }
        };
        add("Hostname", info.hostname);
        add("OS", info.os_name);
        add("Kernel", info.kernel);
        add("Hardware", info.vendor_model);
        add("CPU", info.cpu_model ? (info.cpu_model + (info.cpu_cores ? (" (" + info.cpu_cores + " threads)") : "")) : null);
        if (info.ram_used && info.ram_total) {
            add("Memory", info.ram_used + " / " + info.ram_total);
        }
        if (info.disk_root_used && info.disk_root_total) {
            add("Root Disk", info.disk_root_used + " / " + info.disk_root_total + (info.disk_root_percent ? (" (" + info.disk_root_percent + ")") : ""));
        }
        add("GPU", info.gpu);
        add("Uptime", info.uptime);
        add("Hyprland", info.hyprland_version);
        add("Quickshell", info.quickshell_version);
        return lines.join("\n");
    }
}
