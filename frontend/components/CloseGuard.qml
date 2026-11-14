import QtQuick

// Pure decision logic for the HKS window close [X] button and the app-wide
// Escape shortcut. Kept free of Quickshell/Singleton imports so it is unit
// testable headlessly.
//
//  - Both are blocked while the recorder is active or a modal is open.
//  - Escape is additionally blocked while a text input holds focus, so it
//    never steals focus from search/edit fields.
QtObject {
    id: root

    property bool recorderActive: false
    property bool editDialogOpen: false
    property bool dialogOpen: false
    property var focusItem: null

    function isTextInput(item) {
        return !!item && item.selectedText !== undefined && item.cursorPosition !== undefined;
    }

    readonly property bool textInputFocused: isTextInput(focusItem)
    readonly property bool closeAllowed: !recorderActive && !editDialogOpen && !dialogOpen
    readonly property bool escapeAllowed: closeAllowed && !textInputFocused
}
