-- =============================================================================
-- Hyprland Keybind Studio (HKS) - Sandboxed Lua 5.4 Bind Recorder
-- Usage: lua5.4 recorder.lua <entry_abs_path> <config_dir_abs>
-- =============================================================================

local _assert = assert
local _error = error
local _ipairs = ipairs
local _pairs = pairs
local _next = next
local _pcall = pcall
local _xpcall = xpcall
local _select = select
local _tonumber = tonumber
local _tostring = tostring
local _type = type
local _rawget = rawget
local _rawset = rawset
local _rawequal = rawequal
local _rawlen = rawlen
local _setmetatable = setmetatable
local _getmetatable = getmetatable
local _load = load
local _loadfile = loadfile
local _string = string
local _table = table
local _math = math
local _utf8 = utf8
local _io = io
local _os = os
local _debug = debug
local _collectgarbage = collectgarbage

local RECORDER_VERSION = 1
local entry_arg = arg and arg[1]
local config_dir_arg = arg and arg[2]
local limit_arg = arg and _tonumber(arg[3])
local INSTRUCTION_LIMIT = limit_arg or 50000000
local INSTRUCTION_STEP = 100000
local MAX_HOOK_CALLS = _math.floor(INSTRUCTION_LIMIT / INSTRUCTION_STEP)
if MAX_HOOK_CALLS < 1 then
    MAX_HOOK_CALLS = 1
end
local recorder_info = _debug.getinfo(1, "S")
local recorder_source = (recorder_info and recorder_info.source) or ""
local recorder_path = recorder_source:sub(1, 1) == "@" and recorder_source:sub(2) or ""

-- Private marker metatables
local ARRAY_MT = { __name = "hks_array" }
local DSP_DESCRIPTOR_MT = { __name = "hks_dsp_descriptor" }

local function make_array(t)
    return _setmetatable(t or {}, ARRAY_MT)
end

-- State containers
local binds = make_array()
local files_loaded = make_array()
local files_loaded_seen = {}
local diagnostics = make_array()
local unexecuted_callbacks = make_array()
local ignored_calls = {}
local unknown_api_seen = {}
local submap_warning_emitted = false
local site_occurrences = {}
local complete = true
local hook_calls = 0

local function add_diagnostic(level, code, message, file, line)
    diagnostics[#diagnostics + 1] = {
        level = level,
        code = code,
        message = _tostring(message),
        file = file,
        line = line,
    }
end

-- Normalize a path textually (resolving "." and "..")
local function normalize_path(path, base_dir)
    if _type(path) ~= "string" or path == "" then
        return nil
    end
    local p = path
    if p:sub(1, 1) ~= "/" then
        if base_dir and base_dir ~= "" then
            p = base_dir .. "/" .. p
        else
            return nil
        end
    end
    local parts = {}
    for seg in _string.gmatch(p, "[^/]+") do
        if seg == "." or seg == "" then
            -- skip
        elseif seg == ".." then
            if #parts > 0 then
                _table.remove(parts)
            end
        else
            parts[#parts + 1] = seg
        end
    end
    return "/" .. _table.concat(parts, "/")
end

local config_dir = normalize_path(config_dir_arg or "", "/")
local entry_path = normalize_path(entry_arg or "", config_dir)

-- Remap $HOME/.config/hypr or $XDG_CONFIG_HOME/hypr to config_dir so configs
-- using `os.getenv("HOME") .. "/.config/hypr/..."` stay strictly inside config_dir
local real_home = _os.getenv("HOME")
local real_xdg = _os.getenv("XDG_CONFIG_HOME")
local home_hypr_prefix = real_home and normalize_path(real_home .. "/.config/hypr", "/") or nil
local xdg_hypr_prefix = real_xdg and normalize_path(real_xdg .. "/hypr", "/") or nil

local function resolve_sandbox_path(raw_path)
    if _type(raw_path) ~= "string" or raw_path == "" then
        return nil
    end
    local norm = normalize_path(raw_path, config_dir)
    if not norm then
        return nil
    end
    if config_dir then
        if home_hypr_prefix and home_hypr_prefix ~= config_dir then
            if norm == home_hypr_prefix then
                norm = config_dir
            elseif norm:sub(1, #home_hypr_prefix + 1) == home_hypr_prefix .. "/" then
                norm = config_dir .. norm:sub(#home_hypr_prefix + 1)
            end
        end
        if xdg_hypr_prefix and xdg_hypr_prefix ~= config_dir then
            if norm == xdg_hypr_prefix then
                norm = config_dir
            elseif norm:sub(1, #xdg_hypr_prefix + 1) == xdg_hypr_prefix .. "/" then
                norm = config_dir .. norm:sub(#xdg_hypr_prefix + 1)
            end
        end
    end
    return norm
end

local function is_inside_config_dir(norm_path)
    if not norm_path or not config_dir then
        return false
    end
    if norm_path == config_dir then
        return true
    end
    local prefix = config_dir == "/" and "/" or (config_dir .. "/")
    return norm_path:sub(1, #prefix) == prefix
end

local function record_loaded_file(norm_path)
    if norm_path and not files_loaded_seen[norm_path] then
        files_loaded_seen[norm_path] = true
        files_loaded[#files_loaded + 1] = norm_path
    end
end

-- Find current caller file & line in user config
local function find_caller_location(hl_tbl)
    local bind_fn = hl_tbl and _rawget(hl_tbl, "bind") or nil
    local bindm_fn = hl_tbl and _rawget(hl_tbl, "bindm") or nil
    local on_fn = hl_tbl and _rawget(hl_tbl, "on") or nil
    local frames = make_array()
    local skipping_wrappers = true

    for level = 2, 64 do
        local info = _debug.getinfo(level, "Slft")
        if not info then
            break
        end
        local src = info.source or ""
        if src:sub(1, 1) == "@" then
            local file_path = src:sub(2)
            if file_path ~= recorder_path then
                if skipping_wrappers and (
                    (bind_fn and info.func == bind_fn) or
                    (bindm_fn and info.func == bindm_fn) or
                    (on_fn and info.func == on_fn)
                ) then
                    -- skip user's hl.bind / hl.bindm / hl.on wrapper frame
                else
                    skipping_wrappers = false
                    frames[#frames + 1] = {
                        file = file_path,
                        line = info.currentline or 0,
                        what = info.what or "Lua",
                        istailcall = info.istailcall and true or false,
                    }
                end
            end
        end
    end

    local source_file = entry_path or ""
    local source_line = 0
    if #frames > 0 then
        source_file = frames[1].file
        source_line = frames[1].line
    end
    return source_file, source_line, frames
end

-- Deep copy & sanitize values for recording
local function sanitize_value(val, visited, depth)
    depth = (depth or 0) + 1
    if depth > 16 then
        return "<max_depth>"
    end
    local tv = _type(val)
    if tv == "nil" or tv == "boolean" or tv == "string" then
        return val
    elseif tv == "number" then
        if val ~= val or val == _math.huge or val == -_math.huge then
            add_diagnostic("warning", "json_non_finite_number", "Non-finite number (NaN/Inf) replaced with null", entry_path, nil)
            return nil
        end
        return val
    elseif tv == "function" then
        return "<function>"
    elseif tv == "userdata" then
        return "<userdata>"
    elseif tv == "thread" then
        return "<thread>"
    elseif tv == "table" then
        visited = visited or {}
        if visited[val] then
            return "<cycle>"
        end
        visited[val] = true
        -- Check if sequence 1..n
        local count = 0
        local max_idx = 0
        local is_array = true
        for k, _ in _pairs(val) do
            count = count + 1
            if _math.type(k) == "integer" and k >= 1 then
                if k > max_idx then
                    max_idx = k
                end
            else
                is_array = false
            end
        end
        if is_array and count > 0 and max_idx == count then
            local arr = make_array()
            for i = 1, count do
                arr[i] = sanitize_value(_rawget(val, i), visited, depth)
            end
            visited[val] = nil
            return arr
        else
            local obj = {}
            for k, v in _pairs(val) do
                obj[_tostring(k)] = sanitize_value(v, visited, depth)
            end
            visited[val] = nil
            return obj
        end
    end
    return _tostring(val)
end

-- Shallow copy standard libraries for sandbox isolation
local function shallow_copy(t)
    local out = {}
    for k, v in _pairs(t) do
        out[k] = v
    end
    return out
end

local E = {}

-- Forward reference for hl so find_caller_location can use it
local hl = {}

-- Known no-op Hyprland Lua APIs
local KNOWN_NOOPS = {
    monitor = true,
    env = true,
    animation = true,
    curve = true,
    config = true,
    windowrulev2 = true,
    window_rule = true,
    layer_rule = true,
    exec_cmd = true,
    on = true,
}

local function check_submap_mention(str, file, line)
    if not submap_warning_emitted and _type(str) == "string" then
        if _string.find(_string.lower(str), "submap", 1, true) then
            submap_warning_emitted = true
            add_diagnostic(
                "warning",
                "lua_submap_unsupported",
                "Lua submap API/dispatcher referenced ('" .. str .. "'); Lua submap semantics are unverified.",
                file,
                line
            )
        end
    end
end

-- Dispatcher proxy builder (`hl.dsp`)
local function make_dsp_proxy(prefix)
    local proxy = {}
    local mt = {
        __index = function(_, key)
            local k = _tostring(key)
            local next_path = prefix and (prefix .. "." .. k) or k
            return make_dsp_proxy(next_path)
        end,
        __call = function(_, ...)
            local path = prefix or ""
            local sfile, sline = find_caller_location(hl)
            check_submap_mention(path, sfile, sline)
            local argc = _select("#", ...)
            local raw_args = { ... }
            local clean_args = make_array()
            for i = 1, argc do
                clean_args[i] = sanitize_value(raw_args[i])
            end
            return _setmetatable({
                path = path,
                args = clean_args,
                argc = argc,
            }, DSP_DESCRIPTOR_MT)
        end,
    }
    return _setmetatable(proxy, mt)
end

-- Recorder function R (`hl.bind`)
local function record_bind(keys, action, opts)
    local source_file, source_line, trace = find_caller_location(hl)
    local site_key = source_file .. ":" .. _tostring(source_line)
    local occ = site_occurrences[site_key] or 0
    site_occurrences[site_key] = occ + 1

    local parse_status = "ok"
    local keys_str = _type(keys) == "string" and keys or _tostring(keys)
    local dispatcher_obj = nil
    local copied_opts = {}

    if opts ~= nil then
        if _type(opts) == "table" then
            copied_opts = sanitize_value(opts)
            if _getmetatable(copied_opts) == ARRAY_MT then
                -- Convert empty/array table to plain object if needed
                local plain = {}
                for k, v in _pairs(copied_opts) do
                    plain[_tostring(k)] = v
                end
                copied_opts = plain
            end
        else
            parse_status = "unsupported"
            copied_opts = { _raw_opts = _tostring(opts) }
            add_diagnostic(
                "warning",
                "unsupported_bind_opts",
                "Bind options must be a table or nil, got " .. _type(opts),
                source_file,
                source_line
            )
        end
    end

    if _type(keys) ~= "string" then
        parse_status = "unsupported"
        dispatcher_obj = {
            path = "<unsupported>",
            args = make_array({ _tostring(keys), _tostring(action), _tostring(opts) }),
        }
        add_diagnostic(
            "warning",
            "unsupported_bind_keys",
            "Bind keys argument must be a string, got " .. _type(keys),
            source_file,
            source_line
        )
    elseif _getmetatable(action) == DSP_DESCRIPTOR_MT then
        check_submap_mention(action.path, source_file, source_line)
        dispatcher_obj = {
            path = action.path,
            args = action.args,
        }
    elseif _type(action) == "function" then
        local fn_info = _debug.getinfo(action, "S")
        local cb_line = (fn_info and fn_info.linedefined and fn_info.linedefined > 0) and fn_info.linedefined or nil
        dispatcher_obj = {
            path = "<lua_callback>",
            args = make_array(),
            callback_line = cb_line,
        }
    else
        parse_status = "unsupported"
        dispatcher_obj = {
            path = "<unsupported>",
            args = make_array({ _tostring(keys), _tostring(action), _tostring(opts) }),
        }
        add_diagnostic(
            "warning",
            "unsupported_bind_action",
            "Bind action must be an hl.dsp descriptor or function, got " .. _type(action),
            source_file,
            source_line
        )
    end

    binds[#binds + 1] = {
        keys = keys_str,
        dispatcher = dispatcher_obj,
        opts = copied_opts,
        source_file = source_file,
        source_line = source_line,
        occurrence = occ,
        occurrences_at_site = 1, -- updated after execution completes
        trace = trace,
        parse_status = parse_status,
    }
end

hl.bind = record_bind

local function record_on(event, fn)
    ignored_calls["on"] = (ignored_calls["on"] or 0) + 1
    local source_file, source_line, _ = find_caller_location(hl)
    local ev_str = _type(event) == "string" and event or "?"
    unexecuted_callbacks[#unexecuted_callbacks + 1] = {
        event = ev_str,
        line = source_line,
    }
    add_diagnostic(
        "info",
        "callbacks_not_executed",
        "Event callback for '" .. ev_str .. "' at line " .. _tostring(source_line) .. " was not executed",
        source_file,
        source_line
    )
    return nil
end

hl.on = record_on
hl.dsp = make_dsp_proxy(nil)

_setmetatable(hl, {
    __index = function(_, key)
        if _type(key) == "string" and key:sub(1, 1) == "_" then
            return nil
        end
        local name = _tostring(key)
        return function(...)
            ignored_calls[name] = (ignored_calls[name] or 0) + 1
            local sfile, sline = find_caller_location(hl)
            check_submap_mention(name, sfile, sline)
            if not KNOWN_NOOPS[name] and not unknown_api_seen[name] then
                unknown_api_seen[name] = true
                add_diagnostic(
                    "info",
                    "unknown_api",
                    "Unknown Hyprland Lua API called: hl." .. name .. " (first called at line " .. _tostring(sline) .. ")",
                    sfile,
                    sline
                )
            end
            return nil
        end
    end,
})

-- Sandbox os replacement
local ALLOWED_ENV_VARS = {
    HOME = true,
    XDG_CONFIG_HOME = true,
    XDG_SESSION_TYPE = true,
    USER = true,
    LANG = true,
}

local sandbox_os = {
    getenv = function(varname)
        if _type(varname) == "string" and ALLOWED_ENV_VARS[varname] then
            return _os.getenv(varname)
        end
        return nil
    end,
    time = _os.time,
    date = _os.date,
    clock = _os.clock,
}

_setmetatable(sandbox_os, {
    __index = function(_, key)
        local name = _tostring(key)
        return function(...)
            local sfile, sline = find_caller_location(hl)
            complete = false
            add_diagnostic(
                "error",
                "sandbox_denied",
                "sandbox: os." .. name .. " is not permitted",
                sfile,
                sline
            )
            return nil, "sandbox: os." .. name .. " not permitted"
        end
    end,
})

-- Sandbox io replacement
local function wrap_read_only_file(f)
    local handle = {}
    function handle:read(...)
        return f:read(...)
    end
    function handle:lines(...)
        return f:lines(...)
    end
    function handle:seek(...)
        return f:seek(...)
    end
    function handle:close()
        return f:close()
    end
    function handle:write(...)
        local sfile, sline = find_caller_location(hl)
        complete = false
        add_diagnostic("error", "sandbox_denied", "sandbox: file write is not permitted", sfile, sline)
        return nil, "sandbox: write not permitted"
    end
    function handle:flush()
        return true
    end
    return handle
end

local sandbox_io = {
    open = function(path, mode)
        local m = mode == nil and "r" or mode
        local sfile, sline = find_caller_location(hl)
        if m ~= "r" and m ~= "rb" then
            complete = false
            add_diagnostic(
                "error",
                "sandbox_denied",
                "sandbox: io.open mode '" .. _tostring(m) .. "' not permitted for path: " .. _tostring(path),
                sfile,
                sline
            )
            return nil, "sandbox: path not permitted"
        end
        local norm = resolve_sandbox_path(path)
        if not is_inside_config_dir(norm) then
            complete = false
            add_diagnostic(
                "error",
                "sandbox_denied",
                "sandbox: path not permitted: " .. _tostring(path),
                sfile,
                sline
            )
            return nil, "sandbox: path not permitted"
        end
        local f, err = _io.open(norm, m)
        if not f then
            return nil, err
        end
        record_loaded_file(norm)
        return wrap_read_only_file(f)
    end,
}

_setmetatable(sandbox_io, {
    __index = function(_, key)
        local name = _tostring(key)
        return function(...)
            local sfile, sline = find_caller_location(hl)
            complete = false
            add_diagnostic(
                "error",
                "sandbox_denied",
                "sandbox: io." .. name .. " is not permitted",
                sfile,
                sline
            )
            return nil, "sandbox: io." .. name .. " not permitted"
        end
    end,
})

-- Sandbox load / loadfile / dofile / require
local function sandbox_load(chunk, chunkname, _mode, _env)
    if _type(chunk) ~= "string" and _type(chunk) ~= "function" then
        return nil, "sandbox: invalid chunk"
    end
    if _type(chunk) == "string" and chunk:byte(1) == 27 then
        local sfile, sline = find_caller_location(hl)
        complete = false
        add_diagnostic("error", "sandbox_denied", "sandbox: binary bytecode chunks are not permitted", sfile, sline)
        return nil, "sandbox: binary chunk not permitted"
    end
    return _load(chunk, chunkname or "=(load)", "t", E)
end

local function sandbox_loadfile(path, _mode, _env)
    local sfile, sline = find_caller_location(hl)
    local norm = resolve_sandbox_path(path)
    if not is_inside_config_dir(norm) then
        complete = false
        add_diagnostic(
            "error",
            "sandbox_denied",
            "sandbox: loadfile path not permitted: " .. _tostring(path),
            sfile,
            sline
        )
        return nil, "sandbox: path not permitted"
    end
    local f, err = _io.open(norm, "r")
    if not f then
        return nil, err
    end
    local content = f:read("*a")
    f:close()
    record_loaded_file(norm)
    return _load(content, "@" .. norm, "t", E)
end

local function sandbox_dofile(path)
    local fn, err = sandbox_loadfile(path)
    if not fn then
        _error(err, 0)
    end
    return fn()
end

local require_cache = {}

local function sandbox_require(modname)
    local sfile, sline = find_caller_location(hl)
    if _type(modname) ~= "string" or modname == "" then
        _error("bad argument #1 to 'require' (string expected)", 2)
    end
    if require_cache[modname] ~= nil then
        return require_cache[modname]
    end
    -- Reject traversal patterns in module name
    if modname:sub(1, 1) == "/" or modname:sub(1, 1) == "." or _string.find(modname, "..", 1, true) then
        complete = false
        add_diagnostic(
            "error",
            "sandbox_denied",
            "sandbox: require module outside config_dir not permitted: " .. modname,
            sfile,
            sline
        )
        _error("sandbox: module not permitted: " .. modname, 0)
    end
    local rel = _string.gsub(modname, "%.", "/")
    local cand1 = resolve_sandbox_path(config_dir .. "/" .. rel .. ".lua")
    local cand2 = resolve_sandbox_path(config_dir .. "/" .. rel .. "/init.lua")
    local chosen = nil
    for _, cand in _ipairs({ cand1, cand2 }) do
        if is_inside_config_dir(cand) then
            local f = _io.open(cand, "r")
            if f then
                f:close()
                chosen = cand
                break
            end
        else
            complete = false
            add_diagnostic(
                "error",
                "sandbox_denied",
                "sandbox: require path not permitted: " .. _tostring(cand),
                sfile,
                sline
            )
            _error("sandbox: module not permitted: " .. modname, 0)
        end
    end
    if not chosen then
        _error("module '" .. modname .. "' not found in " .. _tostring(config_dir), 0)
    end
    local fn, err = sandbox_loadfile(chosen)
    if not fn then
        _error(err, 0)
    end
    local res = fn(modname, chosen)
    if res == nil then
        res = true
    end
    require_cache[modname] = res
    return res
end

-- Populate sandbox environment E
E.assert = _assert
E.error = _error
E.ipairs = _ipairs
E.pairs = _pairs
E.next = _next
E.pcall = _pcall
E.xpcall = _xpcall
E.select = _select
E.tonumber = _tonumber
E.tostring = _tostring
E.type = _type
E.rawget = _rawget
E.rawset = _rawset
E.rawequal = _rawequal
E.rawlen = _rawlen
E.setmetatable = function(tbl, mt)
    if _type(tbl) ~= "table" then
        _error("bad argument #1 to 'setmetatable' (table expected)", 2)
    end
    if mt == DSP_DESCRIPTOR_MT or mt == ARRAY_MT then
        _error("sandbox: protected metatable", 2)
    end
    return _setmetatable(tbl, mt)
end
E.getmetatable = function(obj)
    if _type(obj) == "string" then
        return nil
    end
    local mt = _getmetatable(obj)
    if mt == DSP_DESCRIPTOR_MT or mt == ARRAY_MT then
        return "hks_protected"
    end
    return mt
end
E.string = shallow_copy(_string)
E.table = shallow_copy(_table)
E.math = shallow_copy(_math)
E.utf8 = shallow_copy(_utf8)
E.os = sandbox_os
E.io = sandbox_io
E.load = sandbox_load
E.loadfile = sandbox_loadfile
E.dofile = sandbox_dofile
E.require = sandbox_require
E.hl = hl
E.print = function(...) end -- silence any print calls so stdout remains pure JSON
E._G = E

-- Deterministic JSON Encoder
local ESCAPE_MAP = {
    ['"'] = '\\"',
    ['\\'] = '\\\\',
    ['\b'] = '\\b',
    ['\f'] = '\\f',
    ['\n'] = '\\n',
    ['\r'] = '\\r',
    ['\t'] = '\\t',
}

local function escape_json_string(s)
    return '"' .. _string.gsub(s, '[%z\1-\31\\"]', function(c)
        return ESCAPE_MAP[c] or _string.format("\\u%04x", _string.byte(c))
    end) .. '"'
end

local function encode_json(val)
    local tv = _type(val)
    if tv == "nil" then
        return "null"
    elseif tv == "boolean" then
        return val and "true" or "false"
    elseif tv == "number" then
        if val ~= val or val == _math.huge or val == -_math.huge then
            return "null"
        elseif _math.type(val) == "integer" then
            return _string.format("%d", val)
        else
            return _string.format("%.17g", val)
        end
    elseif tv == "string" then
        return escape_json_string(val)
    elseif tv == "table" then
        local mt = _getmetatable(val)
        local is_array = (mt == ARRAY_MT)
        if not is_array then
            local count = 0
            local max_idx = 0
            local all_int = true
            for k, _ in _pairs(val) do
                count = count + 1
                if _math.type(k) == "integer" and k >= 1 then
                    if k > max_idx then
                        max_idx = k
                    end
                else
                    all_int = false
                    break
                end
            end
            if all_int and count > 0 and max_idx == count then
                is_array = true
            end
        end

        if is_array then
            local items = {}
            local n = _rawlen(val)
            for i = 1, n do
                items[i] = encode_json(_rawget(val, i))
            end
            return "[" .. _table.concat(items, ",") .. "]"
        else
            local keys = {}
            for k, _ in _pairs(val) do
                keys[#keys + 1] = _tostring(k)
            end
            _table.sort(keys)
            local pairs_out = {}
            for i = 1, #keys do
                local k = keys[i]
                local raw_v = val[k]
                if raw_v ~= nil then
                    pairs_out[#pairs_out + 1] = escape_json_string(k) .. ":" .. encode_json(raw_v)
                end
            end
            return "{" .. _table.concat(pairs_out, ",") .. "}"
        end
    else
        return escape_json_string("<" .. tv .. ">")
    end
end

-- Execute entrypoint inside sandbox with instruction hook
local function run_entry()
    if not entry_path or not config_dir then
        complete = false
        add_diagnostic("error", "recorder_invalid_args", "Missing entrypoint or config_dir arguments", nil, nil)
        return
    end

    local f, open_err = _io.open(entry_path, "r")
    if not f then
        complete = false
        add_diagnostic("error", "config_load_error", "Cannot open entrypoint: " .. _tostring(open_err), entry_path, nil)
        return
    end
    local source_code = f:read("*a")
    f:close()
    record_loaded_file(entry_path)

    local chunk, load_err = _load(source_code, "@" .. entry_path, "t", E)
    if not chunk then
        complete = false
        local line_num = _tonumber(_string.match(_tostring(load_err), ":(%d+):"))
        add_diagnostic("error", "config_runtime_error", _tostring(load_err), entry_path, line_num)
        return
    end

    hook_calls = 0
    local err_file = entry_path
    local err_line = nil

    _debug.sethook(function()
        hook_calls = hook_calls + 1
        if hook_calls > MAX_HOOK_CALLS then
            _debug.sethook()
            _error("__HKS_INSTRUCTION_LIMIT__", 0)
        end
    end, "", INSTRUCTION_STEP)

    local ok, run_err = _xpcall(chunk, function(err)
        _debug.sethook()
        local sfile, sline = find_caller_location(hl)
        if sfile and sfile ~= "" then
            err_file = sfile
        end
        if sline and sline > 0 then
            err_line = sline
        end
        return err
    end)

    _debug.sethook()

    if not ok then
        _collectgarbage("collect")
        complete = false
        local msg = _tostring(run_err)
        if _string.find(msg, "__HKS_INSTRUCTION_LIMIT__", 1, true) then
            add_diagnostic(
                "error",
                "instruction_limit",
                "Execution exceeded instruction budget (" .. _tostring(INSTRUCTION_LIMIT) .. " instructions)",
                err_file,
                err_line
            )
        elseif _string.find(msg, "^sandbox:") then
            -- sandbox_denied diagnostic was already added at the denial site; ensure complete=false
        else
            local parsed_line = _tonumber(_string.match(msg, ":(%d+):")) or err_line
            add_diagnostic(
                "error",
                "config_runtime_error",
                msg,
                err_file,
                parsed_line
            )
        end
    end
end

run_entry()

-- Populate occurrences_at_site for each recorded bind
for i = 1, #binds do
    local b = binds[i]
    local site_key = b.source_file .. ":" .. _tostring(b.source_line)
    b.occurrences_at_site = site_occurrences[site_key] or 1
end

local instructions_used = hook_calls * INSTRUCTION_STEP

local output_doc = {
    recorder_version = RECORDER_VERSION,
    binds = binds,
    files_loaded = files_loaded,
    diagnostics = diagnostics,
    ignored_calls = ignored_calls,
    unexecuted_callbacks = unexecuted_callbacks,
    complete = complete,
    instructions_used = instructions_used,
    instruction_limit = INSTRUCTION_LIMIT,
}

_io.stdout:write(encode_json(output_doc) .. "\n")
_io.stdout:flush()
