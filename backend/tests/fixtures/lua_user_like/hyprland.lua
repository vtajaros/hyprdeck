-- =============================================================================
-- Hyprland Lua Configuration Fixture (User-like shape)
-- =============================================================================

local mainMod = "SUPER"
local terminal = "kitty"
local altTerminal = "alacritty"
local menu = "wofi --show drun"

-- Dynamic theme loader using io.open + pcall(dofile, ...) + os.getenv("HOME")
local theme = {
    active_border = { "rgba(c4bca6ee)", "rgba(85867cee)" },
    inactive_border = "rgba(2b3238aa)",
}
local theme_path = (os.getenv("HOME") or "") .. "/.config/hypr/theme-colors.lua"
local tf = io.open(theme_path, "r")
if tf then
    tf:close()
    local ok, loaded = pcall(dofile, theme_path)
    if ok and type(loaded) == "table" then
        theme = loaded
    end
end

-- Standard Hyprland configuration no-op calls
hl.monitor("eDP-1, 1536x960@60, 0x0, 1")
hl.env("XCURSOR_SIZE", "24")
hl.curve("easeOutQuint", "0.22, 1.0, 0.36, 1.0")
hl.animation("windows", "1, 4, easeOutQuint, slide")
hl.config({
    general = {
        gaps_in = 4,
        gaps_out = 8,
        border_size = 2,
        col = {
            active_border = { colors = theme.active_border, angle = 45 },
            inactive_border = theme.inactive_border,
        },
    },
})
hl.windowrulev2("float", "class:^(pavucontrol)$")
hl.window_rule({ float = true, match = { class = "^blueman-manager$" } })
hl.layer_rule({ blur = true, ignore_alpha = 0.3, match = { namespace = "^qs-bar$" } })
hl.exec_cmd("systemctl --user start quickshell.service")
hl.on("init", function()
    hl.exec_cmd("dunst")
end)

-- Exact wrapper pattern for hl.bind and hl.bindm
hl._orig_bind = hl._orig_bind or hl.bind
local orig_bind = hl._orig_bind

hl.bind = function(...)
    local args = { ... }
    if type(args[2]) == "string" then
        local mod = (args[1] or ""):gsub("^%s*(.-)%s*$", "%1")
        local key = (args[2] or ""):gsub("^%s*(.-)%s*$", "%1")
        local combo = (mod ~= "") and (mod .. " + " .. key) or key
        return orig_bind(combo, select(3, ...))
    end
    return orig_bind(...)
end

hl.bindm = function(mod, key, action)
    local m = (mod or ""):gsub("^%s*(.-)%s*$", "%1")
    local k = (key or ""):gsub("^%s*(.-)%s*$", "%1")
    local combo = (m ~= "") and (m .. " + " .. k) or k
    if action == "movewindow" then
        return orig_bind(combo, hl.dsp.window.drag(), { mouse = true })
    elseif action == "resizewindow" then
        return orig_bind(combo, hl.dsp.window.resize(), { mouse = true })
    end
end

-- Core application and window binds
hl.bind(mainMod .. " + Return",         hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + SHIFT + Return", hl.dsp.exec_cmd(altTerminal))
hl.bind(mainMod .. " + Space",          hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + C",              hl.dsp.window.close())
hl.bind(mainMod .. " + CTRL + L",       hl.dsp.exec_cmd("hyprlock"))
hl.bind("CTRL + ALT + Delete",          hl.dsp.exec_cmd("wlogout"))

-- Single-quoted string containing double quotes and "$(slurp)"
hl.bind(mainMod .. " + SHIFT + S",      hl.dsp.exec_cmd('grim -g "$(slurp)" - | wl-copy'))

-- exec_cmd with pipes and "||"
hl.bind(mainMod .. " + N",              hl.dsp.exec_cmd("dunstctl history-pop || dunstctl close"))

-- Table argument and string argument dispatchers
hl.bind(mainMod .. " + M",              hl.dsp.window.fullscreen({ mode = "maximized" }))
hl.bind(mainMod .. " + J",              hl.dsp.layout("togglesplit"))

-- Two binds on ALT + Tab (both must be kept!)
hl.bind("ALT + Tab",                    hl.dsp.window.cycle_next())
hl.bind("ALT + Tab",                    hl.dsp.window.bring_to_top())
hl.bind("ALT + SHIFT + Tab",            hl.dsp.window.cycle_next({ prev = true }))

-- Loop over {"ALT", mainMod .. " + ALT"} with 4 focus binds (8 binds total)
for _, fmod in ipairs({ "ALT", mainMod .. " + ALT" }) do
    hl.bind(fmod .. " + Left",  hl.dsp.window.focus({ direction = "left" }))
    hl.bind(fmod .. " + Right", hl.dsp.window.focus({ direction = "right" }))
    hl.bind(fmod .. " + Up",    hl.dsp.window.focus({ direction = "up" }))
    hl.bind(fmod .. " + Down",  hl.dsp.window.focus({ direction = "down" }))
end

-- Loop over {mainMod, mainMod .. " + SHIFT"} with 4 move binds (8 binds total)
for _, mmod in ipairs({ mainMod, mainMod .. " + SHIFT" }) do
    hl.bind(mmod .. " + Left",  hl.dsp.window.move({ direction = "left" }))
    hl.bind(mmod .. " + Right", hl.dsp.window.move({ direction = "right" }))
    hl.bind(mmod .. " + Up",    hl.dsp.window.move({ direction = "up" }))
    hl.bind(mmod .. " + Down",  hl.dsp.window.move({ direction = "down" }))
end

-- Workspace loop 1..10 with 3 binds per iteration using i % 10 and numpadKeys (30 binds total)
local numpadKeys = {
    "KP_End", "KP_Down", "KP_Next", "KP_Left", "KP_Begin",
    "KP_Right", "KP_Home", "KP_Up", "KP_Prior", "KP_Insert",
}
for i = 1, 10 do
    local key = tostring(i % 10)
    local npKey = numpadKeys[i]
    hl.bind(mainMod .. " + " .. key,          hl.dsp.workspace.focus(i))
    hl.bind(mainMod .. " + SHIFT + " .. key,  hl.dsp.window.move({ workspace = i }))
    hl.bind(mainMod .. " + " .. npKey,        hl.dsp.workspace.focus(i))
end

-- Relative workspace binds & mouse wheel binds
hl.bind(mainMod .. " + bracketleft",    hl.dsp.workspace.focus("e-1"))
hl.bind(mainMod .. " + bracketright",   hl.dsp.workspace.focus("e+1"))
hl.bind(mainMod .. " + mouse_down",     hl.dsp.workspace.focus("e+1"))
hl.bind(mainMod .. " + mouse_up",       hl.dsp.workspace.focus("e-1"))

-- XF86 hardware keys with {locked=true} and {locked=true, repeating=true}
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("quickshell ipc call osd volumeUp 5"),   { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("quickshell ipc call osd volumeDown 5"), { locked = true, repeating = true })
hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("quickshell ipc call osd toggleMute"),   { locked = true })

-- Two hl.bindm mouse drag/resize calls
hl.bindm(mainMod, "mouse:272", "movewindow")
hl.bindm(mainMod, "mouse:273", "resizewindow")
