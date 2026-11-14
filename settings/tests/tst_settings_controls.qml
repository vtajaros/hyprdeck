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
}
