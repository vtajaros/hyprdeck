import QtQuick

QtObject {
    id: root

    property string optionType: "int"
    property var value: 0
    property real minValue: 0
    property real maxValue: 100
    property real stepValue: 1

    function clampNumber(raw) {
        var n = Number(raw);
        if (isNaN(n)) return minValue;
        if (n < minValue) n = minValue;
        if (n > maxValue) n = maxValue;
        if (optionType === "int") {
            return Math.round(n);
        }
        return Math.round(n * 10000) / 10000;
    }

    function stepBy(delta) {
        var cur = Number(value);
        if (isNaN(cur)) cur = minValue;
        return clampNumber(cur + delta * stepValue);
    }

    function isValidColor(s) {
        if (typeof s !== "string") return false;
        return /^(0x[0-9a-fA-F]{6,8}|#[0-9a-fA-F]{6,8})$/.test(s.trim());
    }

    function formatDisplay(val) {
        if (val === null || val === undefined) return "";
        if (optionType === "float") {
            return Number(val).toFixed(2);
        }
        return String(val);
    }

    function enumOptionLabel(val) {
        if (val === null || val === undefined || String(val) === "") {
            return "Default";
        }
        return String(val);
    }
}
