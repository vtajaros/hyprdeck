import QtQuick

QtObject {
    id: root

    function connectivityLabel(conn) {
        var c = String(conn || "none").toLowerCase();
        if (c === "full") return "Online";
        if (c === "limited") return "Limited";
        if (c === "portal") return "Captive Portal";
        if (c === "none") return "Offline";
        return c;
    }

    function destructiveConsequence(action, targetObj, safety) {
        var act = String(action || "").toLowerCase();
        var s = safety || ({});
        if (act === "wifi_off") {
            if (s.wifi_off_would_cut_session) {
                return "This is your only active connection. Turning Wi-Fi off will cut your current session.";
            }
            return "";
        }
        if (act === "disconnect") {
            if (targetObj && targetObj.would_cut_current_session) {
                return "This is your only active connection. Disconnecting " + (targetObj.name || "this device") + " will cut your current session.";
            }
            return "";
        }
        if (act === "forget") {
            var label = targetObj ? (targetObj.name || targetObj.uuid || "this connection") : "this connection";
            if (targetObj && targetObj.would_cut_current_session) {
                return "This is your only active connection. Forgetting " + label + " will cut your current session.";
            }
            return "Forget saved connection \"" + label + "\"?";
        }
        return "";
    }

    function needsConfirm(action, targetObj, safety) {
        return destructiveConsequence(action, targetObj, safety).length > 0;
    }

    function wifiStateBanner(available, hasWifiDevice, general) {
        if (!available) return "NetworkManager is unavailable.";
        if (!hasWifiDevice) return "No Wi-Fi device found.";
        if (general && !general.wifi_hw_enabled) return "Wi-Fi hardware is disabled.";
        if (general && !general.wifi_enabled) return "Wi-Fi is turned off.";
        return "";
    }

    function shouldAutoRescanOnShow(pageVisible, available, hasWifiDevice, wifiEnabled, busy, scanning, loading, wifiNetworkCount, lastScanEpochMs, nowEpochMs, maxAgeMs) {
        if (!pageVisible || !available || !hasWifiDevice || !wifiEnabled) {
            return false;
        }
        if (busy || scanning || loading) {
            return false;
        }
        if ((wifiNetworkCount || 0) === 0) {
            return true;
        }
        if (!(lastScanEpochMs > 0)) {
            return true;
        }
        var threshold = (maxAgeMs !== undefined && maxAgeMs > 0) ? maxAgeMs : 30000;
        var age = (nowEpochMs || 0) - lastScanEpochMs;
        return age > threshold;
    }

    function savedConnectionsExcludingActiveDevices(connections, devices) {
        var conns = connections || [];
        var devs = devices || [];
        var activeNames = ({});
        for (var i = 0; i < devs.length; i++) {
            var d = devs[i];
            if (d && d.is_active && d.active_connection) {
                activeNames[String(d.active_connection)] = true;
            }
        }
        var out = [];
        for (var j = 0; j < conns.length; j++) {
            var c = conns[j];
            if (!c) continue;
            if (c.name && activeNames[String(c.name)]) {
                continue;
            }
            out.push(c);
        }
        return out;
    }
}
