# biv-me template files

The files in this directory are copied **unmodified** from
[biv-me](https://github.com/UOA-Heart-Mechanics-Research/biv-me) at commit
[`d4e8010399d04a150a776af837528e31987e1cfc`](https://github.com/UOA-Heart-Mechanics-Research/biv-me/tree/d4e8010399d04a150a776af837528e31987e1cfc/src/model)
(`src/model/`), and are licensed under the Apache License 2.0 (see `LICENSE`).

| File | Content |
|---|---|
| `ETIndicesSorted.txt` | 11760 triangles (1-based node indices) of the biventricular template with 5810 nodes |
| `ETIndicesMaterials.txt` | Material label of each triangle in `ETIndicesSorted.txt` |
| `thru_wall_et_indices.txt` | 160 triangles (1-based) connecting the RV insertion line to the LV/RV epicardial seam |
| `LICENSE` | The biv-me license |

They are loaded by `ukb.template`. Do not edit them; the files are excluded from the pre-commit
hooks so that they stay byte-identical to upstream.
