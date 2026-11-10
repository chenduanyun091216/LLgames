"""Protect the LAN baseline outside the explicitly authorized campaign expansion.

This is a scope guard, not a claim that shared core/assets are unchanged.  New
campaign files are individually listed; unrelated source/assets remain guarded.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = '5f7dd20b25d0cd43eca2423ce4b1f34338b7d31d'
CAMPAIGN_FILES = {
    'README.md', 'docs/NEW_CAMPAIGN.md', 'docs/NEW_CAMPAIGN_TEST_REPORT.md',
    'assets/images/ART_FACTORY_TEMPLE.md', 'game_core/config.py', 'game_core/game.py',
    'game_core/abyss_bosses.py', 'game_core/sprites.py', 'game_core/background.py', 'game_core/entities.py',
    'pc/tests/test_new_campaign.py', 'pc/tests/test_abyss_bosses.py', 'pc/tests/test_factory_enemies.py',
    'web/tests/test_orochi.py', 'web/tests/test_mobile_web.py', 'web/tests/test_animation.py',
    'assets/images/backgrounds/bg9.png', 'assets/images/backgrounds/bg10.png',
    'assets/images/backgrounds/bg11.png',
    'assets/images/bosses/boss_mecha_lizard.png',
    'assets/images/animations/anim_boss_mecha_lizard.png',
    'assets/images/bosses/boss_ancient_whale.png',
    'assets/images/animations/anim_boss_ancient_whale.png',
}
CAMPAIGN_FILES.update('assets/images/enemies/enemy_' + key + '.png' for key in (
    'mecha_crab', 'mecha_ray', 'mecha_jelly',
    'ancient_nautilus', 'ancient_trilobite', 'ancient_ray', 'ancient_worm', 'ancient_rift'))
CAMPAIGN_FILES.update('assets/images/effects/' + key + '.png' for key in (
    'mecha_plasma_rail', 'mecha_guided_missile', 'mecha_emp_ring', 'mecha_emp_iron_ball', 'mecha_molten_burst',
    'whale_sonar_ring', 'whale_tidal_crescent', 'whale_rune_geyser', 'whale_ancient_pearl'))


def main():
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--'], cwd=ROOT, text=True).splitlines()
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    outside = sorted({path for path in changed + untracked
                      if not path.startswith('online/') and path not in CAMPAIGN_FILES})
    if outside:
        raise SystemExit('Out-of-scope changes:\n' + '\n'.join(outside))
    # The old final arena must be moved, never silently regenerated or lost.
    original = subprocess.check_output(['git', 'show', BASE + ':assets/images/backgrounds/bg9.png'], cwd=ROOT)
    if (ROOT / 'assets/images/backgrounds/bg11.png').read_bytes() != original:
        raise SystemExit('Original Orochi arena was not preserved byte-for-byte at bg11.png')
    print('PASS: all changes are online/ or explicitly listed campaign files.')
    print('Unlisted PC/Web entrypoints, dependencies, sources and assets match ' + BASE + '.')
    print('Original Orochi arena is preserved byte-for-byte at backgrounds/bg11.png.')


if __name__ == '__main__':
    main()
