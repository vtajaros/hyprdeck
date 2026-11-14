import QtQuick
import QtTest
import "../components"
import "../shared_components"

TestCase {
    id: tc
    name: "tst_settings_controls"

    CloseGuard {
        id: guard
        recorderActive: false
        editDialogOpen: false
        dialogOpen: false
    }

    SettingControlLogic {
        id: boolLogic
        optionType: "bool"
        value: true
    }

    SettingControlLogic {
        id: intLogic
        optionType: "int"
        value: 8
        minValue: 0
        maxValue: 50
        stepValue: 1
    }

    SettingControlLogic {
        id: floatLogic
        optionType: "float"
        value: 0.95
        minValue: 0.1
        maxValue: 1.0
        stepValue: 0.05
    }

    SettingControlLogic {
        id: colorLogic
        optionType: "color"
        value: "0xee0b0e10"
    }

    DisplayControlLogic {
        id: dispLogic
    }

    function test_close_guard_blocks_when_prompt_open() {
        guard.dialogOpen = false;
        verify(guard.closeAllowed);
        guard.dialogOpen = true;
        verify(!guard.closeAllowed);
        guard.dialogOpen = false;
    }

    function test_int_clamping_and_step() {
        compare(intLogic.clampNumber(-5), 0);
        compare(intLogic.clampNumber(100), 50);
        compare(intLogic.clampNumber(12.4), 12);
    }

    function test_float_clamping() {
        compare(floatLogic.clampNumber(0.0), 0.1);
        compare(floatLogic.clampNumber(1.5), 1.0);
        verify(Math.abs(floatLogic.clampNumber(0.55) - 0.55) < 0.001);
    }

    function test_color_validation() {
        verify(colorLogic.isValidColor("0xee0b0e10"));
        verify(colorLogic.isValidColor("#0b0e10"));
        verify(!colorLogic.isValidColor("not-a-color"));
    }

    function test_display_clean_scale_and_warning() {
        verify(dispLogic.isCleanScale(1920, 1200, 1.0));
        verify(dispLogic.isCleanScale(1920, 1200, 1.25));
        verify(dispLogic.isCleanScale(1920, 1200, 1.5));
        verify(dispLogic.isCleanScale(1920, 1200, 2.0));
        verify(!dispLogic.isCleanScale(1920, 1200, 1.75));
        verify(!dispLogic.isCleanScale(1920, 1200, 1.33));
        compare(dispLogic.scaleWarningText(1920, 1200, 1.25), "");
        compare(dispLogic.scaleWarningText(1920, 1200, 1.75), "fractional: may blur");
    }

    function test_display_brightness_floor() {
        compare(dispLogic.clampBrightness(0), 5);
        compare(dispLogic.clampBrightness(4), 5);
        compare(dispLogic.clampBrightness(-10), 5);
        compare(dispLogic.clampBrightness(5), 5);
        compare(dispLogic.clampBrightness(68), 68);
        compare(dispLogic.clampBrightness(140), 100);
    }

    function test_display_last_output_guard() {
        var single = [{ name: "eDP-1", disabled: false }];
        verify(!dispLogic.canDisableOutput(single, {}, "eDP-1"));

        var dual = [{ name: "eDP-1", disabled: false }, { name: "HDMI-A-1", disabled: false }];
        verify(dispLogic.canDisableOutput(dual, {}, "HDMI-A-1"));
        verify(!dispLogic.canDisableOutput(dual, { "HDMI-A-1": { disabled: true } }, "eDP-1"));
    }

    function test_display_transform_labels() {
        compare(dispLogic.transformLabel(0), "Normal");
        compare(dispLogic.transformLabel(1), "90°");
        compare(dispLogic.transformLabel(3), "270°");
        compare(dispLogic.transformLabel(7), "Flipped 270°");
    }
}
