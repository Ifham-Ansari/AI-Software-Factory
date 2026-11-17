# AI Software Factory brand

<p>
  <img src="asf-mark.svg" width="96" alt="AI Software Factory mark">
  &nbsp;
  <img src="asf-logo-light.svg" width="420" alt="AI Software Factory logo">
</p>

## The mark

A factory on a blue-to-violet tile. Three linked dots inside are the agents working along one production line, and the spark above the roof is the AI. The mark should read as a factory down to 16 px. At favicon sizes the three dots merge into one bar (`favicon.svg`, `favicon-16x16.png`).

## Colors

| Token | Hex | Use |
|---|---|---|
| Factory blue | `#3366FF` | Gradient start (top left), links on dark |
| Factory violet | `#8A3FFC` | Gradient end (bottom right) |
| Line mid | `#5F52FE` | The agents' line and the middle dot |
| Ink | `#0B0D17` | Wordmark on light backgrounds, dark surfaces, `theme-color` |
| White | `#F7F8FC` | Wordmark on dark backgrounds |
| "AI" on dark | `#7B9BFF` → `#B58CFF` | Lighter gradient so "AI" keeps contrast on ink |
| Dashboard accent | `#4338CA` light / `#A5B4FC` dark | Links, focus rings, and highlights in the dashboard (`packages/dashboard/src/styles.css`) |

The gradient always runs diagonally from top left (blue) to bottom right (violet).

## Wordmark

**AI Software Factory**, set in Inter ExtraBold (SIL Open Font License) with slightly tightened tracking, and outlined to paths so no font is needed. "AI" carries the brand gradient, and "Software Factory" is ink (light backgrounds) or white (dark backgrounds). In running text, write the name as **AI Software Factory**, and use `asf` only for the command, folders, and code identifiers.

## Files

| File | Size | Use |
|---|---|---|
| `asf-mark.svg` | vector | Icon only, rounded tile |
| `asf-mark-512.png`, `asf-mark-1024.png` | 512, 1024 px | Icon only, raster |
| `asf-logo-light.svg` / `.png` | 1098 × 170 (PNG at 2×) | Mark and wordmark for **light** backgrounds |
| `asf-logo-dark.svg` / `.png` | 1098 × 170 (PNG at 2×) | Mark and wordmark for **dark** backgrounds |
| `og-image.png` | 1200 × 630 | Social preview (GitHub repository settings → Social preview) |
| `favicon.svg` | vector | Browser tab icon (simplified for small sizes) |
| `favicon.ico` | 16, 32, 48 px | Legacy favicon |
| `favicon-16x16.png`, `favicon-32x32.png` | 16, 32 px | PNG favicons |
| `apple-touch-icon.png` | 180 px | iOS home screen (full bleed, iOS rounds the corners) |
| `android-chrome-192.png`, `android-chrome-512.png` | 192, 512 px | Android and PWA icons |

The dashboard ships copies of the favicon set in `packages/dashboard/public/`, and draws the mark inline in its header (`Logo` in `packages/dashboard/src/components/Shell.tsx`). If you change the mark, update all three places.

## Using the logo

* In a GitHub README, switch versions with the theme:

  ```html
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/asf-logo-dark.svg">
    <img alt="AI Software Factory" src="docs/brand/asf-logo-light.svg" width="460">
  </picture>
  ```

* Leave clear space around the logo of at least half the mark's height.
* Don't recolor, stretch, rotate, or outline the mark, and don't put the full-color tile on a busy photo.
* Below 24 px, use `favicon.svg` instead of `asf-mark.svg`.

## Favicon snippet

Put the favicon files in your web root (or a Next.js `public/` folder):

```html
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#0B0D17">
```
