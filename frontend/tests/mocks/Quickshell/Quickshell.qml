import QtQuick
pragma Singleton

QtObject {
    function env(key) {
        if (key === "HOME") return "/home/delata";
        if (key === "HKS_MODE") return "window";
        return "";
    }
}
