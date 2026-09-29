# Social assets

| File | What it is | Rebuild |
|---|---|---|
| `kubeflight-share-card.png` | 1200×630 card: the README hero and Open Graph preview | `./docs/social/build-social-card.sh` |
| `kubeflight-social-card.html` / `.jpg` | 1600×900 (16:9) card for LinkedIn and X: the product story in five steps | same script |
| `kubeflight-share-card.html` | Source for the 1200×630 share card | same script |

Needs Google Chrome and macOS `sips` (already on a Mac); nothing is installed.

Every claim on the social card is already sourced in the project README and docs.
Licence wording follows `LICENSE`: Apache License 2.0.

## Palette

Apple.com system palette, matching this site's own `docs/stylesheets/apple-glass.css`:

- Light: `#ffffff` / `#f5f5f7` background, `#d2d2d7` hairline, `#1d1d1f` ink, `#6e6e73` secondary text.
- Blue (dominant brand color): gradient `#0071e3` → `#2997ff`.
- Dark surfaces (attribution bar, footnotes): `#1d1d1f` background, `#f5f5f7` text.
- Zyvor orange `#f97316` appears exactly once per card, as a small accent dot — never as a background or primary color.
- Zyvor "Z" mark (`zyvor-mark.svg`): blue gradient `#0071e3` → `#2997ff`.
- Type: Helvetica Neue (sans) and SF Mono/Menlo (mono), unchanged.
