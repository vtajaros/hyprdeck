import QtQuick

QtObject {
    id: root

    function pairedDevices(devices) {
        var list = devices || [];
        var out = [];
        for (var i = 0; i < list.length; i++) {
            if (list[i] && list[i].paired) {
                out.push(list[i]);
            }
        }
        return out;
    }

    function discoveredDevices(devices) {
        var list = devices || [];
        var out = [];
        for (var i = 0; i < list.length; i++) {
            if (list[i] && !list[i].paired) {
                out.push(list[i]);
            }
        }
        return out;
    }

    function destructiveConsequence(action, device, safety) {
        var act = String(action || "").toLowerCase();
        var s = safety || ({});
        if (act === "power_off") {
            if (s.disconnecting_default_audio && s.default_audio_name) {
                return "This will cut the audio playing on " + s.default_audio_name + ".";
            }
            if (s.powering_off_disconnects) {
                var names = (s.connected_names || []).join(", ");
                return "This will disconnect active Bluetooth devices" + (names ? (" (" + names + ")") : "") + ".";
            }
            return "";
        }
        if (act === "disconnect") {
            if (device && device.connected && device.is_default_sink) {
                return "This will cut the audio playing on " + (device.alias || device.name || device.address) + ".";
            }
            return "";
        }
        if (act === "remove") {
            var label = device ? (device.alias || device.name || device.address) : "this device";
            if (device && device.connected && device.is_default_sink) {
                return "This will cut the audio playing on " + label + " and remove its pairing.";
            }
            return "Remove " + label + "? You will need to pair it again to reconnect.";
        }
        return "";
    }

    function needsConfirm(action, device, safety) {
        return destructiveConsequence(action, device, safety).length > 0;
    }

    function rssiLabel(rssi) {
        if (rssi === undefined || rssi === null) return "";
        return String(rssi) + " dBm";
    }
}
