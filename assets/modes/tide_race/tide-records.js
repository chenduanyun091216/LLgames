(() => {
    function raceRecords(name) {
        const states = new Map();
        let db, pending;
        function open() {
            if (db) return Promise.resolve(db);
            if (pending) return pending;
            pending = new Promise((resolve, reject) => {
                const request = indexedDB.open(name, 1);
                request.onupgradeneeded = () => {
                    for (const store of ['receipts', 'catalog', 'best']) request.result.createObjectStore(store);
                };
                request.onsuccess = () => {
                    db = request.result;
                    db.onversionchange = () => { db.close(); db = null; };
                    resolve(db);
                };
                request.onerror = () => reject(request.error);
                request.onblocked = () => reject(new Error('IndexedDB open blocked'));
            }).finally(() => { pending = null; });
            return pending;
        }
        function status(key) {
            const id = JSON.stringify(key);
            if (!states.has(id)) states.set(id, {error:false, best:null, revision:0});
            return states.get(id);
        }
        async function transaction(key, record, valid) {
            const state = status(key);
            try {
                if (record && !valid(record)) throw new Error('Invalid race record');
                const connection = await open();
                const best = await new Promise((resolve, reject) => {
                    const tx = connection.transaction('best', record ? 'readwrite' : 'readonly');
                    const store = tx.objectStore('best');
                    const id = ['tide_race', ...key];
                    const request = store.get(id);
                    let selected;
                    request.onsuccess = () => {
                        selected = valid(request.result) ? request.result : null;
                        if (record && (!selected || record[0] < selected[0])) {
                            selected = record;
                            store.put(selected, id);
                        }
                    };
                    tx.oncomplete = () => resolve(selected);
                    tx.onabort = tx.onerror = () => reject(tx.error);
                });
                if (!state.best || best && best[0] < state.best[0]) state.best = best;
                state.error = false;
            } catch {
                if (record && valid(record) && (!state.best || record[0] < state.best[0])) state.best = record;
                state.error = true;
            }
            state.revision++;
            return state;
        }
        let queue = Promise.resolve();
        return {status, read: (key, valid) => (queue = queue.then(() => transaction(key, null, valid))),
            write: (key, ticks, samples, valid) => (queue = queue.then(() => transaction(key, [ticks, samples], valid)))};
    }
    globalThis.ttgamesRaceRecords = raceRecords;
    const main = raceRecords('ttgames-main-modes');
    function valid(trackLength) {
        return record => {
            if (!Array.isArray(record)) return false;
            const [tick, rows] = record;
            let previous=-1;
            return Number.isInteger(tick) && tick>0 && tick<=12600 && Array.isArray(rows) && rows.length
                && rows.every(row => {
                    if (!Array.isArray(row) || row.length!==5) return false;
                    const [t,x,y,pose,branch]=row;
                    if (![t,x,y].every(Number.isInteger) || t<=previous || t>tick || x<0 || x>trackLength
                        || y<0 || y>540 || !['swim','glide','dive','reset'].includes(pose)
                        || !['surface','deep'].includes(branch)) return false;
                    previous=t;
                    return true;
                }) && rows[0][0]===0 && rows[0][1]===0 && rows.at(-1)[0]===tick
                    && rows.at(-1)[1]===trackLength && rows.at(-1)[4]==='surface';
        };
    }
    globalThis.ttgamesRaceRecordValidator = valid;
    globalThis.ttgamesRaceRead = (key, length) => { main.read(JSON.parse(key), valid(length)); };
    globalThis.ttgamesRaceWrite = (data, length) => { main.write(...JSON.parse(data), valid(length)); };
    globalThis.ttgamesRaceRevision = key => main.status(JSON.parse(key)).revision;
    globalThis.ttgamesRaceStatus = key => JSON.stringify(main.status(JSON.parse(key)));
})();
