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
}
