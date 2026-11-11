const poster = [
    [1, 69, 17, 17], [17, 74, 18, 16], [33, 77, 17, 15], [50, 77, 17, 15],
    [66, 74, 18, 16], [82, 69, 17, 17], [0, 40, 28, 30], [76, 45, 24, 25],
    [22, 48, 30, 28], [51, 47, 29, 28], [8, 0, 84, 62],
];

function bossArt(data, index) {
    const boss = data.bosses[data.levels[index].boss_idx];
    return './art/' + (boss.sprite_asset?.replace(/\.png$/, '') ?? 'bosses/' + boss.key) + '.webp';
}

function chapterArt(index) {
    const x = index % 4 * 100 / 3;
    const y = Math.floor(index / 4) * 50;
    return '<span aria-hidden="true" class="chapter-art" style="--chapter-x:' + x
        + '%;--chapter-y:' + y + '%"></span>';
}

export function homeContent(data, button, offline, downloading) {
    const bosses = [10, 6, 7, 8, 9, 0, 1, 2, 3, 4, 5].map(index => {
        const [x, y, w, h] = poster[index];
        return '<img alt="" src="' + bossArt(data, index) + '" style="left:' + x
            + '%;top:' + y + '%;width:' + w + '%;height:' + h + '%">';
    }).join('');
    const players = ['fire', 'ice', null, 'water', 'radiation'].map(key => '<img alt="" src="./art/'
        + (key ? 'animations/players/anim_player_' + key + '_back' : 'players/player1') + '.webp">').join('');
    return '<div class="home-title"><img src="./art/ui/title.webp" alt="海洋生物入侵"></div>'
        + '<div class="home-poster" aria-hidden="true"><div class="home-bosses">' + bosses
        + '</div><div class="home-team">' + players + '</div></div>'
        + '<div class="home-actions">' + button('select', '开始游戏 →', true)
        + button('offline', downloading ? '正在保存…' : '保存离线资源')
        + '<div class="hint" role="status">' + offline + '</div></div>';
}

export function campaignContent(data, selected, tier, button) {
    const level = data.levels[selected - 1];
    const boss = data.bosses[level.boss_idx];
    const reward = data.CAMPAIGN_REWARDS[selected - 1];
    const levels = data.levels.map(l => '<button type="button" class="level" data-action="level-' + l.level
        + '" aria-pressed="' + (selected === l.level) + '">' + chapterArt(l.level - 1)
        + '<b>' + String(l.level).padStart(2, '0') + '</b><span>' + l.title + '</span></button>').join('');
    const tiers = data.difficulty.map((d, i) => '<button type="button" data-action="tier-' + i
        + '" aria-pressed="' + (tier === i) + '">' + d.name + '</button>').join('');
    return '<nav class="campaign-nav">' + button('menu', '← 首页') + button('shop-menu', '商店') + '</nav>'
        + '<div class="campaign-header"><h2>战役选关</h2><div class="tiers" aria-label="难度">' + tiers + '</div></div>'
        + '<div class="campaign-body"><div class="levels">' + levels + '</div>'
        + '<div class="campaign-detail">' + chapterArt(selected - 1)
        + '<img src="' + bossArt(data, selected - 1) + '" alt="">'
        + '<div class="chapter-description"><h3>' + level.title + '</h3>'
        + '<p>首领 · ' + boss.name + (reward ? ' / +' + reward + ' 金币' : '') + '</p>'
        + button('start', '出击 →', true) + '</div></div></div>'
        + '<footer class="campaign-footer">' + button('endless', '无限模式') + button('custom', '自定义难度') + '</footer>';
}
