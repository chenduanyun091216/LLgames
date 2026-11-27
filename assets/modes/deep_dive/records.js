(() => {
    const stores = new Map();
    function records(name) {
        if (stores.has(name)) return stores.get(name);
        const state = {error: false, data: {discovered: [], best: {}}};
        let db;
        function open() {
            if (db) return Promise.resolve(db);
            return new Promise((resolve, reject) => {
                const request = indexedDB.open(name, 1);
                request.onupgradeneeded = () => {
                    request.result.createObjectStore('receipts');
                    request.result.createObjectStore('catalog');
                    request.result.createObjectStore('best');
                };
                request.onsuccess = () => {
                    db = request.result;
                    db.onversionchange = () => { db.close(); db = null; };
                    resolve(db);
                };
                request.onerror = request.onblocked = () => reject(request.error);
            });
        }
        async function transact(mode, operation) {
            try {
                const connection = await open();
                await new Promise((resolve, reject) => {
                    const tx = connection.transaction(['receipts', 'catalog', 'best'], mode);
                    tx.oncomplete = resolve;
                    tx.onabort = tx.onerror = () => reject(tx.error);
                    operation(tx);
                });
                return true;
            } catch {
                state.error = true;
                return false;
            }
        }
        async function read() {
            await transact('readonly', tx => {
                const catalog = tx.objectStore('catalog').getAllKeys();
                catalog.onsuccess = () => { state.data.discovered = [...new Set([...state.data.discovered,...catalog.result])]; };
                const best = {};
                const cursor = tx.objectStore('best').openCursor();
                cursor.onsuccess = () => {
                    const item = cursor.result;
                    if (item) {
                        if (typeof item.key === 'string') best[item.key] = item.value;
                        item.continue();
                    }
                    else for (const [sea,value] of Object.entries(best))
                        state.data.best[sea] = Math.max(state.data.best[sea] ?? 0,value);
                };
            });
        }
        async function write(run, sea, receipts, safe) {
            if (await transact('readwrite', tx => {
                const table = tx.objectStore('receipts');
                const catalog = tx.objectStore('catalog');
                for (const [instance, treasure, value] of receipts) {
                    table.put(value, [run, instance]);
                    catalog.put(true, treasure);
                }
                if (safe) {
                    const values = table.getAll(IDBKeyRange.bound([run, ''], [run, '\uffff']));
                    const best = tx.objectStore('best');
                    values.onsuccess = () => {
                        const previous = best.get(sea);
                        previous.onsuccess = () => {
                            const income = values.result.reduce((total, value) => total + value, 0);
                            best.put(Math.max(previous.result ?? 0, income), sea);
                        };
                    };
                }
            })) {
                state.error = false;
                await read();
            }
        }
        // Serialize reads and writes from this page. IndexedDB serializes readwrite transactions across tabs.
        let queue = Promise.resolve();
        const store = {state, read: () => { queue = queue.then(read); },
            write: (run, sea, receipts, safe) => {
                state.data.discovered = [...new Set([...state.data.discovered, ...receipts.map(row => row[1])])];
                if (safe) {
                    const value = receipts.reduce((sum,row) => sum+row[2],0);
                    state.data.best[sea] = Math.max(state.data.best[sea] ?? 0,value);
                }
                queue = queue.then(() => write(run, sea, receipts, safe));
            }};
        stores.set(name,store);
        return store;
    }
    globalThis.ttgamesDiveRecords = records;
    const main = records('ttgames-main-modes');
    globalThis.ttgamesDiveRead = () => main.read();
    globalThis.ttgamesDiveWrite = data => main.write(...JSON.parse(data));
    globalThis.ttgamesDiveStatus = () => JSON.stringify(main.state);
})();
