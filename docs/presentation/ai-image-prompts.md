# AI Image Prompts

## Slide 1: Cover background

The cover uses `layout: cover` with white title text on top of the image, so the image needs a dark, low-detail area in the center. Keep it abstract: no text, no logos, no real faces.

### DALL-E 3

```
Wide 16:9 abstract illustration for a software talk titled "Many reviewers, one verdict".
Six small glowing nodes in different soft colors (blue, teal, violet, amber, green, orange)
arranged in a loose arc on the left and right edges, each sending a thin line of light
toward a single bright point in the center, where the lines converge into one clean white beam.
Dark navy background with a faint grid of code-like dots, generous empty space in the middle
third for overlaid title text. Flat vector style, soft gradients, minimal, calm, no text,
no letters, no logos, no people.
```

### Midjourney

```
/imagine abstract flat vector illustration, six small glowing colored nodes in an arc converging their light lines into one bright white point in the center, dark navy background with faint dot grid, minimal, calm, generous negative space in the center for title text, no text, no people --ar 16:9 --v 6 --style raw
```

### Stable Diffusion

```
Positive: abstract flat vector illustration, six glowing colored nodes converging light lines into one bright central point, dark navy background, faint dot grid, minimal, soft gradients, negative space center, 16:9, high quality
Negative: text, letters, watermark, logo, people, faces, hands, clutter, photorealistic, busy background
```

**To use:**

1. Generate the image and save it as `public/images/cover-convergence.png`.
2. In `slides.md`, set `background: /images/cover-convergence.png` in the first frontmatter block.
3. Check the title contrast in the preview; if it is low, darken the image or add `class: text-center text-white`.
