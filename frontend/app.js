document.addEventListener("DOMContentLoaded", () => {

    // --- State ---
    let appConfig = JSON.parse(localStorage.getItem("sc_config")) || null;
    let ws = null;
    let player = null;

    // --- DOM Elements ---
    const ui = {
        domainStatus: document.getElementById("domain-status"),
        onboardingWizard: document.getElementById("onboarding-wizard"),
        setupForm: document.getElementById("setup-form"),
        appContent: document.getElementById("app-content"),
        searchForm: document.getElementById("search-form"),
        searchInput: document.getElementById("search-input"),
        searchResults: document.getElementById("search-results"),
        playerModal: document.getElementById("player-modal"),
        closePlayerBtn: document.getElementById("close-player"),
        videoElement: document.getElementById("player"),
        downloadModal: document.getElementById("download-modal"),
        downloadForm: document.getElementById("download-form"),
        cancelDlModalBtn: document.getElementById("cancel-dl-modal"),
        queueList: document.getElementById("queue-list")
    };

    // --- Initialization ---
    async function init() {
        await checkStatus();

        if (!appConfig) {
            ui.onboardingWizard.classList.remove("hidden");
        } else {
            ui.appContent.classList.remove("hidden");
            ui.setupForm.querySelector("#download-path").value = appConfig.downloadPath;
            ui.setupForm.querySelector("#default-format").value = appConfig.defaultFormat;
            ui.setupForm.querySelector("#default-quality").value = appConfig.defaultQuality;
        }

        initWebSocket();
        initPlayer();
    }

    async function checkStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            if (data.domain) {
                ui.domainStatus.textContent = `Active Domain: ${data.domain}`;
                ui.domainStatus.classList.add("text-green-400");
                ui.domainStatus.classList.remove("text-gray-400");
            } else {
                ui.domainStatus.textContent = `No active domain. Auto-discovery running...`;
            }
        } catch (e) {
            console.error("Failed to check status", e);
        }
    }

    // --- Onboarding ---
    ui.setupForm.addEventListener("submit", (e) => {
        e.preventDefault();
        appConfig = {
            downloadPath: document.getElementById("download-path").value,
            defaultFormat: document.getElementById("default-format").value,
            defaultQuality: document.getElementById("default-quality").value
        };
        localStorage.setItem("sc_config", JSON.stringify(appConfig));

        ui.onboardingWizard.classList.add("hidden");
        ui.appContent.classList.remove("hidden");
    });

    // --- Search ---
    ui.searchForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const q = ui.searchInput.value.trim();
        if (!q) return;

        ui.searchResults.innerHTML = `<div class="col-span-full text-center">Searching...</div>`;

        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
            const json = await res.json();
            renderResults(json.data);
        } catch (e) {
            ui.searchResults.innerHTML = `<div class="col-span-full text-red-500">Search failed.</div>`;
        }
    });

    function renderResults(results) {
        if (!results || results.length === 0) {
            ui.searchResults.innerHTML = `<div class="col-span-full text-center text-gray-400">No results found.</div>`;
            return;
        }

        ui.searchResults.innerHTML = results.map(item => `
            <div class="bg-gray-800 p-4 rounded-lg flex gap-4 items-start border border-gray-700">
                <div class="flex-1">
                    <h3 class="font-bold text-lg">${item.name}</h3>
                    <p class="text-sm text-gray-400 mb-2">${item.type === 'tv' ? 'TV Show' : 'Movie'} | Score: ${item.score || 'N/A'}</p>
                    <div class="flex gap-2 mt-4">
                        <button class="bg-green-600 hover:bg-green-700 px-3 py-1 rounded text-sm font-bold btn-play" data-id="${item.id}">Watch</button>
                        <button class="bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded text-sm font-bold btn-download" data-id="${item.id}" data-title="${item.name}">Download</button>
                    </div>
                </div>
            </div>
        `).join("");

        // Attach listeners
        document.querySelectorAll('.btn-play').forEach(btn => {
            btn.addEventListener('click', (e) => handlePlay(e.target.dataset.id));
        });
        document.querySelectorAll('.btn-download').forEach(btn => {
            btn.addEventListener('click', (e) => handleDownloadModal(e.target.dataset.id, e.target.dataset.title));
        });
    }

    // --- Player Logic ---
    function initPlayer() {
        player = new Plyr(ui.videoElement, {
            controls: ['play-large', 'play', 'progress', 'current-time', 'mute', 'volume', 'fullscreen']
        });
    }

    async function handlePlay(titleId) {
        try {
            // In a real app we might ask for episode selection for TV shows.
            // For now, assume movie or stream direct
            const res = await fetch(`/api/stream/url?title_id=${titleId}`);
            if(!res.ok) throw new Error("Failed to get stream url");
            const data = await res.json();

            const m3u8Url = data.url;

            ui.playerModal.classList.remove('hidden');
            ui.playerModal.classList.add('flex');

            if (Hls.isSupported()) {
                const hls = new Hls();
                hls.loadSource(m3u8Url);
                hls.attachMedia(ui.videoElement);
                window.hls = hls;
            } else if (ui.videoElement.canPlayType('application/vnd.apple.mpegurl')) {
                ui.videoElement.src = m3u8Url;
            }
            player.play();

        } catch(e) {
            alert("Error loading stream: " + e.message);
        }
    }

    ui.closePlayerBtn.addEventListener('click', () => {
        player.pause();
        if(window.hls) {
            window.hls.destroy();
        }
        ui.playerModal.classList.add('hidden');
        ui.playerModal.classList.remove('flex');
    });

    // --- Download Logic ---
    async function handleDownloadModal(titleId, titleName) {
        try {
            const res = await fetch(`/api/stream/url?title_id=${titleId}`);
            if(!res.ok) throw new Error("Failed to get stream url");
            const data = await res.json();

            // Populate Qualities
            const qualSelect = document.getElementById("dl-quality");
            qualSelect.innerHTML = data.qualities.resolutions.map(q =>
                `<option value="${q.height}p">${q.height}p</option>`
            ).join("") || `<option value="best">Best Available</option>`;

            document.getElementById("dl-title").value = titleName;
            document.getElementById("dl-m3u8").value = data.url;

            if(appConfig) {
                document.getElementById("dl-format").value = appConfig.defaultFormat;
                // Attempt to select default quality if exists
            }

            ui.downloadModal.classList.remove("hidden");
        } catch(e) {
            alert("Error preparing download: " + e.message);
        }
    }

    ui.cancelDlModalBtn.addEventListener('click', () => {
        ui.downloadModal.classList.add("hidden");
    });

    ui.downloadForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const payload = {
            m3u8_url: document.getElementById("dl-m3u8").value,
            title: document.getElementById("dl-title").value,
            format: document.getElementById("dl-format").value,
            quality: document.getElementById("dl-quality").value,
            download_path: appConfig ? appConfig.downloadPath : "/app/downloads"
        };

        try {
            const res = await fetch("/api/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if(res.ok) {
                ui.downloadModal.classList.add("hidden");
            } else {
                alert("Failed to start download");
            }
        } catch(e) {
            alert("Error starting download");
        }
    });

    async function cancelDownload(taskId) {
        await fetch(`/api/download/${taskId}/cancel`, { method: "POST" });
    }

    // --- WebSocket Queue Manager ---
    function initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws/progress`);

        ws.onmessage = (event) => {
            const tasks = JSON.parse(event.data);
            updateQueue(tasks);
        };

        ws.onclose = () => {
            setTimeout(initWebSocket, 2000); // reconnect
        };
    }

    function updateQueue(tasks) {
        if(Object.keys(tasks).length === 0) {
            ui.queueList.innerHTML = `<div class="text-gray-400">No active downloads.</div>`;
            return;
        }

        ui.queueList.innerHTML = Object.entries(tasks).map(([id, task]) => `
            <div class="bg-gray-700 p-3 rounded flex flex-col items-stretch justify-between">
                <div class="flex-1 mb-2">
                    <div class="flex justify-between mb-1">
                        <span class="font-bold text-sm truncate pr-4">Task: ${id.substring(0,8)}...</span>
                        <span class="text-sm ${task.status === 'completed' ? 'text-green-400' : task.status === 'failed' ? 'text-red-400' : task.status === 'paused' ? 'text-yellow-400' : 'text-blue-400'}">${task.status} (${task.progress}%)</span>
                    </div>
                    <div class="w-full bg-gray-900 rounded-full h-2">
                        <div class="bg-blue-500 h-2 rounded-full" style="width: ${task.progress}%"></div>
                    </div>
                    <div class="flex justify-between mt-1 text-xs text-gray-400">
                        <span>Speed: ${task.speed || 'N/A'}</span>
                        <span>ETA: ${task.eta || 'N/A'}</span>
                    </div>
                </div>
                <div class="flex gap-2 justify-end">
                    ${task.status === 'downloading' ?
                        `<button class="bg-yellow-600 hover:bg-yellow-500 px-3 py-1 rounded text-xs font-bold pause-btn" data-id="${id}">Pause</button>`
                        : ''}
                    ${task.status === 'paused' ?
                        `<button class="bg-green-600 hover:bg-green-500 px-3 py-1 rounded text-xs font-bold resume-btn" data-id="${id}">Resume</button>`
                        : ''}
                    ${['downloading', 'pending', 'paused'].includes(task.status) ?
                        `<button class="bg-red-600 hover:bg-red-500 px-3 py-1 rounded text-xs font-bold cancel-btn" data-id="${id}">Cancel</button>`
                        : ''}
                </div>
            </div>
        `).join("");

        document.querySelectorAll('.pause-btn').forEach(btn => {
            btn.addEventListener('click', (e) => fetch(`/api/download/${e.target.dataset.id}/pause`, { method: "POST" }));
        });
        document.querySelectorAll('.resume-btn').forEach(btn => {
            btn.addEventListener('click', (e) => fetch(`/api/download/${e.target.dataset.id}/resume`, { method: "POST" }));
        });
        document.querySelectorAll('.cancel-btn').forEach(btn => {
            btn.addEventListener('click', (e) => cancelDownload(e.target.dataset.id));
        });
    }

    // Run
    init();
});
