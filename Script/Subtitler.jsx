(function (thisObj) {

// ================= @block PLUG:JSON:001 @desc JSON Polyfill for ExtendScript =================
if (typeof JSON === 'undefined') {
    JSON = {};
}

JSON.parse = (function() {
    var at, ch, text,
        escapee = {
            '"': '"',
            '\\': '\\',
            '/': '/',
            'b': '\b',
            'f': '\f',
            'n': '\n',
            'r': '\r',
            't': '\t'
        };
    
    function error(m) {
        throw new SyntaxError('JSON.parse: ' + m + ' at position ' + at);
    }
    
    function next(c) {
        if (c && c !== ch) {
            error("Expected '" + c + "' instead of '" + ch + "'");
        }
        ch = text.charAt(at);
        at += 1;
        return ch;
    }
    
    function white() {
        while (ch && ch <= ' ') {
            next();
        }
    }
    
    function number() {
        var num = '', v;
        if (ch === '-') { num = '-'; next('-'); }
        while (ch >= '0' && ch <= '9') { num += ch; next(); }
        if (ch === '.') {
            num += '.'; next();
            while (ch >= '0' && ch <= '9') { num += ch; next(); }
        }
        if (ch === 'e' || ch === 'E') {
            num += ch; next();
            if (ch === '-' || ch === '+') { num += ch; next(); }
            while (ch >= '0' && ch <= '9') { num += ch; next(); }
        }
        v = Number(num);
        if (!isFinite(v)) { error("Bad number"); }
        return v;
    }
    
    function string() {
        var hex, i, v = '', uffff;
        if (ch === '"') {
            while (next()) {
                if (ch === '"') { next(); return v; }
                if (ch === '\\') {
                    next();
                    if (ch === 'u') {
                        uffff = 0;
                        for (i = 0; i < 4; i++) {
                            hex = parseInt(next(), 16);
                            if (!isFinite(hex)) { break; }
                            uffff = uffff * 16 + hex;
                        }
                        v += String.fromCharCode(uffff);
                    } else if (typeof escapee[ch] === 'string') {
                        v += escapee[ch];
                    } else { break; }
                } else { v += ch; }
            }
        }
        error("Bad string");
    }
    
    function word() {
        switch (ch) {
            case 't': next('t'); next('r'); next('u'); next('e'); return true;
            case 'f': next('f'); next('a'); next('l'); next('s'); next('e'); return false;
            case 'n': next('n'); next('u'); next('l'); next('l'); return null;
        }
        error("Unexpected '" + ch + "'");
    }
    
    function array() {
        var arr = [];
        if (ch === '[') {
            next('['); white();
            if (ch === ']') { next(']'); return arr; }
            while (ch) {
                arr.push(value()); white();
                if (ch === ']') { next(']'); return arr; }
                next(','); white();
            }
        }
        error("Bad array");
    }
    
    function object() {
        var key, obj = {};
        if (ch === '{') {
            next('{'); white();
            if (ch === '}') { next('}'); return obj; }
            while (ch) {
                key = string(); white(); next(':');
                if (Object.prototype.hasOwnProperty.call(obj, key)) { error("Duplicate key '" + key + "'"); }
                obj[key] = value(); white();
                if (ch === '}') { next('}'); return obj; }
                next(','); white();
            }
        }
        error("Bad object");
    }
    
    function value() {
        white();
        switch (ch) {
            case '{': return object();
            case '[': return array();
            case '"': return string();
            case '-': return number();
            default: if (ch >= '0' && ch <= '9') { return number(); } return word();
        }
    }
    
    return function(source) {
        if (typeof source !== 'string') { source = String(source); }
        text = source; at = 0; ch = ' ';
        var result = value(); white();
        if (ch) { error("Unexpected characters after JSON"); }
        return result;
    };
})();

if (typeof JSON.stringify !== 'function') {
    JSON.stringify = function(obj, replacer, space) {
        var type = typeof obj;
        if (type !== "object" || obj === null) {
            if (type === "string") return '"' + obj.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
            return String(obj);
        }
        var isArray = obj instanceof Array;
        var json = [];
        for (var k in obj) {
            if (obj.hasOwnProperty(k)) {
                var v = obj[k];
                var vType = typeof v;
                var val;
                if (v === null) { val = "null"; }
                else if (vType === "undefined") { continue; }
                else if (vType === "string") { val = '"' + v.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r') + '"'; }
                else if (vType === "number" || vType === "boolean") { val = String(v); }
                else if (vType === "object") { val = JSON.stringify(v, replacer, space); }
                else { continue; }
                if (isArray) { json.push(val); } else { json.push('"' + k + '":' + val); }
            }
        }
        return isArray ? "[" + json.join(",") + "]" : "{" + json.join(",") + "}";
    };
}
// ================= END JSON POLYFILL =================

// ================= @block PLUG:INIT:001 @desc Global Variables & Constants =================
    var SCRIPT_NAME = "Subtitler";
    var SCRIPT_VERSION = "0.50.0";
    var VERSION_NAME = "PrevedMedved";
    var DEV_URL = "https://helixgem.site";    
    var SCRIPT_URL = "https://subtitler.qzz.io";
    var DOCS_URL = "https://subtitler.qzz.io/#donate"; // PLACEHOLDER - заменить на реальную ссылку
    var SETTINGS_FILE = Folder.userData.absoluteURI + "/subtitleservice_settings.json";
    var CHECK_INTERVAL_MS = 3000;
    var MAX_WAIT_TIME_MS = 600000;
    
    var settings = {
        accessKey: "",
        serverUrl: "",
        lastUsed: "",
        autoSnap: false,
        snapThreshold: 5
    };
    
    var currentTaskId = null;
    var isWaiting = false;
    var pollStartTime = 0;

// ================= @block PLUG:INIT:002 @desc Translation Languages =================
    var TRANSLATION_LANGUAGES = [
        { code: "orig", name: "Original (no translation)", flag: "📄" },
        { code: "en", name: "English", flag: "🇬🇧" },
        { code: "ru", name: "Русский", flag: "🇷🇺" },
        { code: "es", name: "Español", flag: "🇪🇸" },
        { code: "de", name: "Deutsch", flag: "🇩🇪" },
        { code: "fr", name: "Français", flag: "🇫🇷" },
        { code: "it", name: "Italiano", flag: "🇮🇹" },
        { code: "pt", name: "Português", flag: "🇵🇹" },
        { code: "zh", name: "中文", flag: "🇨🇳" },
        { code: "ja", name: "日本語", flag: "🇯🇵" },
        { code: "ko", name: "한국어", flag: "🇰🇷" },
        { code: "ar", name: "العربية", flag: "🇸🇦" },
        { code: "hi", name: "हिन्दी", flag: "🇮🇳" },
        { code: "tr", name: "Türkçe", flag: "🇹🇷" },
        { code: "pl", name: "Polski", flag: "🇵🇱" },
        { code: "nl", name: "Nederlands", flag: "🇳🇱" },
        { code: "uk", name: "Українська", flag: "🇺🇦" }
    ];

// ================= @block PLUG:HTTP:001 @desc URL Parser =================
    
    function parseUrl(url) {
        var result = { protocol: "http", host: "", port: 80, path: "/" };
        var s = url;
        if (s.indexOf("https://") === 0) { result.protocol = "https"; result.port = 443; s = s.substring(8); }
        else if (s.indexOf("http://") === 0) { result.protocol = "http"; result.port = 80; s = s.substring(7); }
        var pathIndex = s.indexOf("/");
        if (pathIndex !== -1) { result.path = s.substring(pathIndex); s = s.substring(0, pathIndex); }
        var portIndex = s.indexOf(":");
        if (portIndex !== -1) { result.port = parseInt(s.substring(portIndex + 1), 10); result.host = s.substring(0, portIndex); }
        else { result.host = s; }
        return result;
    }
    
    function escapeUrl(url) {
        // Убираем только опасные символы, оставляем валидные URL символы
        return url.replace(/[\s<>|`]/g, '');
    }
    
// ================= @block PLUG:HTTP:002 @desc HTTP Response Parser =================
        // Обработка всех HTTP статусов (100 Continue, редиректы)
    function parseHttpResponse(output) {
        if (!output || output.length === 0) {
            return { success: false, status: 0, body: "", error: "Empty response" };
        }
        
        // Ищем ВСЕ HTTP статусы (может быть несколько из-за 100 Continue или редиректов)
        var allMatches = [];
        var regex = /HTTP\/[\d.]+\s+(\d+)/g;
        var match;
        while ((match = regex.exec(output)) !== null) {
            allMatches.push({
                status: parseInt(match[1], 10),
                position: match.index
            });
        }
        
        if (allMatches.length === 0) {
            // Нет HTTP заголовков — возможно это просто тело ответа
            return { success: true, status: 200, body: output, error: "" };
        }
        
        // Берём последний не-100 статус
        var lastStatus = 0;
        var lastPosition = 0;
        for (var i = allMatches.length - 1; i >= 0; i--) {
            if (allMatches[i].status !== 100) {
                lastStatus = allMatches[i].status;
                lastPosition = allMatches[i].position;
                break;
            }
        }
        
        // Если все статусы были 100, берём последний
        if (lastStatus === 0 && allMatches.length > 0) {
            lastStatus = allMatches[allMatches.length - 1].status;
            lastPosition = allMatches[allMatches.length - 1].position;
        }
        
        // Извлекаем тело — ищем пустую строку после заголовков
        var relevantPart = output.substring(lastPosition);
        var bodyStart = relevantPart.indexOf("\r\n\r\n");
        if (bodyStart === -1) bodyStart = relevantPart.indexOf("\n\n");
        
        var bodyPart = "";
        if (bodyStart !== -1) {
            bodyPart = relevantPart.substring(bodyStart).replace(/^\s+/, "");
        }
        
        return {
            success: lastStatus >= 200 && lastStatus < 300,
            status: lastStatus,
            body: bodyPart,
            error: lastStatus >= 400 ? "HTTP " + lastStatus : ""
        };
    }
    
// ================= @block PLUG:HTTP:003 @desc HTTP Request (CURL wrapper) =================

function httpRequest(method, url, headers, body) {
    var cmd = 'curl -s -i -k -L --connect-timeout 15 --max-time 30 -H "Expect:"';
    
    if (method === "POST") { cmd += ' -X POST'; }
    
    for (var key in headers) {
        if (headers.hasOwnProperty(key)) {
            var headerValue = String(headers[key]).replace(/"/g, '\\"').replace(/\r/g, '').replace(/\n/g, '');
            cmd += ' -H "' + key + ': ' + headerValue + '"';
        }
    }
    
    // Безопасная отправка тела POST-запроса через временный файл
    var tempPostFile = null;
    if (method === "POST" && body) {
        try {
            tempPostFile = new File(Folder.temp.absoluteURI + "/subtitler_post_" + new Date().getTime() + ".txt");
            tempPostFile.encoding = "UTF-8";
            tempPostFile.open("w");
            tempPostFile.write(body);
            tempPostFile.close();
            
            if ($.os.indexOf("Windows") !== -1) {
                // Windows CURL понимает прямые слеши, это спасает от проблем с экранированием кавычек
                var winPath = tempPostFile.fsName.replace(/\\/g, "/");
                cmd += ' --data-binary "@' + winPath + '"';
            } else {
                var macPath = tempPostFile.fsName.replace(/'/g, "'\\''");
                cmd += " --data-binary '@" + macPath + "'";
            }
        } catch(e) {
            // Если не удалось создать файл - отправка без тела
        }
    }

    var safeUrl = escapeUrl(url);
    cmd += ' "' + safeUrl + '"';
    
    var output = "";
    try {
        output = system.callSystem(cmd);
    } catch (e) {
        if (tempPostFile) try { tempPostFile.remove(); } catch(e2) {}
        return { success: false, status: 0, body: "", error: "CURL failed: " + e.toString() };
    }
    
    // Удаляем временный файл после выполнения
    if (tempPostFile) try { tempPostFile.remove(); } catch(e2) {}
    
    return parseHttpResponse(output);
}
    
// ================= @block PLUG:HTTP:004 @desc HTTP GET =================

     function httpGet(url, apiKey) {
        var headers = {};
        if (apiKey) { headers["X-API-Key"] = apiKey; }
        return httpRequest("GET", url, headers, null);
    }
    
    /**
     * Скачивание файла с правильной кодировкой UTF-8
     */
    
// ================= @block PLUG:HTTP:005 @desc Download File with UTF-8 =================

    function downloadFileUtf8(url, apiKey) {
        // Скачивание через temp file для правильной кодировки
        // Создаём временный файл
        var tempFile = new File(Folder.temp.absoluteURI + "/subtitler_download_" + new Date().getTime() + ".txt");
        var tempPath = tempFile.fsName;
        
        // CURL с сохранением в файл (сохраняет UTF-8 правильно)
        var cmd = 'curl -s -k -L --connect-timeout 15 --max-time 60 -H "Expect:"';
        
        if (apiKey) {
            var safeApiKey = String(apiKey).replace(/"/g, '\\"');
            cmd += ' -H "X-API-Key: ' + safeApiKey + '"';
        }
        
        // Экранируем путь для Windows
        var safeTempPath;
        if ($.os.indexOf("Windows") !== -1) {
            safeTempPath = tempPath.replace(/\\/g, "\\\\");
            cmd += ' -o "' + safeTempPath + '"';
        } else {
            cmd += " -o '" + tempPath.replace(/'/g, "'\\''") + "'";
        }
        
        cmd += ' "' + escapeUrl(url) + '"';
        
        try {
            system.callSystem(cmd);
        } catch (e) {
            return { success: false, content: "", error: "Download failed: " + e.toString() };
        }
        
        // Проверяем что файл создан
        if (!tempFile.exists) {
            return { success: false, content: "", error: "File not created" };
        }
        
        // Читаем файл с UTF-8 кодировкой
        tempFile.encoding = "UTF-8";
        tempFile.open("r");
        var content = tempFile.read();
        tempFile.close();
        
        // Удаляем временный файл
        try { tempFile.remove(); } catch(e) {}
        
        if (!content || content.length === 0) {
            return { success: false, content: "", error: "Empty file" };
        }
        
        return { success: true, content: content, error: "" };
    }
    
// ================= @block PLUG:HTTP:006 @desc HTTP POST Multipart (file upload) =================
        
    function httpPostMultipart(url, apiKey, filePath, format, targetLanguage) {
        // Увеличенный таймаут 600s для больших файлов
        var file = new File(filePath);
        if (!file.exists) {
            return { success: false, status: 0, body: "", error: "File not found: " + filePath };
        }
        
        // Увеличенный таймаут для загрузки файлов, отключаем Expect
        var cmd = 'curl -s -i -k -L --connect-timeout 15 --max-time 600 -H "Expect:"';
        
        // API ключ
        var safeApiKey = String(apiKey).replace(/"/g, '\\"');
        cmd += ' -H "X-API-Key: ' + safeApiKey + '"';
        
        // Путь к файлу
        var safePath;
        if ($.os.indexOf("Windows") !== -1) {
            safePath = filePath.replace(/\\/g, "/").replace(/"/g, '\\"');
            cmd += ' -F "file=@' + safePath + '"';
        } else {
            safePath = filePath.replace(/'/g, "'\\''");
            cmd += " -F 'file=@" + safePath + "'";
        }
        
        // Формат
        cmd += ' -F "format=' + format + '"';
        
        // Язык перевода
        if (targetLanguage && targetLanguage !== "orig" && targetLanguage !== "") {
            cmd += ' -F "target_language=' + targetLanguage + '"';
        }
        
        var safeUrl = escapeUrl(url);
        cmd += ' "' + safeUrl + '"';
        
        var output = "";
        try {
            output = system.callSystem(cmd);
        } catch (e) {
            return { success: false, status: 0, body: "", error: "CURL upload failed: " + e.toString() };
        }
        
        return parseHttpResponse(output);
    }
    
// ================= @block PLUG:HTTP:007 @desc Test Server Connection =================

    // === Функции обновления UI баланса ===
    function updateBalanceUI(newBalance) {
        if (newBalance !== null && newBalance !== undefined) {
            balanceText.text = newBalance + " cr";
        } else {
            balanceText.text = "N/A";
        }
    }

function testServerConnection(serverUrl, apiKey) {
    // Проверка api_test.php
    if (!serverUrl) { return { success: false, message: "Server URL is empty" }; }
    if (!apiKey) { return { success: false, message: "API Key is empty" }; }
    
    // Убираем trailing slash
    while (serverUrl.charAt(serverUrl.length - 1) === "/") {
        serverUrl = serverUrl.substring(0, serverUrl.length - 1);
    }
    
    var url = serverUrl + "/api_test.php";
    var result = httpGet(url, apiKey);
    
    if (!result.success) {
        // --- ИНТЕГРАЦИЯ: Сброс баланса при ошибке ---
        if (typeof updateBalanceUI === 'function') updateBalanceUI(null);
        // -------------------------------------------
        
        if (result.status === 401) { return { success: false, message: "Invalid API Key" }; }
        if (result.status === 404) { return { success: false, message: "api_test.php not found on server" }; }
        if (result.status === 0) { return { success: false, message: "Cannot connect to server" }; }
        return { success: false, message: result.error || "HTTP " + result.status };
    }
    
    // Пробуем распарсить JSON
    var bodyTrimmed = result.body.replace(/^\s+/, "").replace(/\s+$/, "");
    
    try {
        var json = JSON.parse(bodyTrimmed);
        if (json.status === "ok") {
            // --- ИНТЕГРАЦИЯ: Обновление блока Balance ---
            if (json.balance !== undefined && typeof updateBalanceUI === 'function') {
                updateBalanceUI(json.balance);
            } else if (typeof updateBalanceUI === 'function') {
                updateBalanceUI(null); // Если баланс не пришел - сбрасываем
            }
            // -------------------------------------------
            
            // Убрал баланс из строки сообщения, т.к. теперь он отображается в выделенном блоке UI
            return { success: true, message: "Connection OK" }; 
        }
        return { success: false, message: json.message || "Unknown error" };
    } catch (e) {
        // --- ИНТЕГРАЦИЯ: Сброс баланса при некорректном ответе ---
        if (typeof updateBalanceUI === 'function') updateBalanceUI(null);
        // --------------------------------------------------------
        
        // Если не JSON, но статус 200 — считаем что сервер работает
        if (result.status === 200) {
            return { success: true, message: "Server responding" };
        }
        return { success: false, message: "Invalid response format" };
    }
}

    // ================= PANEL SETUP =================

// ================= @block PLUG:UI:001 @desc Panel Setup =================

    var win = (thisObj instanceof Panel)
        ? thisObj
        : new Window("palette", SCRIPT_NAME + " v" + SCRIPT_VERSION, undefined, { resizeable: true });

    var scrollBar = win.add("scrollbar", [0, 0, 20, 200]);
    var content = win.add("group");
    // ... setup code ...
    content.orientation = "column";
    content.alignChildren = ["fill", "top"];
    content.spacing = 5;

    function updateLayout() {
        var winSize = win.size;
        var contentSize = content.preferredSize;
        scrollBar.location = [winSize.width - 20, 0];
        scrollBar.size = [20, winSize.height];
        var visibleHeight = winSize.height;
        var totalHeight = contentSize.height;
        if (totalHeight > visibleHeight) {
            scrollBar.enabled = true;
            scrollBar.maxvalue = totalHeight - visibleHeight + 20;
            scrollBar.value = Math.min(scrollBar.value, scrollBar.maxvalue);
        } else {
            scrollBar.enabled = false;
            scrollBar.value = 0;
        }
        content.location = [10, -scrollBar.value + 10];
        content.fixedSize = true;
        content.size = [winSize.width - 35, totalHeight];
    }

    win.onResizing = win.onResize = function () { this.layout.resize(); updateLayout(); };
    scrollBar.onChanging = function () { content.location.y = -this.value + 10; };

    function row(p) {
        var g = p.add("group");
        g.spacing = 6;
        g.alignChildren = "center";
        return g;
    }

    // ================= NAVIGATION TABS =================

// ================= @block PLUG:UI:002 @desc Navigation Tabs =================

    var navGroup = content.add("group");
    navGroup.orientation = "row";
    navGroup.alignChildren = ["fill", "top"];
    navGroup.spacing = 0;
    
    var tabImport = navGroup.add("button", undefined, "Import");
    var tabTTM = navGroup.add("button", undefined, "Create Subs");
    var tabAI = navGroup.add("button", undefined, "AI Transcription");
    var tabPrefs = navGroup.add("button", undefined, "Preferences");
    var tabAbout = navGroup.add("button", undefined, "About");
    
    tabImport.preferredSize.width = 55;
    tabTTM.preferredSize.width = 75;
    tabAI.preferredSize.width = 95;
    tabPrefs.preferredSize.width = 75;
    tabAbout.preferredSize.width = 50;

    content.add("panel", undefined, "");

    // ================= MAIN STACK CONTAINER =================
    var mainStack = content.add("group");
    mainStack.orientation = "stack";
    mainStack.alignment = ["fill", "top"];
    mainStack.alignChildren = ["fill", "top"];

    // ================= GROUP 1: IMPORT =================

// ================= @block PLUG:UI:003 @desc Group 1: Import Tab =================

    var groupImport = mainStack.add("group");
    groupImport.orientation = "column";
    groupImport.alignChildren = ["center", "top"];
    
    var hImport = groupImport.add("statictext", undefined, "Import Tool");
    hImport.alignment = "center";
    hImport.graphics.font = ScriptUI.newFont("Arial", "BOLD", 13);

    var importBtnSrt = groupImport.add("button", undefined, "Import SRT");
    importBtnSrt.preferredSize.width = 120;

    var importBtnVtt = groupImport.add("button", undefined, "Import VTT");
    importBtnVtt.preferredSize.width = 120;

    // ================= GROUP 2: PREFERENCES =================

// ================= @block PLUG:UI:004 @desc Group 2: Preferences Tab =================

    var groupPrefs = mainStack.add("group");
        // Text panel: Animation, Fade In, Duration, Bounce, Amplitude
        // Background panel: Enable, Padding, Roundness, Colors
        // Marker Colors sync
    groupPrefs.orientation = "column";
    groupPrefs.alignChildren = ["fill", "top"];
    groupPrefs.spacing = 8;
    groupPrefs.visible = false;

    var hPrefs = groupPrefs.add("statictext", undefined, "Preferences");
    hPrefs.alignment = "center";
    hPrefs.graphics.font = ScriptUI.newFont("Arial", "BOLD", 13);

    var textPanel = groupPrefs.add("panel", undefined, "Text");
    textPanel.alignChildren = ["fill", "top"];
    textPanel.margins = 10;
    textPanel.spacing = 6;

    var rAnim = row(textPanel);
    rAnim.add("statictext", undefined, "Animation:").preferredSize.width = 80;
    var animDropdown = rAnim.add("dropdownlist", undefined, ["Scale", "Opacity", "Simple"]);
    animDropdown.selection = 0;
    animDropdown.preferredSize.width = 100;

    var rFade = row(textPanel);
    rFade.add("statictext", undefined, "Fade In:").preferredSize.width = 80;
    var scaleInInput = rFade.add("edittext", undefined, "0.25");
    scaleInInput.characters = 5;
    rFade.add("statictext", undefined, "sec");

    var rDur = row(textPanel);
    rDur.add("statictext", undefined, "Duration:").preferredSize.width = 80;
    var durationInput = rDur.add("edittext", undefined, "");
    durationInput.characters = 5;
    var autoBtn = rDur.add("button", undefined, "Auto");
    autoBtn.preferredSize.width = 40;

    var rBounce = row(textPanel);
    rBounce.add("statictext", undefined, "Bounce:").preferredSize.width = 80;
    var bounceCountDropdown = rBounce.add("dropdownlist", undefined, ["0", "1", "2", "3"]);
    bounceCountDropdown.selection = 2;
    bounceCountDropdown.preferredSize.width = 50;
    var btnUp = rBounce.add("button", undefined, "↑");
    btnUp.preferredSize.width = 25;
    var btnDown = rBounce.add("button", undefined, "↓");
    btnDown.preferredSize.width = 25;

    var rAmp = row(textPanel);
    rAmp.add("statictext", undefined, "Amplitude:").preferredSize.width = 80;
    var bounceAmpInput = rAmp.add("edittext", undefined, "20");
    bounceAmpInput.characters = 5;

    var rPunct = row(textPanel);
    var btnRemovePunct = rPunct.add("button", undefined, "Remove Punctuation");
    btnRemovePunct.preferredSize.width = 180;
    btnRemovePunct.helpTip = "Remove all periods and commas from selected subtitle layer markers";
    
    btnRemovePunct.onClick = function() {
        var comp = app.project.activeItem;
        if (!comp || !(comp instanceof CompItem)) {
            alert("Open a Composition first.");
            return;
        }
        
        var selectedLayers = comp.selectedLayers;
        if (!selectedLayers || selectedLayers.length === 0) {
            alert("Select a subtitle layer in the Composition.");
            return;
        }
        
        var layer = selectedLayers[0];
        var markers = layer.property("Marker");
        
        if (!markers || markers.numKeys === 0) {
            alert("Selected layer has no markers.");
            return;
        }
        
        app.beginUndoGroup("Remove Punctuation");
        
        var count = 0;
        for (var i = 1; i <= markers.numKeys; i++) {
            var mv = markers.keyValue(i);
            var original = mv.comment;
            // Remove periods and commas, preserve ||| DUR= and other metadata
            var parts = original.split(" ||| ");
            if (parts.length > 0) {
                parts[0] = parts[0].replace(/[.,]/g, "");
            }
            mv.comment = parts.join(" ||| ");
            markers.setValueAtKey(i, mv);
            if (mv.comment !== original) count++;
        }
        
        app.endUndoGroup();
        
        mainStatus.text = "Removed punctuation from " + count + " marker(s)";
    };

    // Snap Markers — чекбокс Auto-snap
    var rSnap = row(textPanel);
    var cbAutoSnap = rSnap.add("checkbox", undefined, "Auto-snap markers on import");
    cbAutoSnap.value        = settings.autoSnap || false;
    cbAutoSnap.helpTip      = "Automatically snap marker durations on SRT/VTT import";
    cbAutoSnap.preferredSize.width = 220;

    cbAutoSnap.onClick = function() {
        settings.autoSnap = cbAutoSnap.value;
        saveSettings();
    };

    // Snap Markers — строка с порогом и кнопкой
    var rSnapBtn = row(textPanel);
    rSnapBtn.add("statictext", undefined, "Threshold:").preferredSize.width = 60;
    var snapThresholdInput = rSnapBtn.add("edittext", undefined, String(settings.snapThreshold || 5));
    snapThresholdInput.characters    = 3;
    snapThresholdInput.helpTip       = "Maximum gap in frames to snap";

    rSnapBtn.add("statictext", undefined, "fr");

    var btnSnap = rSnapBtn.add("button", undefined, "Snap Markers");
    btnSnap.preferredSize.width = 110;
    btnSnap.helpTip             = "Snap marker durations to next marker start if gap < threshold";

    btnSnap.onClick = function() {
        var comp = app.project.activeItem;
        if (!comp || !(comp instanceof CompItem)) {
            alert("Open a Composition first.");
            return;
        }

        var selectedLayers = comp.selectedLayers;
        if (!selectedLayers || selectedLayers.length === 0) {
            alert("Select a subtitle layer in the Composition.");
            return;
        }

        var threshold = parseInt(snapThresholdInput.text, 10);
        if (isNaN(threshold) || threshold < 1) {
            alert("Enter a valid threshold (frames).");
            return;
        }

        // Сохраняем порог в настройках
        settings.snapThreshold = threshold;
        saveSettings();

        var layer   = selectedLayers[0];
        var markers = layer.property("Marker");

        if (!markers || markers.numKeys === 0) {
            alert("Selected layer has no markers.");
            return;
        }

        var snapped = snapMarkers(layer, threshold);
        mainStatus.text = "Snapped " + snapped + " marker(s) (threshold: " + threshold + " frames)";
    };
    
    var bgPanel = groupPrefs.add("panel", undefined, "Background");
    bgPanel.alignChildren = ["fill", "top"];
    bgPanel.margins = 10;
    bgPanel.spacing = 6;

    var rBgEnable = row(bgPanel);
    var bgEnableCheck = rBgEnable.add("checkbox", undefined, "Enable Background");
    bgEnableCheck.value = true;

    var rBgPadding = row(bgPanel);
    rBgPadding.add("statictext", undefined, "Padding:").preferredSize.width = 100;
    var bgPaddingInput = rBgPadding.add("edittext", undefined, "0");
    bgPaddingInput.characters = 5;

    var rBgRound = row(bgPanel);
    rBgRound.add("statictext", undefined, "Roundness:").preferredSize.width = 100;
    var bgRoundInput = rBgRound.add("edittext", undefined, "0");
    bgRoundInput.characters = 5;

    var rBgColor = row(bgPanel);
    rBgColor.add("statictext", undefined, "BG Color:").preferredSize.width = 100;
    var bgColorBtn = rBgColor.add("button", undefined, "");
    bgColorBtn.preferredSize = [50, 20];
    
    var rTextColor = row(bgPanel);
    rTextColor.add("statictext", undefined, "Text Color:").preferredSize.width = 100;
    var textColorBtn = rTextColor.add("button", undefined, "");
    textColorBtn.preferredSize = [50, 20];
    
    var bgColor = [0.1, 0.1, 0.1];
    var textColor = [1, 1, 1];
    
    function updateBgColorButton() {
        bgColorBtn.onDraw = function() {
            var g = this.graphics;
            var b = g.newBrush(g.BrushType.SOLID_COLOR, bgColor);
            g.newPath(); g.rectPath(0, 0, this.size.width, this.size.height); g.fillPath(b);
        };
        bgColorBtn.notify("onDraw");
    }
    updateBgColorButton();
    
    function updateTextColorButton() {
        textColorBtn.onDraw = function() {
            var g = this.graphics;
            var b = g.newBrush(g.BrushType.SOLID_COLOR, textColor);
            g.newPath(); g.rectPath(0, 0, this.size.width, this.size.height); g.fillPath(b);
            var p = g.newPen(g.PenType.SOLID_COLOR, [0.3, 0.3, 0.3], 1);
            g.strokePath(p);
        };
        textColorBtn.notify("onDraw");
    }
    updateTextColorButton();
    
    bgColorBtn.onClick = function() {
        var currentHex = Math.round(bgColor[0] * 255) << 16 | Math.round(bgColor[1] * 255) << 8 | Math.round(bgColor[2] * 255);
        var result = $.colorPicker(currentHex);
        if (result !== -1) {
            bgColor = [(result >> 16 & 0xFF) / 255, (result >> 8 & 0xFF) / 255, (result & 0xFF) / 255];
            updateBgColorButton();
            updateBackgroundEffectsOnSelectedLayer();
        }
    };
    
    textColorBtn.onClick = function() {
        var currentHex = Math.round(textColor[0] * 255) << 16 | Math.round(textColor[1] * 255) << 8 | Math.round(textColor[2] * 255);
        var result = $.colorPicker(currentHex);
        if (result !== -1) {
            textColor = [(result >> 16 & 0xFF) / 255, (result >> 8 & 0xFF) / 255, (result & 0xFF) / 255];
            updateTextColorButton();
            updateBackgroundEffectsOnSelectedLayer();
        }
    };

    var syncPanel = groupPrefs.add("panel", undefined, "Marker Colors");
    syncPanel.alignChildren = ["fill", "top"];
    syncPanel.margins = 10;
    var rSync = row(syncPanel);
    var syncBtn = rSync.add("button", undefined, "Sync with Text Color");

    // ================= GROUP 3: TEXT TO MARKERS =================

 // ================= @block PLUG:UI:005 @desc Group 3: Text to Markers Tab =================

    var groupTTM = mainStack.add("group");
        // Words per marker dropdown
        // Text input multiline
        // Generate button
    groupTTM.orientation = "column";
    groupTTM.alignChildren = ["fill", "top"];
    groupTTM.visible = false;

    var hTTM = groupTTM.add("statictext", undefined, "Text to Markers Tool");
    hTTM.alignment = "center";
    hTTM.graphics.font = ScriptUI.newFont("Arial", "BOLD", 13);
    
    var ttmRow1 = row(groupTTM);
    ttmRow1.add("statictext", undefined, "Words per marker:");
    var wordsDropdown = ttmRow1.add("dropdownlist", undefined, ["1", "2", "3", "4", "5", "6"]);
    wordsDropdown.selection = 0;
    wordsDropdown.preferredSize = [50, 25];

    var textInput = groupTTM.add("edittext", undefined, "", {multiline: true, scrolling: true});
    textInput.alignment = ["fill", "top"];
    textInput.minimumSize.height = 150;

    var ttmCreateBtn = groupTTM.add("button", undefined, "Generate Subtitles");
    ttmCreateBtn.alignment = ["center", "top"];
    ttmCreateBtn.preferredSize = [140, 25];

    // ================= GROUP 4: AI TRANSCRIPTION =================

// ================= @block PLUG:UI:006 @desc Group 4: AI Transcription Tab =================


    var groupAI = mainStack.add("group");
        // Connection panel: Status, Mode, Server, Settings button
        // Generation Settings: Format dropdown, Language dropdown
        // Actions: Select File button, Status text, Cancel, Import Result    
    groupAI.orientation = "column";
    groupAI.alignChildren = ["fill", "top"];
    groupAI.visible = false;
    
    var hAI = groupAI.add("statictext", undefined, "AI Transcription Tool");
    hAI.alignment = "center";
    hAI.graphics.font = ScriptUI.newFont("Arial", "BOLD", 13);

    // ================= @block PLUG:UI:009 @desc Notice for unauthenticated users =================
    var noticeText = groupAI.add("statictext", undefined, 
        "API and Cloud Sync require a registered account at https://subtitler.qzz.io.\nSelf-hosted mode (localhost) is free with no limits.", 
        {multiline: true});
    noticeText.alignment = ["fill", "top"];
    noticeText.graphics.font = ScriptUI.newFont("Arial", "ITALIC", 10);
    noticeText.preferredSize.height = 30; 
    //end

    var connectionPanel = groupAI.add("panel", undefined, "Connection");
    connectionPanel.alignChildren = ["fill", "top"];
    connectionPanel.margins = 10;
    
    var connRow = row(connectionPanel);
    connRow.add("statictext", undefined, "Status:");
    var connectionStatus = connRow.add("statictext", undefined, "Not configured");
    connectionStatus.preferredSize.width = 120;
    
    var modeRow = row(connectionPanel);
    modeRow.add("statictext", undefined, "Mode:");
    var modeDisplay = modeRow.add("statictext", undefined, "—");
    modeDisplay.preferredSize.width = 120;
    
    var serverRow = row(connectionPanel);
    serverRow.add("statictext", undefined, "Server:");
    var serverDisplay = serverRow.add("statictext", undefined, "—");
    serverDisplay.preferredSize.width = 120;
    var btnSettings = serverRow.add("button", undefined, "Settings");
    btnSettings.preferredSize.width = 70;

    // Блок баланса (Пассивный)
    var balanceGrp = groupAI.add("group"); // ИСПРАВЛЕНО: groupAI вместо aiTab
    balanceGrp.alignment = ["fill", "top"];
    balanceGrp.add("statictext", undefined, "Balance:");
    var balanceText = balanceGrp.add("statictext", undefined, "N/A"); 
    balanceText.graphics.foregroundColor = balanceText.graphics.newPen(balanceText.graphics.PenType.SOLID_COLOR, [0.2, 0.6, 0.2], 1); // Зеленый цвет
    balanceText.alignment = ["fill", "top"];
    
    var genPanel = groupAI.add("panel", undefined, "Generation Settings");
    genPanel.alignChildren = ["fill", "top"];
    genPanel.margins = 10;
    
    var fmtRow = row(genPanel);
    fmtRow.add("statictext", undefined, "Format:");
    var formatDropdown = fmtRow.add("dropdownlist", undefined, [
        "1 Word (Karaoke)",
        "Short (2-3 words)", 
        "Standard (5-7 words)",
        "Long (up to 10 words)"
    ]);
    formatDropdown.selection = 2;
    formatDropdown.preferredSize.width = 140;
    
    var langRow = row(genPanel);
    langRow.add("statictext", undefined, "Translate to:");
    var langNames = [];
    for (var li = 0; li < TRANSLATION_LANGUAGES.length; li++) {
        langNames.push(TRANSLATION_LANGUAGES[li].flag + " " + TRANSLATION_LANGUAGES[li].name);
    }
    var langDropdown = langRow.add("dropdownlist", undefined, langNames);
    langDropdown.selection = 0;
    langDropdown.preferredSize.width = 160;
    
    var langHint = genPanel.add("statictext", undefined, "Translation: 1 token per 3 min");
    langHint.graphics.font = ScriptUI.newFont("Arial", "Regular", 10);
    
    var actionPanel = groupAI.add("panel", undefined, "Actions");
    actionPanel.alignChildren = ["fill", "top"];
    actionPanel.margins = 10;
    
    var btnSelectFile = actionPanel.add("button", undefined, "Select File & Transcribe");
    btnSelectFile.enabled = false;

    var btnUseActive = actionPanel.add("button", undefined, "Use Active Item");
    
    var svcStatusText = actionPanel.add("statictext", undefined, "");
    svcStatusText.alignment = ["center", "top"];
    svcStatusText.preferredSize = [200, 18];

    var timeText = actionPanel.add("statictext", undefined, "");
    timeText.alignment = ["center", "top"];
    timeText.preferredSize = [200, 18];
    
    var btnServiceImport = actionPanel.add("button", undefined, "Import Result");
    btnServiceImport.enabled = false;

    // ================= GROUP 5: ABOUT =================

// ================= @block PLUG:UI:007 @desc Group 5: About Tab =================

    var groupAbout = mainStack.add("group");
        // Logo, Version, Description
        // Links: Developer, Website, Donate
        // Copyright
    groupAbout.orientation = "column";
    groupAbout.alignChildren = ["center", "top"];
    groupAbout.spacing = 15;
    groupAbout.visible = false;

    var hAbout = groupAbout.add("statictext", undefined, "About");
    hAbout.alignment = "center";
    hAbout.graphics.font = ScriptUI.newFont("Arial", "BOLD", 13);

    var aboutPanel = groupAbout.add("panel", undefined, "");
    aboutPanel.alignChildren = ["center", "top"];
    aboutPanel.margins = 20;
    aboutPanel.spacing = 10;
    aboutPanel.preferredSize.width = 280;

    var logoText = aboutPanel.add("statictext", undefined, "🎬 " + SCRIPT_NAME);
    logoText.graphics.font = ScriptUI.newFont("Arial", "BOLD", 16);

    var versionText = aboutPanel.add("statictext", undefined, "Version " + SCRIPT_VERSION);
    versionText.graphics.font = ScriptUI.newFont("Arial", "Regular", 12);

    var versionNameText = aboutPanel.add("statictext", undefined, '"' + VERSION_NAME + '"');
    versionNameText.graphics.font = ScriptUI.newFont("Arial", "ITALIC", 11);

    aboutPanel.add("panel", undefined, "").preferredSize.height = 1;

    var descText = aboutPanel.add("statictext", undefined, 
        "AI-powered subtitle generation\nfor Adobe After Effects", 
        {multiline: true}
    );
    descText.graphics.font = ScriptUI.newFont("Arial", "Regular", 11);
    descText.preferredSize.width = 240;
    descText.justify = "center";

    aboutPanel.add("panel", undefined, "").preferredSize.height = 1;

    var linksPanel = groupAbout.add("panel", undefined, "Links");
    linksPanel.alignChildren = ["fill", "top"];
    linksPanel.margins = 10;
    linksPanel.preferredSize.width = 280;

    var developerRow = row(linksPanel);
    developerRow.add("statictext", undefined, "Developer:");
    var developerLink = developerRow.add("statictext", undefined, "helixgem.site");
    developerLink.graphics.foregroundColor = developerLink.graphics.newPen(
        developerLink.graphics.PenType.SOLID_COLOR, [0.2, 0.4, 0.8], 1
    );

    var websiteRow = row(linksPanel);
    websiteRow.add("statictext", undefined, "Website:");
    var websiteLink = websiteRow.add("statictext", undefined, "https://subtitler.qzz.io");
    websiteLink.graphics.foregroundColor = websiteLink.graphics.newPen(
        websiteLink.graphics.PenType.SOLID_COLOR, [0.2, 0.4, 0.8], 1
    );

    var docsRow = row(linksPanel);
    docsRow.add("statictext", undefined, "Donate ❤️ :");
    var docsLink = docsRow.add("statictext", undefined, "Help Us →");
    docsLink.graphics.foregroundColor = docsLink.graphics.newPen(
        docsLink.graphics.PenType.SOLID_COLOR, [0.2, 0.4, 0.8], 1
    );

    // Блок Feedback
    var feedbackPanel = groupAbout.add("panel", undefined, "Give me feedback"); // ИСПРАВЛЕНО: groupAbout вместо aboutTab
    feedbackPanel.alignment = ["fill", "top"];
    feedbackPanel.alignChildren = ["fill", "top"];

    var feedbackInput = feedbackPanel.add("edittext", undefined, "", {multiline: true});
    feedbackInput.preferredSize.height = 80;

    var feedbackBtnGrp = feedbackPanel.add("group");
    feedbackBtnGrp.alignment = ["fill", "top"];
    var feedbackSubmitBtn = feedbackBtnGrp.add("button", undefined, "Submit");
    var feedbackStatusText = feedbackBtnGrp.add("statictext", undefined, "");

    // Обработчики кликов по ссылкам
    developerLink.addEventListener("click", function() {
        try {
            if ($.os.indexOf("Windows") !== -1) {
                system.callSystem('cmd /c start "" "' + DEV_URL + '"');
            } else {
                system.callSystem('open "' + DEV_URL + '"');
            }
        } catch(e) {
            alert("Open in browser:\n" + DEV_URL);
        }
    });

    websiteLink.addEventListener("click", function() {
        try {
            if ($.os.indexOf("Windows") !== -1) {
                system.callSystem('cmd /c start "" "' + SCRIPT_URL + '"');
            } else {
                system.callSystem('open "' + SCRIPT_URL + '"');
            }
        } catch(e) {
            alert("Open in browser:\n" + SCRIPT_URL);
        }
    });

    docsLink.addEventListener("click", function() {
        try {
            if ($.os.indexOf("Windows") !== -1) {
                system.callSystem('cmd /c start "" "' + DOCS_URL + '"');
            } else {
                system.callSystem('open "' + DOCS_URL + '"');
            }
        } catch(e) {
            alert("Open in browser:\n" + DOCS_URL);
        }
    });

    var copyrightText = groupAbout.add("statictext", undefined, "© 2026 Subtitler Online");
    copyrightText.graphics.font = ScriptUI.newFont("Arial", "Regular", 10);

    // ================= TABS LOGIC =================

// ================= @block PLUG:UI:008 @desc Tabs Logic =================

    function switchTab(index) {
        groupImport.visible = (index === 0);
        groupTTM.visible = (index === 1);
        groupAI.visible = (index === 2);
        groupPrefs.visible = (index === 3);
        groupAbout.visible = (index === 4);
        win.layout.layout(true);
        updateLayout();
    }

    tabImport.onClick = function() { switchTab(0); };
    tabTTM.onClick = function() { switchTab(1); };
    tabAI.onClick = function() { switchTab(2); };
    tabPrefs.onClick = function() { switchTab(3); };
    tabAbout.onClick = function() { switchTab(4); };

    var mainStatus = content.add("statictext", undefined, "Made by Helixgem | v" + SCRIPT_VERSION);
    mainStatus.alignment = ["fill", "top"];

    // ================= LOGIC & HELPERS =================
    var bounceMode = 0;
    loadSettings();

    function f(v) {
        var val = parseFloat(String(v).replace(",", "."));
        return isNaN(val) ? 0 : val;
    }

    function trim(s) { return (s || "").replace(/^\s+|\s+$/g, ""); }

    function updateUI() {
        var scaleMode = animDropdown.selection.index === 0;
        var simpleMode = animDropdown.selection.index === 2;
        rFade.visible = !simpleMode;
        rBounce.visible = scaleMode;
        rAmp.visible = scaleMode;
        var bgEnabled = bgEnableCheck.value;
        rBgPadding.enabled = bgEnabled;
        rBgRound.enabled = bgEnabled;
        rBgColor.enabled = bgEnabled;
        rTextColor.enabled = bgEnabled;
        win.layout.layout(true);
        updateLayout();
    }

    function liveUpdate() {
        updateUI();
        applyExpressionsToSelectedLayer();
    }

    function getSelectedTextLayer() {
        var comp = app.project.activeItem;
        if (!(comp instanceof CompItem)) return null;
        var sel = comp.selectedLayers;
        if (sel.length === 0) return null;
        if (sel[0] && sel[0].property("ADBE Text Properties")) return sel[0];
        return null;
    }

    // ================= EXPRESSIONS =================

// ================= @block PLUG:EXPR:003 @desc Color Animator =================

    function recreateColorAnimator(layer) {
            // ADBE Text Animator для цвета текста
        var animators = layer.Text.Animators;
        var animName = "Label Color Control"; 
        for (var i = animators.numProperties; i >= 1; i--) {
            if (animators.property(i).name === animName) animators.property(i).remove();
        }
        var animator = animators.addProperty("ADBE Text Animator");
        animator.name = animName;
        var propsGroup = animator.property("ADBE Text Animator Properties");
        var fillProp = propsGroup.addProperty("ADBE Text Fill Color");
        fillProp.setValue([1, 1, 1]); 
        return fillProp;
    }

    function syncMarkerColors() {
        var comp = app.project.activeItem;
        if (!comp) return 0;
        var sel = comp.selectedLayers;
        var count = 0;
        for (var i = 0; i < sel.length; i++) {
            var mProp = sel[i].property("Marker");
            if (mProp) {
                for (var k = 1; k <= mProp.numKeys; k++) {
                    var mv = mProp.keyValue(k);
                    if (mv.url !== mv.label.toString()) {
                        mv.url = mv.label.toString();
                        mProp.setValueAtKey(k, mv);
                        count++;
                    }
                }
            }
        }
        return count;
    }

// ================= @block PLUG:EXPR:001 @desc Apply Expressions to Layer =================

    function applyExpressions(layer) {
            // sourceText expression — показ текста из маркера
            // scale/opacity expression — анимация появления
            // color expression — цвет из label
        if (!layer) return;
        var sIn = Math.max(0.01, f(scaleInInput.text) || 0.25);
        var bCnt = parseInt(bounceCountDropdown.selection.text) || 0;
        var amp = f(bounceAmpInput.text) || 20;
        var anim = animDropdown.selection.index;

        try {
            layer.transform.opacity.expression = "";
            layer.transform.scale.expression = "";

            if (anim === 2) { 
                layer.transform.opacity.expression =
                    'm=thisLayer.marker;o=0;if(m.numKeys>0){n=m.nearestKey(time).index;if(m.key(n).time>time)n--;if(n>0){k=m.key(n);if(time>=k.time&&time<(k.time+k.duration)){o=100;}}}o;';
            } else if (anim === 0) {
                layer.transform.scale.expression =
                    'm=thisLayer.marker;scaleIn=' + sIn + ';amp=' + amp + ';bounceCount=' + bCnt + ';mode=' + bounceMode + ';res=[100,100];if(m.numKeys>0){n=m.nearestKey(time).index;if(m.key(n).time>time)n--;if(n>0){mt=m.key(n).time-thisLayer.inPoint;t=time-thisLayer.inPoint-mt;if(t<=scaleIn){p=t/scaleIn;s=' + (bounceMode === 0 ? '0+(100-0)*p' : '150+(100-150)*p') + ';res=[s,s];}else{tb=t-scaleIn;td=bounceCount*2*scaleIn;if(td<=0.001)td=0.001;if(tb<td&&bounceCount>0){osc=Math.sin((tb/(2*scaleIn))*Math.PI*2);decay=1-tb/td;s=100+osc*amp*decay;res=[s,s];}else{res=[100,100];}}}}res;';
            } else {
                layer.transform.opacity.expression =
                    'm=thisLayer.marker;lt=time-thisLayer.inPoint;appear=' + sIn + ';o=0;if(m.numKeys>0){n=m.nearestKey(time).index;if(m.key(n).time>time)n--;if(n>0){mt=m.key(n).time-thisLayer.inPoint;t=lt-mt;if(t<=appear){o=ease(t,0,appear,0,100);}else{o=100;}}}o;';
            }
        } catch(e) {}

        try {
            layer.text.sourceText.expression =
                'm=thisLayer.marker;r="";if(m.numKeys>0){n=m.nearestKey(time).index;if(m.key(n).time>time)n--;if(n>0){k=m.key(n);if(time>=k.time&&time<(k.time+k.duration)){if(k.comment.indexOf(" ||| ")!==-1)r=k.comment.split(" ||| ")[0];else r=k.comment;}}}r;';
        } catch(e) {}

        try {
            var animators = layer.Text.Animators;
            var animName = "Label Color Control";
            var animator, fillProp;
            for (var i = 1; i <= animators.numProperties; i++) {
                if (animators.property(i).name === animName) { animator = animators.property(i); break; }
            }
            if (!animator) fillProp = recreateColorAnimator(layer);
            else fillProp = animator.property("ADBE Text Animator Properties").property("ADBE Text Fill Color");
            if (fillProp) {
                fillProp.expression = 'var m=thisLayer.marker;var c=[1,1,1,1];var lc=[[1,1,1],[0.71,0.22,0.22],[0.89,0.85,0.3],[0.66,0.8,0.78],[0.9,0.74,0.79],[0.66,0.66,0.79],[0.91,0.76,0.62],[0.7,0.78,0.7],[0.4,0.49,0.88],[0.29,0.64,0.3],[0.56,0.17,0.6],[0.91,0.53,0.02],[0.56,0.31,0.12],[0.96,0.43,0.84],[0.12,0.64,0.66],[0.66,0.59,0.47],[0.12,0.25,0.12]];if(m.numKeys>0){var n=m.nearestKey(time).index;if(m.key(n).time>time)n--;if(n>0){var k=m.key(n);if(time>=k.time&&time<(k.time+k.duration)){try{var u=k.url;var val=(u&&u!=="")?parseInt(u):0;if(!isNaN(val)&&val>=0&&val<lc.length){var rgb=lc[val];c=[rgb[0],rgb[1],rgb[2],1];}}catch(e){}}}}c;';
            }
        } catch(e) {}
    }

    function applyExpressionsToSelectedLayer() {
        var layer = getSelectedTextLayer();
        if (layer) applyExpressions(layer);
    }

    // ================= BACKGROUND EFFECTS =================
    
    function removeBackgroundEffects(layer) {
        var effects = layer.property("ADBE Effect Parade");
        for (var i = effects.numProperties; i >= 1; i--) {
            if (effects.property(i).name.indexOf("BG_") === 0) effects.property(i).remove();
        }
    }
    
// ================= @block PLUG:EXPR:002 @desc Background Effects =================

    function applyBackgroundEffects(layer) {
        // BG_Simple Choker, BG_Minimax, BG_Tint, BG_Simple Choker 2
        if (!bgEnableCheck.value) return;
        var padding = f(bgPaddingInput.text);
        var roundness = f(bgRoundInput.text);
        var effects = layer.property("ADBE Effect Parade");
        removeBackgroundEffects(layer);
        try {
            var c1 = effects.addProperty("ADBE Simple Choker"); c1.name = "BG_Simple Choker";
            var vp = c1.property("View"); if (vp) vp.setValue(2);
            var mm = effects.addProperty("ADBE Minimax"); mm.name = "BG_Minimax";
            var op = mm.property("Operation"); if (op) op.setValue(2);
            var rp = mm.property("Radius"); if (rp) rp.setValue(padding);
            var cp = mm.property("Channel"); if (cp) cp.setValue(6);
            var ti = effects.addProperty("ADBE Tint"); ti.name = "BG_Tint";
            var mb = ti.property("Map Black To"); if (mb) mb.setValue(bgColor);
            var mw = ti.property("Map White To"); if (mw) mw.setValue(textColor);
            var am = ti.property("Amount to Tint"); if (am) am.setValue(100);
            var c2 = effects.addProperty("ADBE Simple Choker"); c2.name = "BG_Simple Choker 2";
            var ch = c2.property("Choke Matte"); if (ch) ch.setValue(roundness);
        } catch(e) {}
    }
    
    function updateBackgroundEffectsOnSelectedLayer() {                
                // Live update при изменении настроек
        var layer = getSelectedTextLayer();
        if (!layer) return;
        app.beginUndoGroup("Update BG");
        var effects = layer.property("ADBE Effect Parade");
        var hasEffects = false;
        for (var i = 1; i <= effects.numProperties; i++) {
            if (effects.property(i).name.indexOf("BG_") === 0) { hasEffects = true; break; }
        }
        if (!bgEnableCheck.value) {
            for (var i = 1; i <= effects.numProperties; i++) {
                if (effects.property(i).name.indexOf("BG_") === 0) effects.property(i).enabled = false;
            }
        } else if (!hasEffects) {
            applyBackgroundEffects(layer);
        } else {
            for (var i = 1; i <= effects.numProperties; i++) {
                var eff = effects.property(i);
                if (eff.name === "BG_Minimax") { eff.enabled = true; var r = eff.property("Radius"); if (r) r.setValue(f(bgPaddingInput.text)); }
                else if (eff.name === "BG_Tint") { eff.enabled = true; var mb = eff.property("Map Black To"); if (mb) mb.setValue(bgColor); var mw = eff.property("Map White To"); if (mw) mw.setValue(textColor); }
                else if (eff.name === "BG_Simple Choker 2") { eff.enabled = true; var ch = eff.property("Choke Matte"); if (ch) ch.setValue(f(bgRoundInput.text)); }
                else if (eff.name.indexOf("BG_") === 0) eff.enabled = true;
            }
        }
        app.endUndoGroup();
    }

    // ================= PARSERS =================
// ================= @block PLUG:PARSE:001 @desc Parse SRT =================
    
    function parseSrt(txt) {
        var lines = txt.split(/\r\n|\n|\r/);
        var res = [], cur = null, buf = [];
        
        function pushCur() {
            if (cur && buf.length > 0) {
                cur.text = buf.join(" ");
                cur.duration = cur.end - cur.start;
                if (cur.duration > 0 && cur.text.length > 0) {
                    res.push(cur);
                }
            }
            cur = null;
            buf = [];
        }
        
        var STATE_SEEK_INDEX = 0;
        var STATE_SEEK_TC    = 1;
        var STATE_SEEK_TEXT  = 2;
        var state = STATE_SEEK_INDEX;
        
        for (var i = 0; i < lines.length; i++) {
            var line = trim(lines[i]);
            
            if (state === STATE_SEEK_INDEX) {
                if (/^\d+$/.test(line)) {
                    pushCur();
                    cur = { start: 0, end: 0, text: "", duration: 0 };
                    state = STATE_SEEK_TC;
                }
                // skip blank lines and non-index lines
                continue;
            }
            
            if (state === STATE_SEEK_TC) {
                var m = line.match(/(\d\d):(\d\d):(\d\d)[,.](\d+)\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d+)/);
                if (m) {
                    cur.start = +m[1]*3600 + +m[2]*60 + +m[3] + +m[4]/1000;
                    cur.end   = +m[5]*3600 + +m[6]*60 + +m[7] + +m[8]/1000;
                    state = STATE_SEEK_TEXT;
                } else if (line === "") {
                    // malformed — reset
                    cur = null; buf = [];
                    state = STATE_SEEK_INDEX;
                }
                continue;
            }
            
            if (state === STATE_SEEK_TEXT) {
                if (line === "") {
                    pushCur();
                    state = STATE_SEEK_INDEX;
                } else {
                    buf.push(line);
                }
                continue;
            }
        }
        
        // EOF without trailing blank line — flush last entry
        pushCur();
        
        return res;
    }
    
// ================= @block PLUG:PARSE:002 @desc Parse VTT =================    

    function parseVtt(txt) {
            // Парсинг: WEBVTT header → таймкод → текст
            // Удаление тегов <>, {}
        var lines = txt.split(/\r\n|\n|\r/);
        var res = [], cur = null, buf = [], headerPassed = false;
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i], tl = trim(line);
            if (!headerPassed) {
                if (tl.indexOf("WEBVTT") === 0) { headerPassed = true; continue; }
                if (tl === "") continue;
                if (tl.indexOf("-->") !== -1) headerPassed = true; else continue;
            }
            if (tl === "") {
                if (cur && buf.length > 0) { cur.text = buf.join(" "); cur.duration = cur.end - cur.start; res.push(cur); }
                cur = null; buf = []; continue;
            }
            if (tl.indexOf("NOTE") === 0 || tl.indexOf("STYLE") === 0) continue;
            var tm = tl.match(/(\d{1,2}):?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{1,2}):?(\d{2}):(\d{2})\.(\d{3})/);
            if (tm) {
                if (cur && buf.length > 0) { cur.text = buf.join(" "); cur.duration = cur.end - cur.start; res.push(cur); buf = []; }
                cur = { start: 0, end: 0, text: "", duration: 0 };
                cur.start = parseInt(tm[1],10)*3600 + parseInt(tm[2],10)*60 + parseInt(tm[3],10) + parseInt(tm[4],10)/1000;
                cur.end = parseInt(tm[5],10)*3600 + parseInt(tm[6],10)*60 + parseInt(tm[7],10) + parseInt(tm[8],10)/1000;
                continue;
            }
            if (!cur && /^\d+$/.test(tl)) { cur = { start: 0, end: 0, text: "", duration: 0 }; continue; }
            if (cur) { var ct = tl.replace(/<[^>]+>/g, "").replace(/\{[^}]+\}/g, ""); if (ct) buf.push(ct); }
        }
        if (cur && buf.length > 0) { cur.text = buf.join(" "); cur.duration = cur.end - cur.start; res.push(cur); }
        return res;
    }

    // ================= GENERATORS =================
// ================= @block PLUG:GEN:001 @desc Create Layer from SRT =================

    function createFromSRT(subs, layerName) {
            // addText → markers → expressions → background effects
        var comp = app.project.activeItem;
        if (!(comp instanceof CompItem)) return;
        app.beginUndoGroup("Import SRT");
        var layer = comp.layers.addText("");
        if (layerName) layer.name = layerName;
        var m = layer.property("Marker");
        while (m.numKeys) m.removeKey(1);
        var maxTime = 0;
        for (var i = 0; i < subs.length; i++) {
            var mv = new MarkerValue(subs[i].text + " ||| DUR=" + subs[i].duration.toFixed(3));
            mv.duration = subs[i].duration; mv.url = "0"; mv.label = 0;
            m.setValueAtTime(subs[i].start, mv);
            if (subs[i].end > maxTime) maxTime = subs[i].end;
        }
        if (comp.duration < maxTime) comp.duration = maxTime + 0.5;
        // Add extra margin so last marker is fully visible
        var layerEnd = maxTime + Math.max(subs[subs.length-1].duration, 0.5);
        if (comp.duration < layerEnd) comp.duration = layerEnd;
        layer.inPoint = subs[0].start;
        layer.outPoint = layerEnd;
        layer.transform.position.setValue([comp.width / 2, comp.height - 100]);
        layer.transform.anchorPoint.setValue([0, 0]);
        recreateColorAnimator(layer); applyExpressions(layer); applyBackgroundEffects(layer);
        layer.selected = true;
        // Auto-snap если включён
        if (settings.autoSnap) {
            var threshold = settings.snapThreshold || 5;
            var snapped   = snapMarkers(layer, threshold);
            if (snapped > 0) {
                mainStatus.text = "Subtitles created. Snapped " + snapped + " marker(s).";
            }
        }
        app.endUndoGroup();
        mainStatus.text = "Subtitles created.";
    }
// ================= @block PLUG:GEN:002 @desc Create Layer from VTT =================
    
    function createFromVTT(subs, layerName) {
            // Аналогично SRT
        var comp = app.project.activeItem;
        if (!(comp instanceof CompItem)) return;
        app.beginUndoGroup("Import VTT");
        var layer = comp.layers.addText("");
        if (layerName) layer.name = layerName;
        var m = layer.property("Marker");
        while (m.numKeys) m.removeKey(1);
        var maxTime = 0;
        for (var i = 0; i < subs.length; i++) {
            var mv = new MarkerValue(subs[i].text + " ||| DUR=" + subs[i].duration.toFixed(3));
            mv.duration = subs[i].duration; mv.url = "0"; mv.label = 0;
            m.setValueAtTime(subs[i].start, mv);
            if (subs[i].end > maxTime) maxTime = subs[i].end;
        }
        if (comp.duration < maxTime) comp.duration = maxTime + 0.5;
        // Add extra margin so last marker is fully visible
        var layerEnd = maxTime + Math.max(subs[subs.length-1].duration, 0.5);
        if (comp.duration < layerEnd) comp.duration = layerEnd;
        layer.inPoint = subs[0].start;
        layer.outPoint = layerEnd;
        layer.transform.position.setValue([comp.width / 2, comp.height - 100]);
        layer.transform.anchorPoint.setValue([0, 0]);
        recreateColorAnimator(layer); applyExpressions(layer); applyBackgroundEffects(layer);
        layer.selected = true;
        app.endUndoGroup();
        mainStatus.text = "VTT subtitles created.";
    }

// ================= @block PLUG:GEN:003 @desc Create Markers from Text =================

    function createMarkersFromText(comp, text, wordsPerMarker) {
            // Разбиение текста на группы слов
            // Равномерное распределение по длительности comp
        app.beginUndoGroup("Text to Markers");
        try {
            var rawWords = text.split(/\s+/), words = [];
            for (var i = 0; i < rawWords.length; i++) if (rawWords[i].length > 0) words.push(rawWords[i]);
            if (words.length === 0) { alert("Text empty"); app.endUndoGroup(); return; }
            var groups = [];
            for (var i = 0; i < words.length; i += wordsPerMarker) {
                var g = [];
                for (var j = i; j < i + wordsPerMarker && j < words.length; j++) g.push(words[j]);
                groups.push(g.join(" "));
            }
            var layer = comp.layers.addText(text);
            layer.name = "Generated Markers Layer"; layer.inPoint = 0; layer.outPoint = comp.duration;
            var mp = layer.property("Marker");
            var interval = comp.duration / groups.length;
            for (var k = 0; k < groups.length; k++) {
                var mv = new MarkerValue(groups[k]); mv.duration = interval; mv.url = "0"; mv.label = 0;
                var mt = k * interval; if (mt >= comp.duration) mt = comp.duration - 0.001;
                mp.setValueAtTime(mt, mv);
            }
            layer.transform.position.setValue([comp.width / 2, comp.height - 100]);
            layer.transform.anchorPoint.setValue([0, 0]);
            recreateColorAnimator(layer); applyExpressions(layer); applyBackgroundEffects(layer);
            layer.selected = true;
            mainStatus.text = "Layer generated!";
        } catch(e) { alert("Error: " + e.toString()); }
        app.endUndoGroup();
    }

    // ================= EVENT HANDLERS =================
    
    importBtnSrt.onClick = function() {
        var f = File.openDialog("Select SRT", "*.srt");
        if (!f) return;
        f.open("r"); var t = f.read(); f.close();
        createFromSRT(parseSrt(t), f.name);
    };
    
    importBtnVtt.onClick = function() {
        var f = File.openDialog("Select VTT", "*.vtt");
        if (!f) return;
        f.open("r"); var t = f.read(); f.close();
        var subs = parseVtt(t);
        if (subs.length === 0) { alert("No subtitles found"); return; }
        createFromVTT(subs, f.name);
    };

    syncBtn.onClick = function() {
        app.beginUndoGroup("Sync Colors");
        var count = syncMarkerColors();
        mainStatus.text = count > 0 ? "Colors updated: " + count : "Colors synced";
        app.endUndoGroup();
        liveUpdate();
    };

    ttmCreateBtn.onClick = function() {
        var text = textInput.text;
        if (!text || text.replace(/\s/g, "").length === 0) { alert("Enter text"); return; }
        var comp = app.project.activeItem;
        if (!(comp instanceof CompItem)) { alert("Open Composition"); return; }
        createMarkersFromText(comp, text, parseInt(wordsDropdown.selection.text, 10));
    };

    scaleInInput.onChanging = liveUpdate;
    bounceCountDropdown.onChange = liveUpdate;
    bounceAmpInput.onChanging = liveUpdate;
    animDropdown.onChange = liveUpdate;
    btnUp.onClick = function() { bounceMode = 0; liveUpdate(); };
    btnDown.onClick = function() { bounceMode = 1; liveUpdate(); };
    bgEnableCheck.onClick = function() { updateUI(); updateBackgroundEffectsOnSelectedLayer(); };
    bgPaddingInput.onChange = updateBackgroundEffectsOnSelectedLayer;
    bgRoundInput.onChange = updateBackgroundEffectsOnSelectedLayer;

    durationInput.onChange = function() {
        var layer = getSelectedTextLayer();
        if (!layer) return;
        var v = f(durationInput.text); if (!v) return;
        app.beginUndoGroup("Change Duration");
        var m = layer.marker;
        for (var i = 1; i <= m.numKeys; i++) { var mv = m.keyValue(i); mv.duration = v; m.setValueAtKey(i, mv); }
        app.endUndoGroup();
    };

    autoBtn.onClick = function() {
        var layer = getSelectedTextLayer(); if (!layer) return;
        app.beginUndoGroup("Auto Duration");
        var m = layer.marker;
        for (var i = 1; i <= m.numKeys; i++) {
            var mv = m.keyValue(i);
            if (mv.comment && mv.comment.indexOf("DUR=") !== -1) {
                mv.duration = parseFloat(mv.comment.split("DUR=")[1]);
                m.setValueAtKey(i, mv);
            }
        }
        app.endUndoGroup();
        durationInput.text = "";
    };

// ================= @block PLUG:SNAP:001 @desc Snap Markers =================
function snapMarkers(layer, thresholdFrames) {
    var comp = app.project.activeItem;
    if (!comp || !(comp instanceof CompItem)) return 0;

    var fps       = comp.frameRate;
    var threshold = thresholdFrames / fps;  // порог в секундах
    var markers   = layer.property("Marker");
    var count     = markers.numKeys;

    if (count < 2) return 0;

    // Собираем данные всех маркеров (нельзя менять во время итерации)
    var data = [];
    for (var i = 1; i <= count; i++) {
        data.push({
            time:     markers.keyTime(i),
            value:    markers.keyValue(i),
            duration: markers.keyValue(i).duration
        });
    }

    var snapped = 0;

    app.beginUndoGroup("Snap Markers");

    for (var i = 0; i < data.length - 1; i++) {
        var currentEnd = data[i].time + data[i].duration;
        var nextStart  = data[i + 1].time;
        var gap        = nextStart - currentEnd;

        if (gap > 0 && gap < threshold) {
            // Растягиваем duration текущего маркера до начала следующего
            var mv       = data[i].value;
            mv.duration  = nextStart - data[i].time;
            mv.comment   = mv.comment; // сохраняем комментарий
            markers.setValueAtKey(i + 1, mv);
            // Обновляем data для следующей итерации
            data[i].duration = mv.duration;
            snapped++;
        }
    }

    app.endUndoGroup();
    return snapped;
}    

    // ================= AI SERVICE =================

// ================= @block PLUG:SETTINGS:001 @desc Load Settings =================
    function loadSettings() {
        var file = new File(SETTINGS_FILE);
        if (file.exists) {
            file.open("r"); file.encoding = "UTF-8";
            try { settings = JSON.parse(file.read()); } catch(e) {}
            file.close();
        }
    }
    
// ================= @block PLUG:SETTINGS:002 @desc Save Settings =================

    function saveSettings() {
        var file = new File(SETTINGS_FILE);
        file.open("w"); file.encoding = "UTF-8";
        file.write(JSON.stringify(settings, null, 2));
        file.close();
    }
    
    function generateTaskId() {
        return new Date().getTime().toString(36) + Math.random().toString(36).substr(2, 4);
    }
    
    function formatTime(ms) {
        var sec = Math.floor(ms / 1000);
        var min = Math.floor(sec / 60);
        sec = sec % 60;
        return min + ":" + (sec < 10 ? "0" : "") + sec;
    }
    
    function isDirectMode() { return settings.serverUrl && settings.accessKey; }
    
    function getServerBaseUrl() {
        var url = settings.serverUrl || "";
        if (url.charAt(url.length - 1) === "/") url = url.substring(0, url.length - 1);
        return url;
    }
    
    function getSelectedLanguageCode() {
        var idx = langDropdown.selection.index;
        if (idx >= 0 && idx < TRANSLATION_LANGUAGES.length) return TRANSLATION_LANGUAGES[idx].code;
        return "orig";
    }

// ================= @block PLUG:SETTINGS:003 @desc Settings Dialog =================

    function showSettingsDialog() {
        var dlg = new Window("dialog", "Settings — " + SCRIPT_NAME);
        dlg.orientation = "column"; dlg.alignChildren = ["fill", "top"]; dlg.margins = 20; dlg.spacing = 15;
        var saveSuccess = false;
        
        var keyPanel = dlg.add("panel", undefined, "Server Connection"); keyPanel.alignChildren = ["fill", "top"]; keyPanel.margins = 10; keyPanel.spacing = 8;
        var serverRow = keyPanel.add("group"); serverRow.add("statictext", undefined, "Server URL:").preferredSize.width = 70;
        var serverInput = serverRow.add("edittext", undefined, settings.serverUrl || "https://subtitler.qzz.io"); serverInput.preferredSize.width = 220;
        var keyRow = keyPanel.add("group"); keyRow.add("statictext", undefined, "API Key:").preferredSize.width = 70;
        var keyInput = keyRow.add("edittext", undefined, settings.accessKey); keyInput.preferredSize.width = 220;
        keyPanel.add("statictext", undefined, "Get key at https://subtitler.qzz.io/account.php").graphics.font = ScriptUI.newFont("Arial", "Regular", 10);
        var testRow = keyPanel.add("group"); testRow.alignment = ["center", "top"];
        var btnTest = testRow.add("button", undefined, "Test Connection");
        var testResult = testRow.add("statictext", undefined, ""); testResult.preferredSize.width = 100;
        
        btnTest.onClick = function() {
            var url = serverInput.text, key = keyInput.text.replace(/\s/g, "");
            if (!url || url === "https://") { testResult.text = "Enter URL"; return; }
            if (!key) { testResult.text = "Enter key"; return; }
            testResult.text = "Testing..."; dlg.update();
            var r = testServerConnection(url, key);
            testResult.text = r.success ? "OK" : (r.message || "FAIL");
        };
        
        var btnGroup = dlg.add("group"); btnGroup.alignment = ["right", "top"];
        btnGroup.add("button", undefined, "Cancel", {name: "cancel"}).onClick = function() { dlg.close(); };
        btnGroup.add("button", undefined, "Save", {name: "ok"}).onClick = function() {
            var url = serverInput.text, key = keyInput.text.replace(/\s/g, "");
            if (!url || url === "https://") { alert("Enter URL!"); return; }
            if (!key) { alert("Enter key!"); return; }
            settings.serverUrl = url; settings.accessKey = key;
            saveSettings(); saveSuccess = true; dlg.close();
        };
        dlg.show();
        if (saveSuccess) updateConnectionStatus();
    }
    
    function updateConnectionStatus() {
        if (settings.serverUrl && settings.accessKey) {
            connectionStatus.text = "Connected"; modeDisplay.text = "Direct Server";
            serverDisplay.text = parseUrl(settings.serverUrl).host;
            btnSelectFile.enabled = true; return;
        }
        connectionStatus.text = "Not Configured"; modeDisplay.text = "—"; serverDisplay.text = "—"; btnSelectFile.enabled = false;
    }
    
    function getFormatCode() {
        return ["word", "short", "standard", "long"][formatDropdown.selection.index];
    }
    
    // ================= POLLING =================
    
    $.global._subtitlerPolling = { active: false, taskId: null, resultsFolder: "", startTime: 0, maxWait: MAX_WAIT_TIME_MS, checkInterval: CHECK_INTERVAL_MS, mode: "cloud" };
    $.global._subtitlerTimer = { active: false, startTime: 0 };
    $.global._subtitlerOnSuccess = null;
    $.global._subtitlerOnTimeout = null;
    $.global._subtitlerOnTimer = null;
    $.global._subtitlerOnError = null;
    
    $.global._subtitlerCheckResultDirect = function() {
        var p = $.global._subtitlerPolling;
        if (!p.active || p.mode !== "direct") return;
        var elapsed = new Date().getTime() - p.startTime;
        
        var r = httpGet(p.serverUrl + "/api_status.php?task_id=" + p.taskId, p.apiKey);
        
        if (r.success) {
            try {
                var j = JSON.parse(r.body);
                
                // Completed
                if (j.status === "completed") {
                    p.active = false;
                    $.global._subtitlerTimer.active = false;
                    if ($.global._subtitlerOnSuccess) $.global._subtitlerOnSuccess(elapsed);
                    return;
                }
                
                // Error (including insufficient balance for URL tasks)
                if (j.status === "error") {
                    p.active = false;
                    $.global._subtitlerTimer.active = false;
                    
                    var errorMsg = "Processing failed";
                    var reason = (j.error || j.reason || j.message || "").toLowerCase();
                    
                    if (reason.indexOf("insufficient") !== -1 || 
                        reason.indexOf("balance") !== -1 ||
                        reason.indexOf("not enough") !== -1) {
                        errorMsg = "Insufficient token balance. Top up at https://subtitler.qzz.io";
                    } else if (j.error || j.reason || j.message) {
                        errorMsg = j.error || j.reason || j.message;
                    }
                    
                    if ($.global._subtitlerOnError) {
                        $.global._subtitlerOnError(errorMsg);
                    }
                    return;
                }
                
                // queued / processing — continue polling
                
            } catch(e) {}
        }
        
        // Timeout check
        if (elapsed >= p.maxWait) {
            p.active = false;
            $.global._subtitlerTimer.active = false;
            if ($.global._subtitlerOnTimeout) $.global._subtitlerOnTimeout();
            return;
        }
        
        app.scheduleTask('$.global._subtitlerCheckResultDirect()', p.checkInterval, false);
    };
    
    $.global._subtitlerUpdateTimer = function() {
        var t = $.global._subtitlerTimer; if (!t.active) return;
        if ($.global._subtitlerOnTimer) $.global._subtitlerOnTimer(new Date().getTime() - t.startTime);
        app.scheduleTask('$.global._subtitlerUpdateTimer()', 1000, false);
    };
    
// ================= @block PLUG:POLL:002 @desc Start Polling (Direct Server) =================

    function startPollingDirect(taskId, serverUrl, apiKey, onSuccess, onTimeout, onTimer, onError) {
        var now = new Date().getTime();
        var p = $.global._subtitlerPolling;
        p.active = true; p.taskId = taskId; p.serverUrl = serverUrl; p.apiKey = apiKey;
        p.startTime = now; p.maxWait = MAX_WAIT_TIME_MS;
        p.checkInterval = CHECK_INTERVAL_MS; p.mode = "direct";
        var t = $.global._subtitlerTimer; t.active = true; t.startTime = now;
        $.global._subtitlerOnSuccess = onSuccess;
        $.global._subtitlerOnTimeout = onTimeout;
        $.global._subtitlerOnTimer = onTimer;
        $.global._subtitlerOnError = onError || null;
        app.scheduleTask('$.global._subtitlerCheckResultDirect()', CHECK_INTERVAL_MS, false);
        app.scheduleTask('$.global._subtitlerUpdateTimer()', 1000, false);
    }

// ================= @block PLUG:POLL:003 @desc Stop Polling =================

    function stopPolling() { $.global._subtitlerPolling.active = false; $.global._subtitlerTimer.active = false; }
    

// ================= @block PLUG:WORKFLOW:001 @desc File processing (shared logic) =================

    function processFileForTranscription(sourceFile) {
        var comp = app.project.activeItem;
        if (!comp || !(comp instanceof CompItem)) {
            comp = null;
            for (var i = 1; i <= app.project.numItems; i++) {
                if (app.project.item(i) instanceof CompItem) {
                    comp = app.project.item(i);
                    break;
                }
            }
        }
        if (!comp) {
            alert("Open a Composition first!");
            return;
        }
        
        currentComp = comp;
        currentTaskId = generateTaskId();
        currentCloudFile = null;
        var formatCode = getFormatCode();
        var targetLanguage = getSelectedLanguageCode();
        
        btnSelectFile.enabled = false;
        btnUseActive.enabled = false;
        btnServiceImport.enabled = false;
        
        if (isDirectMode()) {
            svcStatusText.text = "Uploading...";
            timeText.text = "";
            
            var serverUrl = getServerBaseUrl();
            var result = httpPostMultipart(
                serverUrl + "/api_upload.php", 
                settings.accessKey, 
                sourceFile.fsName, 
                formatCode, 
                targetLanguage
            );
            
            if (!result.success) {
                svcStatusText.text = "Upload failed";
                timeText.text = result.error || "HTTP " + result.status;
                btnSelectFile.enabled = true;
                btnUseActive.enabled = true;
                currentTaskId = null;
                return;
            }
            
            try {
                var json = JSON.parse(result.body);
                
                if (json.error || json.detail) {
                    var errorMsg = json.error || json.detail;
                    var errorLower = errorMsg.toLowerCase();
                    
                    if (errorLower.indexOf("balance") !== -1 || 
                        errorLower.indexOf("insufficient") !== -1 || 
                        errorLower.indexOf("not enough") !== -1) {
                        svcStatusText.text = "Insufficient balance";
                        timeText.text = "Top up at https://subtitler.qzz.io";
                    } else {
                        svcStatusText.text = "Error";
                        timeText.text = errorMsg;
                    }
                    
                    btnSelectFile.enabled = true;
                    btnUseActive.enabled = true;
                    currentTaskId = null;
                    return;
                }
                
                currentTaskId = json.task_id;
                
                if (json.new_balance !== undefined) {
                    updateBalanceUI(json.new_balance);
                }                
                
            } catch(e) {
                svcStatusText.text = "Parse error";
                timeText.text = e.toString();
                btnSelectFile.enabled = true;
                btnUseActive.enabled = true;
                currentTaskId = null;
                return;
            }
            
            var directTaskId = currentTaskId;
            var directServerUrl = serverUrl;
            var directApiKey = settings.accessKey;
            
            svcStatusText.text = (targetLanguage && targetLanguage !== "orig") 
                ? "Processing + Translating..." 
                : "Processing...";
            timeText.text = "0:00";
            isWaiting = true;
            
            startPollingDirect(currentTaskId, serverUrl, settings.accessKey,
                function(elapsed) {
                    isWaiting = false;
                    svcStatusText.text = "Completed";
                    timeText.text = "Time: " + formatTime(elapsed);
                    btnServiceImport.enabled = true;
                    btnSelectFile.enabled = true;
                    btnUseActive.enabled = true;
                    try { beep(); } catch(e) {}
                },
                function() {
                    // TIMEOUT — cancel task on server
                    isWaiting = false;
                    try {
                        var cancelUrl = directServerUrl + "/api_status.php?task_id=" + directTaskId + "&cancel=1";
                        var cancelResult = httpGet(cancelUrl, directApiKey);
                        if (cancelResult && cancelResult.success) {
                            try {
                                var cr = JSON.parse(cancelResult.body);
                                if (cr.success) {
                                    svcStatusText.text = "Cancelled";
                                    timeText.text = cr.refunded > 0 ? "Tokens refunded: " + cr.refunded : "";
                                    btnSelectFile.enabled = true;
                                    btnUseActive.enabled = true;
                                    currentTaskId = null;
                                    return;
                                }
                            } catch(e) {}
                        }
                    } catch(e) {}
                    svcStatusText.text = "Timeout";
                    timeText.text = "Check results at https://subtitler.qzz.io";
                    btnSelectFile.enabled = true;
                    btnUseActive.enabled = true;
                    currentTaskId = null;
                },
                function(elapsed) {
                    timeText.text = "Elapsed: " + formatTime(elapsed);
                }
            );
        }    
    }

// ================= Button handlers =================
    btnSelectFile.onClick = function() {
        var sourceFile = File.openDialog("Select Media", "*.*");
        if (!sourceFile) return;
        processFileForTranscription(sourceFile);
    };
    
    btnUseActive.onClick = function() {
        var selection = app.project.selection;
        
        if (!selection || selection.length === 0) {
            alert("Select a media file in the Project panel.");
            return;
        }
        
        var selectedItem = selection[0];
        
        if (!(selectedItem instanceof FootageItem)) {
            alert("Selected item is not a media file.\nSelect a video or audio footage item in the Project panel.");
            return;
        }
        
        if (!selectedItem.mainSource || !(selectedItem.mainSource instanceof FileSource)) {
            alert("Selected item has no file source.\nSelect a file-based footage item.");
            return;
        }
        
        var sourceFile = selectedItem.mainSource.file;
        
        if (!sourceFile || !sourceFile.exists) {
            alert("Source file not found:\n" + (sourceFile ? sourceFile.fsName : "unknown"));
            return;
        }
        
        processFileForTranscription(sourceFile);
    };

// ================= Button handlers =================

    btnSelectFile.onClick = function() {
        var sourceFile = File.openDialog("Select Media", "*.*");
        if (!sourceFile) return;
        processFileForTranscription(sourceFile);
    };
    
    btnUseActive.onClick = function() {
        // Get selected item from Project panel
        var selection = app.project.selection;
        
        if (!selection || selection.length === 0) {
            alert("Select a media file in the Project panel.");
            return;
        }
        
        var selectedItem = selection[0];
        
        // Must be a footage item (not comp, folder, etc.)
        if (!(selectedItem instanceof FootageItem)) {
            alert("Selected item is not a media file.\nSelect a video or audio footage item in the Project panel.");
            return;
        }
        
        // Must have a file source (not solid, placeholder, etc.)
        if (!selectedItem.mainSource || !(selectedItem.mainSource instanceof FileSource)) {
            alert("Selected item has no file source.\nSelect a file-based footage item.");
            return;
        }
        
        var sourceFile = selectedItem.mainSource.file;
        
        if (!sourceFile || !sourceFile.exists) {
            alert("Source file not found:\n" + (sourceFile ? sourceFile.fsName : "unknown"));
            return;
        }
        
        processFileForTranscription(sourceFile);
    };
        
// ================= @block PLUG:WORKFLOW:002 @desc Import Result =================

    btnServiceImport.onClick = function() {
            // Direct mode: downloadFileUtf8
            // Cloud mode: read from results folder
            // Parse SRT → createFromSRT
        var comp = app.project.activeItem;
        if (!comp || !(comp instanceof CompItem)) { alert("Select Composition in Project panel!"); return; }
        if (!currentTaskId) { alert("No Task!"); return; }
        
        var srtContent = "";
        var layerName = "Task_" + currentTaskId + ".srt";
        
        if (isDirectMode()) {
            var serverUrl = getServerBaseUrl();
            var downloadUrl = serverUrl + "/api_download.php?task_id=" + currentTaskId;
            
            // Используем функцию с правильной кодировкой
            var result = downloadFileUtf8(downloadUrl, settings.accessKey);
            
            if (!result.success) {
                alert("Download failed: " + result.error);
                return;
            }
            
            srtContent = result.content;
        } else {
            alert("Cloud Sync mode is disabled. Please configure Direct Server in Settings.");
            return;
        }
        
        var subs = parseSrt(srtContent);
        if (subs.length === 0) { alert("Empty or invalid SRT file!"); return; }
        
        createFromSRT(subs, layerName);
        
        svcStatusText.text = "Imported";
        timeText.text = "";
        btnServiceImport.enabled = false;
        btnSelectFile.enabled = true;
        currentTaskId = null;
    };
    
    btnSettings.onClick = showSettingsDialog;
    updateConnectionStatus();

// Глобальная функция для очистки статуса фидбека (нужна для app.scheduleTask)
function clearFeedbackStatus() {
    if (feedbackStatusText) feedbackStatusText.text = "";
}

// Обработчик кнопки Submit feedback
feedbackSubmitBtn.onClick = function() {
    var msg = feedbackInput.text;
    if (!msg || msg.replace(/\s/g, "").length === 0) return;

    feedbackSubmitBtn.enabled = false; // Блокируем

    try {
        // Формируем тело запроса
        var bodyStr = "feedback=" + encodeURIComponent(msg) + "&script_version=" + encodeURIComponent(SCRIPT_VERSION);

        // ЖЕСТКО указываем адрес сервера.
        var feedbackUrl = SCRIPT_URL + "/api_feedback.php";
        
        var headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "close"
        };
        
        if (settings.accessKey) {
            headers["X-API-Key"] = settings.accessKey;
        }

        var response = httpRequest("POST", feedbackUrl, headers, bodyStr);

        // --- ВРЕМЕННАЯ ДИАГНОСТИКА ---
        var alertMsg = "URL: " + feedbackUrl + "\n";
        alertMsg += "Success: " + (response ? response.success : "null") + "\n";
        alertMsg += "Status: " + (response ? response.status : "null") + "\n";
        alertMsg += "Error: " + (response ? response.error : "null") + "\n";
        alertMsg += "Body: " + (response ? response.body.substring(0, 200) : "null");
        alert(alertMsg);
        // -----------------------------

        // Если успешно — просто очищаем поле.
        if (response && response.success) {
            feedbackInput.text = "";
        }
        
    } catch (e) {
        alert("JS Error: " + e.toString());
    } finally {
        feedbackSubmitBtn.enabled = true; // Разблокируем кнопку
    }
};

// ================= @block PLUG:MAIN:001 @desc Initialize =================

    updateUI();
    switchTab(0);
    
    if (win instanceof Window) { win.center(); win.show(); }

})(this);