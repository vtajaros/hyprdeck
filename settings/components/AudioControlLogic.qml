import QtQuick

QtObject {
    id: root

    function clampVolume(pct, maxPct) {
        var cap = (maxPct !== undefined && maxPct !== null) ? Math.min(150, Math.max(0, Math.round(Number(maxPct) || 100))) : 100;
        var n = Math.round(Number(pct) || 0);
        if (isNaN(n)) return 0;
        return Math.max(0, Math.min(cap, n));
    }

    function kindLabel(kind) {
        var k = String(kind || "other").toLowerCase();
        if (k === "bluez") return "Bluetooth";
        if (k === "hdmi") return "HDMI";
        if (k === "alsa") return "ALSA";
        return "Other";
    }

    function muteLabel(muted) {
        return muted ? "Muted" : "Mute";
    }

    function balanceWarningText(balanceDiff) {
        var d = Math.round(Number(balanceDiff) || 0);
        return d > 0 ? ("L/R diff: " + d + "%") : "";
    }
}
