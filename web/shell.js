(() => {
    const box = document.getElementById('infobox');
    const loading = document.getElementById('ttgames-loading');
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
        if (caching) return;
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

    const canvas = document.getElementById('ttgames-ui');
    const ctx = canvas.getContext('2d');
    let previous = '';
    let previousLayout = '';
    let previousLabels = [];
    // The scene keeps its logical resolution; this separate layer draws glyphs at device resolution.
    window.ttgamesDrawUI = (frame, width, height, inBattle, paused, cutscene = '') => {
        if (!finished) finishProgress();
        loading.hidden = true;
        button.hidden = Boolean(cutscene) || !request;
        button.toggleAttribute('data-menu', !inBattle);
        quality.hidden = !paused;
        if (paused) {
            const scaleX = canvas.clientWidth / width;
            const scaleY = canvas.clientHeight / height;
            const pauseRight = canvas.clientWidth / 2 + 160 * scaleX;
            const style = getComputedStyle(quality);
            const menuWidth = parseFloat(style.getPropertyValue('--quality-menu-width'));
            const safeRight = parseFloat(style.getPropertyValue('--quality-safe-right'));
            quality.toggleAttribute('data-side', canvas.clientWidth - pauseRight >= menuWidth + 20 + safeRight);
            quality.style.left = `${canvas.clientWidth / 2 + 100 * scaleX}px`;
            quality.style.setProperty('--quality-top', `${canvas.clientHeight / 2 - 61 * scaleY}px`);
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
