// Same logical viewport and control space as game_core.config.update_mobile_view.
export function mobileView(width, height) {
    const portrait = width < height;
    const canvasWidth = portrait ? 480 : 960;
    const canvasHeight = Math.max(1, Math.round(canvasWidth * height / width));
    const controls = Math.min(150, Math.max(80, Math.floor(canvasHeight * .18)));
    return {
        width: 480,
        height: canvasHeight,
        canvasWidth,
        bottom: Math.max(1, canvasHeight - controls),
        offset: portrait ? 0 : 240,
        entityScale: portrait ? .8 : .64,
        bossScale: portrait ? .8 : .48,
    };
}

export function fixedView(portrait) {
    const width = portrait ? 480 : 960;
    return {width, height: 720, canvasWidth: width, bottom: portrait ? 585 : 657, offset: 0,
        entityScale: 1, bossScale: portrait ? .81 : 1};
}
