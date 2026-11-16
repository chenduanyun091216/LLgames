/* The game owns rendering and input. JavaScript owns browser network/storage APIs. */
(() => {
    const invite = new URL(location.href).searchParams.get('room') || '';
    let resumeCode = '';
    try { resumeCode = sessionStorage.getItem('ttgames-lan-active') || ''; } catch (_) {}
    if (invite && invite !== resumeCode) resumeCode = '';
    const transport = window.ttgamesLAN = {
        address: location.origin, invite, resumeCode, error: '', leaveResult: false,
        state: '', stateRevision: 0, slot: 0, ended: false, ready: false, createId: '', leaveId: '',
        lastSnapshotAt: null, maxSnapshotGap: 0,
        perf: new URL(location.href).searchParams.get('perf') === '1',
    };
    const bridge = new LLBridge({
        version: 2,
        onStatus(kind, detail) {
            if (kind === 'ended' || kind === 'stopped') {
                try { sessionStorage.removeItem('ttgames-lan-active'); } catch (_) {}
                if (kind === 'ended' || transport.slot) transport.ended = true;
            }
            if (kind === 'connected') {
                try { sessionStorage.setItem('ttgames-lan-active', bridge.code); } catch (_) {}
            }
            transport.ready = kind === 'connected' || (kind === 'error' && bridge.welcomed);
            transport.error = ({connecting: '连接中…', disconnected: '连接中断，正在重连'})[kind] || detail || '';
        },
        onState() {
            const now = performance.now();
            if (transport.lastSnapshotAt !== null) {
                transport.maxSnapshotGap = Math.max(transport.maxSnapshotGap, now - transport.lastSnapshotAt);
            }
            transport.lastSnapshotAt = now;
            transport.slot = bridge.slot;
            const raw = bridge.takeState();
            if (raw !== transport.state) {
                transport.state = raw;
                transport.stateRevision++;
            }
        },
    });
    const requestId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
    async function request(path, body) {
        const response = await fetch(path, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body), signal: AbortSignal.timeout(8000),
        });
        if (!response.ok) {
            if (response.status === 404) throw new Error('当前网页未连接联机宿主');
            throw new Error((await response.json()).error || '请求失败');
        }
        return response.json();
    }
    transport.begin = async (mode, value) => {
        transport.reset();
        transport.error = '连接中…';
        try {
            if (mode === 'create') {
                transport.createId ||= requestId();
                const result = await request('/rooms', {request_id: transport.createId});
                bridge.hostToken = result.host_token;
                transport.invite = result.invite_url;
                bridge.connect(result.code);
            } else {
                if (!/^[0-9]{4}$/.test(value)) {
                    const url = new URL(value);
                    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || !/^[0-9]{4}$/.test(url.searchParams.get('room'))) {
                        throw new Error('请输入四位房间码或邀请链接');
                    }
                    if (url.origin !== location.origin) { location.assign(url.href); return; }
                    value = url.searchParams.get('room');
                }
                bridge.hostToken = null;
                bridge.connect(value);
            }
        } catch (error) {
            transport.error = error.message || '连接失败';
        }
    };
    transport.send = raw => {
        if (!bridge.welcomed) return;
        const message = JSON.parse(raw);
        if (message.type === 'input') return bridge.input(message.dx, message.dy, message.shoot) ? bridge.seq : null;
        else if (message.type === 'action') bridge.action(message.action, message.key);
        else bridge.send(message);
    };
    transport.reset = () => {
        bridge.disconnect();
        transport.ended = false;
        transport.slot = 0;
        transport.state = '';
        transport.lastSnapshotAt = null;
        transport.maxSnapshotGap = 0;
        transport.stateRevision++;
        transport.error = '';
        transport.ready = false;
        transport.leaveResult = false;
    };
    transport.leave = async () => {
        transport.leaveId ||= requestId();
        try {
            await request('/rooms/leave', {request_id: transport.leaveId, room_id: bridge.roomId, token: bridge.token});
            try {
                sessionStorage.removeItem('llonline:' + bridge.code);
                sessionStorage.removeItem('ttgames-lan-active');
            } catch (_) {}
            transport.createId = transport.leaveId = '';
            transport.reset();
            transport.leaveResult = true;
        } catch (error) {
            transport.error = error.message || '退出失败，请重试';
        }
    };
    transport.noticeSeen = key => {
        try { return sessionStorage.getItem(key) === '1'; } catch (_) { return false; }
    };
    transport.markNotice = key => {
        try { sessionStorage.setItem(key, '1'); } catch (_) {}
    };
    const join = document.createElement('dialog');
    join.id = 'ttgames-lan-join';
    join.innerHTML = '<form method="dialog"><label for="ttgames-lan-address">房间码或邀请链接</label>' +
        '<input id="ttgames-lan-address" autocomplete="off" required>' +
        '<div><button value="cancel" formnovalidate>取消</button><button value="join">加入房间</button></div></form>';
    document.body.append(join);
    const field = join.querySelector('input');
    for (const type of ['keydown', 'keypress', 'keyup']) field.addEventListener(type, event => event.stopPropagation());
    join.addEventListener('close', () => {
        if (join.returnValue === 'join') transport.begin('join', field.value.trim());
    });
    transport.promptJoin = () => {
        join.returnValue = '';
        field.value = invite;
        join.showModal();
        field.focus();
    };
})();
