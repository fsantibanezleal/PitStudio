# sdg-cc0-textures

The CC0 colour maps that texture the bench rock, the haul roads and the rock of the SDG frames (spec 009, FR-009-08; spec 004 FR-004-26).

| Item | Value |
|---|---|
| Producers | ambientCG (https://ambientcg.com) and Poly Haven (https://polyhaven.com) |
| Licence | CC0 1.0 for both; the licence pages are saved in the data root under `raw/textures/<source>/LICENSE-page.html` with their SHA-256 in `raw/textures/manifest.json` (`licence_evidence`) |
| Files used | the 1K colour map of each set (ambientCG `*_Color.jpg` inside the 1K-JPG archive, Poly Haven `Diffuse` 1k jpg); SHA-256 of each map in the table below and of each archive in `data/sources.yaml` |
| Access | the publishers' public APIs (`https://ambientcg.com/api/v2/full_json`, `https://api.polyhaven.com/files/<asset>`), fetched 2026-11-23 by `tools/sdg_inputs.py textures` |
| Where it lives | the data root, `raw/textures/` (never committed) |

## Choice: arid rock without vegetation tint

The first pool (sdg-inputs, 2026-10-13) held `Rock063`, `Rock064`, `Ground068` and `aerial_rocks_01`, whose colour maps show yellow-green moss and lichen: the share of pixels with hue 60 to 150 degrees and saturation above 0.25 is 18.8, 3.0, 3.2 and 4.5 percent, and the bench rock rendered mossy. Fifty-nine candidate sets (ambientCG Rock and Ground sets, Poly Haven rock textures) were measured on the colour map reduced to 512 by 512 pixels; the pool keeps sets with a tint below 2 percent (the limit `TINT_LIMIT_PCT` of the tool, which refuses a texture at or above it). Lithology lists: quartz monzonite (pale grey to pink-grey: Rock023, Rock027, Rock026, `rock_boulder_dry`) and limestone (grey to buff: Rock058, Rock054, `rock_boulder_cracked`, `worn_rock_natural_01`, `rock_wall_11`). The bench rock material is `rock_boulder_dry`. No set is matched to the Bingham Canyon geology; they are generic arid rock surfaces (UNVERIFIED as lithologically representative).

| Texture id | Asset | Source | SHA-256 of the colour map | Vegetation tint (percent) |
|---|---|---|---|---|
| `ambientcg-rock023` | Rock023 | ambientcg | `4406a3a28fa0edd2734cf08c0720ef84d5edd1a4cf035f4c9e56de6c905151ff` | 0.000 |
| `ambientcg-rock027` | Rock027 | ambientcg | `d86c2b71384cab25ab6498b50e88842af681b08640ecc8d832923f03b9f6dc6e` | 0.000 |
| `ambientcg-rock026` | Rock026 | ambientcg | `6f2595c1a1e96b5cb69855787386e5d8804e29a0bc2074cbca572fb920afc7d6` | 0.001 |
| `ambientcg-rock024` | Rock024 | ambientcg | `e07e1d804c6851cc84d5e74e0ad3f46bd68f087e1676a2b1cbdaf7882f8148b1` | 0.005 |
| `ambientcg-rock058` | Rock058 | ambientcg | `ba46be27557942876629de570ce6d674d92a4bf32f8514fca0ca05510860df53` | 0.000 |
| `ambientcg-rock025` | Rock025 | ambientcg | `4db440e006640d37b8a93cdf7d526b4a9f13923d1248f4d901cb5416ebbfeb10` | 0.000 |
| `ambientcg-rock051` | Rock051 | ambientcg | `92bdd9212a6d5c6dcc7a143130e51f8b2eceeb1410825714e1565b1bc1102445` | 0.000 |
| `ambientcg-rock054` | Rock054 | ambientcg | `da4507440a11374b449820eb0f0f6ed852ce51e18c27b3257806d51de8ecc0ee` | 0.000 |
| `ambientcg-rock060` | Rock060 | ambientcg | `0badf4e433aa96102c3beaeadb08ae4a9510d374ee251ddbf3ae77f73efaddad` | 0.000 |
| `polyhaven-rock-boulder-cracked` | rock_boulder_cracked | polyhaven | `e88c9e50109c7f610bc380a00b9bdac5954c392bb02134dedeea3358da57276a` | 0.000 |
| `polyhaven-rock-boulder-dry` | rock_boulder_dry | polyhaven | `20f653a42fb24f42aa40641663070d578678da49af18cc1049dbdd4ed8679f3c` | 0.000 |
| `polyhaven-worn-rock-natural-01` | worn_rock_natural_01 | polyhaven | `ef6c74732c61974c5df7f0f7185e7d6a97308198bf10aec7a0e95e953a617d9e` | 0.000 |
| `polyhaven-rock-wall-11` | rock_wall_11 | polyhaven | `850f45c4ea8692c4ea990a2bb8b673cb1a94a2240c4a5dedab5d8a3d695256f6` | 0.000 |
| `polyhaven-rock-face-03` | rock_face_03 | polyhaven | `ea48e0e47ad42c8bd312476178b1248ec66f0eb19156a26a1c222f2a40caaf2d` | 0.000 |
| `polyhaven-quarry-wall` | quarry_wall | polyhaven | `929c85d9acf3a3949bd271cd310d2c892ec8756d575b39861f179be31a41ad49` | 0.000 |
| `polyhaven-dry-riverbed-rock` | dry_riverbed_rock | polyhaven | `5dc1fd5777f613451a703d2fc292d4a4e79987f90b991efa98c7ca02458c6a8a` | 0.000 |
| `polyhaven-gravel-ground-01` | gravel_ground_01 | polyhaven | `c3a12b0e3a9399913158dd5cfa1d67ede066970acd1f99e5b89969ac13f89089` | 0.000 |

## Known biases and limits

- Generic CC0 surfaces photographed elsewhere, 1K resolution, colour map only (no normal or roughness map in the SDG renderer).
- Shadows and highlights of the photographs are baked into the colour map and show under every rendered light.
- The tint measure is a colour statistic on a reduced image; it removes yellow-green growth, it does not prove that a surface is geologically right.

## Use and leakage

The structured arm draws rock textures from a lithology list; the unstructured arm draws from the whole pool (FR-009-08). The textures are inputs of the renderer, never labels; a detector is not trained on a texture alone.
