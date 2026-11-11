# Factory and ancient temple campaign artwork

All 18 new images were created individually with OpenAI's built-in image generation tool. Existing `backgrounds/bg9.png` was preserved byte-for-byte as `backgrounds/bg11.png` before replacement. No game-effect artwork was drawn with canvas or procedural shapes.

## Art direction and prompt set

Shared direction: polished hand-painted, colorful 2D underwater arcade fantasy; clean dark outlines, cel-shaded highlights, strong silhouettes, no writing or watermarks. Characters and effects were requested with genuine transparent backgrounds. Backgrounds use open central dark water to preserve combat readability.

- `backgrounds/bg9.png`: submerged abandoned industrial factory, rusted pipes and turbine, broken smokestacks, copper metal, cyan reactor windows and coral; structures at bottom and sides, underwater light shafts.
- `backgrounds/bg10.png`: submerged ancient temple, turquoise pillars, gold-and-jade altar, stairs and whale reliefs, violet coral, blue water and light shafts; open center.
- `enemies/enemy_mecha_crab.png`: front-facing copper and steel crab, hydraulic pincers, six mechanical legs, orange eyes and cyan reactor.
- `enemies/enemy_mecha_ray.png`: overhead downward-facing mechanical manta, swept steel/copper wings, cyan edges and orange reactor eye.
- `enemies/enemy_mecha_jelly.png`: copper/violet domed jellyfish, cyan glass core, five curled cable tentacles and electric tips.
- `enemies/enemy_ancient_nautilus.png`: turquoise spiral shell, carved gold bands, purple face, bright aqua eyes, curled tentacles.
- `enemies/enemy_ancient_trilobite.png`: overhead downward-facing segmented jade fossil armor, gold edges, amber eyes and short legs.
- `enemies/enemy_ancient_ray.png`: overhead downward-facing purple/blue manta guardian, gold fossil markings, luminous turquoise wing tips.
- `bosses/boss_mecha_lizard.png`: full armored mechanical lizard, four hydraulic claws, curled armored tail, cyan plasma mouth, orange eyes, bronze dorsal fins and shoulder missile pods.
- `bosses/boss_ancient_whale.png`: chibi indigo whale with carved sandstone brows, turquoise runes, and a moss-covered temple gate on its back. An open mouth draws in a storm.
- `animations/bosses/anim_boss_ancient_whale.png`: 8 frames each for swimming, tidal crescent, rune geyser, ancient pearl, suction, and swallowing. Each motion occupies one row of eight square cells.
- `effects/mecha_plasma_rail.png`: vertical white-hot plasma beam, cyan electric filaments, blue glow and small orange sparks.
- `effects/mecha_guided_missile.png`: downward copper/gunmetal torpedo with cyan nose and orange/cyan exhaust above.
- `effects/mecha_emp_ring.png`: perfectly front-on narrow cyan/white electric circle, transparent center and exterior.
- `effects/mecha_molten_burst.png`: orange molten reactor orb, white/gold core, dark red lava ribbons, compact flame corona.
- `effects/whale_tidal_crescent.png`: downward-moving aqua crescent, white frothy lower convex leading edge, upturned ends and transparent upper concavity.
- `effects/whale_rune_geyser.png`: tall aqua geyser, twisting water streams, white foam and gold spiral energy above a rune pedestal.
- `effects/whale_ancient_pearl.png`: ivory magical pearl, turquoise/violet iridescence, thin gold orbit rings and soft blue halo.

## Production preparation and validation

Character sprites were cropped to visible alpha bounds and downsampled with Lanczos: enemies at most 384 pixels, bosses at most 768 pixels. Effects were cropped using alpha >= 12, retaining 1.5% glow padding; rings were centered in square canvases. Tall beams/geysers are at most 768 pixels; other effects at most 512 pixels. Original generated alpha was preserved. Backgrounds are 1448 x 1086 RGB PNGs. New assets total about 9.93 MB.

All 18 original files were visually inspected in a contact sheet. Both ring center pixels have alpha 0. All character/effect files are RGBA with transparent outer space, no boxed backgrounds or watermarks. Gameplay should preserve missile/beam aspect ratios and anchor collision to visible art, rather than treating each PNG as a square.


## Ancient whale redraw

The whale, three skill sprites, the worm, and the rift eye were redrawn using built-in image generation. The whale pose atlas adds a banking swim, side profile, front-facing open mouth, and forward lunge. Prompt details for the redrawn set follow.

- Whale and poses: indigo ancient whale, raised gold temple armor, turquoise runes, isolated front and side views on transparent alpha.
- Skills: downward aqua crescent, vertical rising rune geyser, and round pearl with gold coral veins.
- Enemies: a round indigo parasite covered in spines and a purple space tear with one pair of orange eyes.

The delivered RGBA sheets and sprites have a long edge of at least 2048 px. The generated whale, pose atlas, pearl, and worm were resized for the 2K export. The crescent, geyser, and rift eye were generated at 2172 px on the long edge.

## Chibi ancient whale skill sprites

- Tidal crescent uses lavender foam curls, glowing cyan runes, and mossy sandstone along the leading edge.
- Rune geyser rises from a carved sandstone plinth, with cyan symbols in the indigo water and a rounded foam crest.
- Ancient pearl pairs ivory and lavender cloud motifs with a sandstone band inset with turquoise runes.

## Additional factory and temple enemies

Each enemy was generated as a two-pose sheet using built-in image generation. Shared direction was a downward-facing three-quarter view, cartoon cel shading, dark outlines, and a transparent background. The normal and action poses were exported separately to `enemies/enemy_<key>.png` and `enemies/enemy_<key>_action.png` with matching canvases and a 384 px long edge.

| Key | Character and action prompt |
| --- | --- |
| `mecha_drill` | Copper and steel treaded drill crab extends its retracted drill and spins it with turquoise trails. |
| `mecha_eel` | Segmented copper eel coils around its head and lights up its cyan segments. |
| `mecha_forge` | Round iron furnace puffer opens its orange vents and extends mechanical spikes. |
| `ancient_turtle` | Jade stone turtle with gold shell trim tucks in its flippers and lights up its turquoise shell rune. |
| `ancient_seahorse` | Indigo temple seahorse with a gold crown lashes its tail and flares its fins. |
| `ancient_scallop` | Violet stone scallop with gold shell rims opens its shell to reveal a turquoise pearl. |
