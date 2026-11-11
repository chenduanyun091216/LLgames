export const weapons = ['pistol', 'rifle', 'shotgun', 'sniper'];
export const characters = ['ice', 'water', 'fire', 'radiation'];

export function controlLayout({canvasWidth: width, height, offset}) {
    const compact = height < 500;
    const gap = compact ? 70 : 76;
    const right = width - (compact ? 42 : 48);
    const fireY = height - (compact ? 72 : 80);
    const arc = compact ? 88 : 96;
    const shortArc = compact ? 32 : 35;
    const utilityY = compact ? 40 : 48;
    const utility = compact ? 22 : 27;
    const skill = compact ? 24 : 28;
    const weaponY = height - (compact ? 191 : 270);
    const charY = compact ? 102 : offset ? 145 : 222;
    const result = {
        shop: [right - gap, utilityY, utility], pause: [right, utilityY, utility],
        attack: [right, fireY, compact ? 34 : 36], auto: [right - 78, fireY + 36, compact ? 24 : 25],
        skill0: [right - arc, fireY - shortArc, skill], skill1: [right - shortArc, fireY - arc, skill],
        skill2: [right - 174, fireY - gap, utility], skill3: [right - 174, fireY, utility],
    };
    weapons.forEach((key, index) => {
        result[key] = [index % 2 ? (compact ? 104 : 136) : (compact ? 36 : 56),
            weaponY - (index < 2 ? (compact ? 66 : 78) : 0), compact ? 24 : 30];
    });
    characters.forEach((key, index) => {
        result[key] = [index % 2 ? right : right - gap,
            charY + (index < 2 ? 0 : compact ? 62 : 67), compact ? 21 : 25];
    });
    return result;
}
