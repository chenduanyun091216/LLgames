(() => {
    let activeTouches = new Set();
    window.ttgamesTouchActive = id => activeTouches.has(id);
    for (const type of ['touchstart', 'touchmove', 'touchend', 'touchcancel']) {
        window.addEventListener(type, event => {
            activeTouches = new Set(Array.from(event.touches, touch => touch.identifier));
        }, {capture: true, passive: true});
    }
    window.addEventListener('blur', () => activeTouches.clear());
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) activeTouches.clear();
    });

    const box = document.getElementById('infobox');
    const loading = document.getElementById('ttgames-loading');
    const visibleViewport = window.visualViewport;
    let updateGameSize;
    if (visibleViewport) {
        const positionViewport = () => {
            if (visibleViewport.width <= 0 || visibleViewport.height <= 0) return;
            const style = document.documentElement.style;
            style.setProperty('--game-viewport-left', `${visibleViewport.offsetLeft}px`);
            style.setProperty('--game-viewport-top', `${visibleViewport.offsetTop}px`);
            style.setProperty('--game-viewport-right', `${visibleViewport.offsetLeft + visibleViewport.width}px`);
            style.setProperty('--game-viewport-bottom', `${visibleViewport.offsetTop + visibleViewport.height}px`);
            updateGameSize?.();
            if (loading.hidden) return;
            style.setProperty('--loading-center-x', `${visibleViewport.offsetLeft + visibleViewport.width / 2}px`);
            style.setProperty('--loading-center-y', `${visibleViewport.offsetTop + visibleViewport.height / 2}px`);
            style.setProperty('--loading-visible-width', `${visibleViewport.width}px`);
        };
        visibleViewport.addEventListener('resize', positionViewport);
        visibleViewport.addEventListener('scroll', positionViewport);
        window.addEventListener('resize', positionViewport);
        positionViewport();
    }
    const gameCanvas = document.getElementById('canvas');
    const canvas = document.getElementById('ttgames-ui');
    // iPadOS can request desktop sites and identify itself as a Mac.
    window.ttgamesIPad = /iPad/.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    if (window.ttgamesIPad) {
        window.ttgamesSetSceneSize = (width, height, outputWidth, outputHeight) => {
            // Show the scene crop directly at viewport size, with a single browser resampling pass.
            gameCanvas.style.setProperty('--scene-scale-x', outputWidth / width);
            gameCanvas.style.setProperty('--scene-scale-y', outputHeight / height);
            gameCanvas.toggleAttribute('data-scene-crop', width !== outputWidth || height !== outputHeight);
        };
    }
    const showPerformance = /(?:\?|&)perf=1(?:&|$)/.test(window.location?.search || '');
    if (showPerformance) {
        const stats = document.createElement('output');
        stats.id = 'ttgames-frame-stats';
        stats.style.cssText = 'position:fixed;top:calc(var(--game-top, 0px) + 2px);left:4px;z-index:30;pointer-events:none;max-width:calc(100vw - 20px);' +
            'font:12px monospace;color:white;background:#071b2bdd;padding:3px 6px';
        document.body.append(stats);
        let last = null, started = null, mode = '', intervals = [], refreshes = 0;
        const countRefresh = () => {
            refreshes++;
            requestAnimationFrame(countRefresh);
        };
        requestAnimationFrame(countRefresh);
        const resetSample = () => {
            last = started = null;
            intervals = [];
            stats.textContent = '';
        };
        document.addEventListener('visibilitychange', resetSample);
        window.ttgamesRecordFrame = (currentMode, resized = false) => {
            const now = performance.now();
            if (resized || document.hidden || currentMode !== mode) {
                mode = currentMode;
                resetSample();
            }
            if (document.hidden) return;
            if (last !== null) intervals.push(now - last);
            last = now;
            if (started === null) {
                started = now;
                refreshes = 0;
            }
            if (now - started < 1000 || !intervals.length) return;
            const sorted = [...intervals].sort((a, b) => a - b);
            const p95 = sorted[Math.ceil(sorted.length * .95) - 1];
            const label = {single: '单人', lan: '联机', idle: '菜单/暂停'}[mode] || mode;
            stats.textContent = `${label} · ${Math.round(intervals.length * 1000 / (now - started))} FPS` +
                ` · 浏览器 rAF ${Math.round(refreshes * 1000 / (now - started))} Hz` +
                ` · 帧间隔 P95 ${p95.toFixed(1)} / 最大 ${sorted.at(-1).toFixed(1)} ms` +
                ` · >50ms ${intervals.filter(value => value > 50).length}`;
            const build = document.getElementById('ttgames-version')?.textContent;
            if (build) stats.textContent += ' · ' + build;
            const network = window.ttgamesLAN;
            if (mode === 'lan' && network?.lastSnapshotAt != null) {
                stats.textContent += ' · 网络最大间隔 ' + Math.round(network.maxSnapshotGap) +
                    ' / 当前等待 ' + Math.round(now - network.lastSnapshotAt) + ' ms';
                network.maxSnapshotGap = 0;
            }
            started = now;
            intervals = [];
            refreshes = 0;
        };
    }
    const safeArea = document.getElementById('ttgames-safe-area');
    if (gameCanvas && typeof ResizeObserver !== 'undefined') {
        updateGameSize = () => {
            window.ttgamesViewportWidth = canvas.clientWidth;
            window.ttgamesViewportHeight = canvas.clientHeight;
            if (safeArea) {
                const game = canvas.getBoundingClientRect();
                const safe = safeArea.getBoundingClientRect();
                window.ttgamesSafeArea = [safe.left - game.left, safe.top - game.top,
                    game.right - safe.right, game.bottom - safe.bottom]
                    .map(inset => Math.max(0, Math.ceil(inset))).join(',');
            }
        };
        const layoutObserver = new ResizeObserver(updateGameSize);
        layoutObserver.observe(canvas);
        if (safeArea) layoutObserver.observe(safeArea);
        updateGameSize();
    }
    const progress = loading.querySelector('progress');
    const loadingStatus = loading.querySelector('.loading-status');
    const loadingPercent = loading.querySelector('.loading-percent');
    const stages = ['正在加载浏览器运行环境', '正在下载游戏素材', '正在初始化游戏', '点击屏幕开始游戏'];
    const stageTargets = [0, 35, 80, 96];
    const stageLimits = [30, 75, 94, 98];
    let stage = 0;
    let target = 0;
    let displayed = 0;
    let previousTime = null;
    let finished = false;
    const drawProgress = () => {
        progress.value = displayed;
        loadingPercent.textContent = `${finished ? '' : '约 '}${Math.floor(displayed)}%`;
    };
    const finishProgress = () => {
        finished = true;
        displayed = 100;
        drawProgress();
    };
    const animateProgress = time => {
        if (finished) return;
        const elapsed = previousTime === null ? 0 : Math.min((time - previousTime) / 1000, 0.1);
        previousTime = time;
        target = Math.max(target, Math.min(stageLimits[stage], target + elapsed * 0.5));
        displayed += Math.min(target - displayed, elapsed * Math.max(1, (target - displayed) * 2));
        drawProgress();
        requestAnimationFrame(animateProgress);
    };
    drawProgress();
    requestAnimationFrame(animateProgress);
    const runtimeProgress = document.getElementById('progress');
    new MutationObserver(() => {
        if (stage === 0 && runtimeProgress.hasAttribute('value') && runtimeProgress.max > 0) {
            target = Math.max(target, Math.min(30, 30 * runtimeProgress.value / runtimeProgress.max));
        }
    }).observe(runtimeProgress, {attributes: true, attributeFilter: ['value', 'max']});
    window.ttgamesLoadStage = nextStage => {
        stage = Math.max(stage, Math.min(3, nextStage));
        target = Math.max(target, stageTargets[stage]);
        loadingStatus.textContent = stages[stage];
    };
    const button = document.getElementById('ttgames-fullscreen');
    const root = document.documentElement;
    const active = () => Boolean(document.fullscreenElement || document.webkitFullscreenElement);
    const request = root.requestFullscreen || root.webkitRequestFullscreen;
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    const update = () => {
        button.textContent = active() ? '×' : '⛶';
        button.title = active() ? '退出全屏' : '进入全屏';
        button.setAttribute('aria-label', button.title);
    };
    button.hidden = !request;
    button.addEventListener('click', async event => {
        event.stopPropagation();
        try {
            if (active()) await exit.call(document);
            else await request.call(root);
        } catch {
            button.title = '当前浏览器未允许全屏';
            button.setAttribute('aria-label', button.title);
        }
    });
    document.addEventListener('fullscreenchange', update);
    document.addEventListener('webkitfullscreenchange', update);

    const quality = document.getElementById('ttgames-quality');
    const qualityChoices = [...quality.querySelectorAll('input')];
    const resolutions = quality.querySelectorAll('label span');
    window.ttgamesShowResolutions = (...sizes) => {
        resolutions.forEach((label, i) => {
            label.textContent = `${sizes[2 * i]} × ${sizes[2 * i + 1]}`;
        });
    };
    const qualityKey = 'ttgames-render-density';
    let savedQuality;
    try {
        savedQuality = window.localStorage.getItem(qualityKey);
    } catch {
        // Settings remain usable when the browser blocks storage.
    }
    const initialQuality = qualityChoices.find(choice => choice.value === savedQuality)
        || qualityChoices.find(choice => choice.checked);
    initialQuality.checked = true;
    window.ttgamesRenderDensity = Number(initialQuality.value);
    quality.addEventListener('change', event => {
        if (!qualityChoices.includes(event.target)) return;
        window.ttgamesRenderDensity = Number(event.target.value);
        try {
            window.localStorage.setItem(qualityKey, event.target.value);
        } catch {
            // Keep the current session's selection.
        }
        quality.open = false;
        quality.querySelector('summary').focus();
    });
    for (const event of ['pointerdown', 'pointerup', 'click', 'keydown', 'keyup']) {
        quality.addEventListener(event, input => input.stopPropagation());
    }

    let caching = false;
    const prepareCache = async () => {
        // Keep the offline download out of performance samples.
        if (caching || showPerformance) return;
        caching = true;
        const status = document.getElementById('ttgames-offline');
        const serviceWorker = navigator.serviceWorker;
        if (!window.isSecureContext || !serviceWorker) {
            status.textContent = '离线保存需要支持此功能的浏览器和可信 HTTPS';
            return;
        }
        const failed = () => { status.textContent = '离线资源保存失败，请联网刷新重试'; };
        status.textContent = '正在自动保存离线资源，请保持页面开启…';
        try {
            const registration = await serviceWorker.register('./sw.js');
            const worker = registration.active || registration.waiting || registration.installing;
            if (!worker) {
                failed();
                return;
            }
            const update = () => {
                if (worker.state === 'activated') {
                    status.textContent = '离线资源已保存，下次可以断网打开';
                    setTimeout(() => { status.textContent = ''; }, 6000);
                } else if (worker.state === 'redundant') {
                    failed();
                }
            };
            worker.addEventListener('statechange', update);
            update();
        } catch (error) {
            failed();
            console.warn('TTgames offline cache:', error);
        }
    };
    const ready = () => {
        if (box.textContent === 'Ready to start ! Please click/touch page') {
            box.textContent = '点击或触摸屏幕开始游戏';
            box.dataset.ready = '';
            box.setAttribute('role', 'button');
            box.tabIndex = 0;
            finishProgress();
            prepareCache();
        }
    };
    new MutationObserver(ready).observe(box, {childList: true, characterData: true, subtree: true});
    ready();
    box.addEventListener('click', () => {
        if (box.hasAttribute('data-ready') && window.MM) window.MM.UME = true;
    });
    box.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            box.click();
        }
    });

    const ctx = canvas.getContext('2d');
    const buildVersion = document.getElementById('ttgames-version');
    let previous = '';
    let previousLayout = '';
    let previousLabels = [];
    // The scene keeps its logical resolution; this separate layer draws glyphs at device resolution.
    window.ttgamesDrawUI = (frame, width, height, inBattle, paused, cutscene = '', home = false) => {
        if (!finished) finishProgress();
        if (!loading.hidden) {
            gameCanvas.setAttribute('data-game-ready', '');
            loading.hidden = true;
        }
        if (buildVersion) buildVersion.hidden = !home;
        const offlineStatus = document.getElementById('ttgames-offline');
        if (offlineStatus) offlineStatus.hidden = inBattle || paused;
        button.hidden = Boolean(cutscene) || !request;
        button.toggleAttribute('data-menu', !inBattle);
        quality.hidden = !paused;
        if (paused) {
            const scaleX = canvas.clientWidth / width;
            const scaleY = canvas.clientHeight / height;
            const pauseRight = canvas.clientWidth / 2 + 160 * scaleX;
            const style = getComputedStyle(quality);
            const menuWidth = parseFloat(style.getPropertyValue('--quality-menu-width'));
            quality.toggleAttribute('data-side', canvas.clientWidth - pauseRight >= menuWidth + 20);
            quality.style.setProperty('--quality-left', `${canvas.clientWidth / 2 + 100 * scaleX}px`);
            quality.style.setProperty('--quality-top', `${canvas.clientHeight / 2 - 139 * scaleY}px`);
            quality.style.setProperty('--pause-right', `${pauseRight}px`);
            quality.style.setProperty('--pause-bottom', `${canvas.clientHeight / 2 + 75 * scaleY}px`);
        } else {
            quality.open = false;
        }
        canvas.style.transition = cutscene === 'ending' ? 'opacity 460ms ease-out' : '';
        canvas.style.opacity = cutscene ? '0' : '1';
        if (cutscene) return;
        if (!ctx) return;
        prepareCache();
        const dpr = Math.min(3, window.devicePixelRatio || 1);
        const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
        const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
        const layout = `${w}:${h}:${width}:${height}`;
        const key = `${layout}:${frame}`;
        if (key === previous) return;
        previous = key;
        if (canvas.width !== w) canvas.width = w;
        if (canvas.height !== h) canvas.height = h;
        ctx.setTransform(w / width, 0, 0, h / height, 0, 0);
        if (layout !== previousLayout) {
            ctx.clearRect(0, 0, width, height);
        } else {
            for (const [, , , , x, y, rw, rh] of previousLabels) {
                ctx.clearRect(x - 4, y - 4, rw + 8, rh + 8);
            }
        }
        previousLayout = layout;
        previousLabels = JSON.parse(frame);
        ctx.textBaseline = 'middle';
        const family = 'system-ui, "PingFang SC", "Noto Sans CJK SC", sans-serif';
        for (const [label, size, bold, color, x, y, rw, rh, align] of previousLabels) {
            ctx.textAlign = align;
            ctx.font = `${bold ? 700 : 500} ${Math.min(size, rh)}px ${family}`;
            ctx.fillStyle = 'rgba(1, 9, 18, .85)';
            const tx = x + (align === 'center' ? rw / 2 : align === 'right' ? rw : 0);
            const ty = y + rh / 2;
            ctx.fillText(label, tx + .75, ty + 1, rw);
            ctx.fillStyle = `rgb(${color.join(',')})`;
            ctx.fillText(label, tx, ty, rw);
        }
    };
})();
