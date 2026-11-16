import QtQuick

QtObject {
    id: root

    function statusText(available, hksRunning, hksWindowOpen) {
        if (!available) {
            return "Keybind Studio launcher script not found";
        }
        if (hksWindowOpen === true) {
            return "Keybind Studio is open";
        }
        if (hksRunning) {
            return "Background daemon running (window closed)";
        }
        return "Not currently running (launches on demand)";
    }

    function windowStateBadge(hksRunning, hksWindowOpen) {
        if (hksWindowOpen === true) {
            return "Open";
        }
        if (hksRunning) {
            return "Standby";
        }
        return "Closed";
    }

    function buttonLabel(busy, hksWindowOpen) {
        if (busy) {
            return "Opening...";
        }
        if (hksWindowOpen === true) {
            return "Focus Keybind Studio";
        }
        return "Open Keybind Studio";
    }
}
