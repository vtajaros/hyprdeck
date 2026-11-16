import QtQuick
import QtQuick.Window
import Quickshell
import "../../frontend/theme"
import "../../frontend/services"
import "../../frontend/components"

Window {
    id: win
    width: 1120
    height: 760
    visible: true
    color: HKS.bg

    property int step: 0
    readonly property string outDir: Quickshell.env("HKS_CAPTURE_DIR") || "scripts/ui-capture"

    Loader {
        id: pageLoader
        anchors.fill: parent
    }

    KeybindEditDialog {
        id: editDlg
        anchors.fill: parent
        visible: EditService.editDialogOpen
        z: 90
    }

    readonly property string rootDir: Quickshell.env("HYPRDECK_ROOT") || Quickshell.env("HKS_ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")

    Timer {
        id: stepTimer
        interval: 400
        running: true
        repeat: true
        onTriggered: {
            if (win.step === 0) {
                pageLoader.source = "file://" + win.rootDir + "/frontend/pages/Settings.qml";
            } else if (win.step === 1) {
                win.contentItem.grabToImage(function(r) { console.log("SAVE_settings=" + r.saveToFile(win.outDir + "/settings.png")); });
            } else if (win.step === 2) {
                pageLoader.source = "file://" + win.rootDir + "/frontend/pages/Disabled.qml";
            } else if (win.step === 3) {
                win.contentItem.grabToImage(function(r) { console.log("SAVE_disabled=" + r.saveToFile(win.outDir + "/disabled.png")); });
            } else if (win.step === 4) {
                pageLoader.source = "file://" + win.rootDir + "/frontend/pages/Backups.qml";
            } else if (win.step === 5) {
                win.contentItem.grabToImage(function(r) { console.log("SAVE_backups=" + r.saveToFile(win.outDir + "/backups.png")); });
            } else if (win.step === 6) {
                pageLoader.source = "file://" + win.rootDir + "/frontend/pages/AllKeybindings.qml";
                EditService.requestAdd();
            } else if (win.step === 7) {
                win.contentItem.grabToImage(function(r) { console.log("SAVE_add=" + r.saveToFile(win.outDir + "/add.png")); });
            } else if (win.step === 8) {
                EditService.closeEditDialog();
                if (KeybindData.binds && KeybindData.binds.length > 0) {
                    EditService.requestEdit(KeybindData.binds[0]);
                }
            } else if (win.step === 9) {
                stepTimer.stop();
                win.contentItem.grabToImage(function(r) { console.log("SAVE_edit=" + r.saveToFile(win.outDir + "/edit.png")); Qt.quit(); });
            }
            win.step++;
        }
    }
}
