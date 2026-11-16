import QtQuick
import Quickshell
import Quickshell.Io
import "services"

ShellRoot {
    id: root

    readonly property bool debugEnabled: Quickshell.env("HKS_SETTINGS_DEBUG") === "1"

    function _debugDisabledJson() {
        return JSON.stringify({ ok: false, error: "debug mode disabled" });
    }

    function _parseJsonArg(raw) {
        if (raw === undefined || raw === null) return raw;
        var s = String(raw).trim();
        if (s.length === 0) return "";
        try {
            return JSON.parse(s);
        } catch (e) {
            return String(raw);
        }
    }

    IpcHandler {
        target: AppInfo.ipcTarget

        function open() {
            winLoader.item.openWindow();
        }

        function toggle() {
            winLoader.item.toggleWindow();
        }

        function close() {
            winLoader.item.closeWindow(false);
        }

        function reload() {
            SettingsService.reload();
            DisplayService.reload();
            AudioService.reload(false);
            BluetoothService.reload(false);
        }

        function navigate(page: string) {
            winLoader.item.navigate(page);
        }

        function debugSet(id: string, jsonValue: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var val = root._parseJsonArg(jsonValue);
            SettingsService.setDraft(String(id), val);
            return JSON.stringify({ ok: true, id: String(id), value: val });
        }

        function debugSave(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            SettingsService.save();
            return JSON.stringify({ ok: true });
        }

        function debugDiscard(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            SettingsService.discard();
            return JSON.stringify({ ok: true });
        }

        function debugReset(section: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            SettingsService.resetSection(String(section));
            return JSON.stringify({ ok: true, section: String(section) });
        }

        function debugDisplayApply(jsonChanges: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var parsed = null;
            try {
                parsed = JSON.parse(String(jsonChanges));
            } catch (e) {
                return JSON.stringify({ ok: false, error: "Invalid JSON changes: " + e.message });
            }
            DisplayService.applyChanges(parsed);
            return JSON.stringify({ ok: true });
        }

        function debugDisplayKeep(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            DisplayService.keepChanges();
            return JSON.stringify({ ok: true });
        }

        function debugDisplayRevert(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            DisplayService.revertChanges();
            return JSON.stringify({ ok: true });
        }

        function debugInputApply(jsonChanges: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var parsed = null;
            try {
                parsed = JSON.parse(String(jsonChanges));
            } catch (e) {
                return JSON.stringify({ ok: false, error: "Invalid JSON changes: " + e.message });
            }
            InputService.applyChanges(parsed);
            return JSON.stringify({ ok: true });
        }

        function debugInputKeep(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            InputService.keepChanges();
            return JSON.stringify({ ok: true });
        }

        function debugInputRevert(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            InputService.revertChanges();
            return JSON.stringify({ ok: true });
        }

        function debugAudioState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: AudioService.available,
                defaultSink: AudioService.defaultSink,
                defaultSource: AudioService.defaultSource,
                outputs: AudioService.outputs,
                inputs: AudioService.inputs,
                streams: AudioService.streams,
                loading: AudioService.loading,
                busy: AudioService.busy,
                error: AudioService.error,
                statusMessage: AudioService.statusMessage
            });
        }

        function debugAudioSetVolume(kind: string, name: string, percent: int): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var k = (String(kind || "sink").toLowerCase() === "source") ? "source" : "sink";
            var n = String(name || "").trim();
            if (n.length === 0) {
                return JSON.stringify({ ok: false, error: "name is required" });
            }
            AudioService.setVolume(k, n, percent);
            return JSON.stringify({ ok: true, kind: k, name: n, percent: percent });
        }

        function debugAudioSetMute(kind: string, name: string, mode: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var k = (String(kind || "sink").toLowerCase() === "source") ? "source" : "sink";
            var n = String(name || "").trim();
            var m = String(mode || "toggle").trim();
            if (n.length === 0) {
                return JSON.stringify({ ok: false, error: "name is required" });
            }
            AudioService.setMute(k, n, m);
            return JSON.stringify({ ok: true, kind: k, name: n, mode: m });
        }

        function debugBluetoothState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: BluetoothService.available,
                noController: BluetoothService.noController,
                controller: BluetoothService.controller,
                rfkill: BluetoothService.rfkill,
                devices: BluetoothService.devices,
                safety: BluetoothService.safety,
                confirmOpen: BluetoothService.confirmOpen,
                confirmTitle: BluetoothService.confirmTitle,
                confirmMessage: BluetoothService.confirmMessage,
                loading: BluetoothService.loading,
                busy: BluetoothService.busy,
                error: BluetoothService.error,
                statusMessage: BluetoothService.statusMessage
            });
        }

        function debugBluetoothSetPairable(enabled: bool): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            BluetoothService.setPairable(!!enabled);
            return JSON.stringify({ ok: true, pairable: !!enabled });
        }

        function debugBluetoothRequestPowerOff(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            BluetoothService.requestPower(false);
            return JSON.stringify({
                ok: true,
                confirmOpen: BluetoothService.confirmOpen,
                confirmTitle: BluetoothService.confirmTitle,
                confirmMessage: BluetoothService.confirmMessage
            });
        }

        function debugBluetoothCancelConfirm(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            BluetoothService.cancelPending();
            return JSON.stringify({ ok: true, confirmOpen: BluetoothService.confirmOpen });
        }

        function debugState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var optsMap = ({});
            var allOpts = SettingsService.options || [];
            for (var i = 0; i < allOpts.length; i++) {
                var o = allOpts[i];
                if (o && o.id) {
                    optsMap[o.id] = SettingsService.effectiveValue(o);
                }
            }
            return JSON.stringify({
                ok: true,
                currentPage: winLoader.item ? winLoader.item.currentPage : "",
                options: optsMap,
                unsaved: Object.keys(SettingsService.draftValues || ({})),
                pendingResets: Object.keys(SettingsService.pendingResets || ({})),
                hasUnsavedChanges: SettingsService.hasUnsavedChanges,
                includeInstalled: SettingsService.includeInstalled,
                overridesSha256: SettingsService.overridesSha256,
                error: SettingsService.error,
                statusMessage: SettingsService.statusMessage,
                busy: SettingsService.busy,
                loading: SettingsService.loading,
                display: {
                    outputs: DisplayService.outputs,
                    draftOutputs: DisplayService.draftOutputs,
                    brightness: DisplayService.brightness,
                    includeInstalled: DisplayService.includeInstalled,
                    overridesSha256: DisplayService.overridesSha256,
                    countdownActive: DisplayService.countdownActive,
                    remainingSeconds: DisplayService.remainingSeconds,
                    busy: DisplayService.busy,
                    loading: DisplayService.loading,
                    error: DisplayService.error,
                    statusMessage: DisplayService.statusMessage
                },
                input: {
                    options: InputService.options,
                    devices: InputService.devices,
                    deviceOverrides: InputService.deviceOverrides,
                    draftOptions: InputService.draftOptions,
                    draftDevices: InputService.draftDevices,
                    includeInstalled: InputService.includeInstalled,
                    overridesSha256: InputService.overridesSha256,
                    countdownActive: InputService.countdownActive,
                    remainingSeconds: InputService.remainingSeconds,
                    busy: InputService.busy,
                    loading: InputService.loading,
                    error: InputService.error,
                    warningsText: InputService.warningsText,
                    statusMessage: InputService.statusMessage
                },
                audio: {
                    available: AudioService.available,
                    defaultSink: AudioService.defaultSink,
                    defaultSource: AudioService.defaultSource,
                    outputs: AudioService.outputs,
                    inputs: AudioService.inputs,
                    streams: AudioService.streams,
                    busy: AudioService.busy,
                    loading: AudioService.loading,
                    error: AudioService.error,
                    statusMessage: AudioService.statusMessage
                },
                bluetooth: {
                    available: BluetoothService.available,
                    noController: BluetoothService.noController,
                    controller: BluetoothService.controller,
                    rfkill: BluetoothService.rfkill,
                    devices: BluetoothService.devices,
                    safety: BluetoothService.safety,
                    confirmOpen: BluetoothService.confirmOpen,
                    busy: BluetoothService.busy,
                    loading: BluetoothService.loading,
                    error: BluetoothService.error,
                    statusMessage: BluetoothService.statusMessage
                }
            });
        }
    }

    Loader {
        id: winLoader
        source: "WindowShell.qml"
    }
}
