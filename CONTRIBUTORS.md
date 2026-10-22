# Contributors

| Name | Email | GitHub | Role |
|---|---|---|---|
| Dmitry Stakhin | dstakhin@gmail.com | `ethene` | author of the code: the archive parse, the markout measurement, the persistence and identification tests, the quoting models and the market-making economics, the integrity checks and the reproduction notebook |

The paper this code accompanies is by Dmitry Stakhin and Saad Zaman; `CITATION.cff`
gives the reference.

## Sources

Every script opens with a header naming the sources it stands on. Where an idea, a
formula or a modelling choice comes from the literature, the source is named in the header
of the script that implements it. The trade data are the Hyperliquid node data; the open
archive of Albers, Cucuringu, Howison and Shestopaloff (Zenodo, DOI 10.5281/zenodo.18184441)
is cited in `README.md` as the public copy of the same trades.

## How this repository is kept

| Rule | This repository |
|---|---|
| Do not commit what can be regenerated | `.gitignore` excludes the large `.npz` intermediates, the raw archive caches, the per-wallet address maps, run logs and completion markers. `notebooks/wallet_toxicity_frame.csv` is the one deliberate exception, because rebuilding it needs the raw archive and credentials a reader may not have |
| Do not commit machine-specific configuration | every setting that moves a number is declared in `settings.py`; data roots, caches and narrowings by day or coin reach the code as environment variables or flags, listed in `CONFIG.md` |
| Keep credentials out | no key material is in the tree, and `.gitignore` excludes the usual credential file names at every depth |
