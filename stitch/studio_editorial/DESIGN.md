---
name: Studio Editorial
colors:
  surface: '#fbf9f7'
  surface-dim: '#dbdad8'
  surface-bright: '#fbf9f7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3f1'
  surface-container: '#efedec'
  surface-container-high: '#eae8e6'
  surface-container-highest: '#e4e2e0'
  on-surface: '#1b1c1b'
  on-surface-variant: '#53433f'
  inverse-surface: '#30302f'
  inverse-on-surface: '#f2f0ee'
  outline: '#86736e'
  outline-variant: '#d9c1bc'
  surface-tint: '#8e4c3b'
  primary: '#8e4c3b'
  on-primary: '#ffffff'
  primary-container: '#cc7e6b'
  on-primary-container: '#4e1a0e'
  inverse-primary: '#ffb4a2'
  secondary: '#655d55'
  on-secondary: '#ffffff'
  secondary-container: '#e9ded4'
  on-secondary-container: '#696159'
  tertiary: '#5f5e5e'
  on-tertiary: '#ffffff'
  tertiary-container: '#939292'
  on-tertiary-container: '#2b2b2b'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdad2'
  primary-fixed-dim: '#ffb4a2'
  on-primary-fixed: '#3a0b02'
  on-primary-fixed-variant: '#723526'
  secondary-fixed: '#ece0d7'
  secondary-fixed-dim: '#d0c5bb'
  on-secondary-fixed: '#201b15'
  on-secondary-fixed-variant: '#4d463e'
  tertiary-fixed: '#e4e2e1'
  tertiary-fixed-dim: '#c8c6c6'
  on-tertiary-fixed: '#1b1c1c'
  on-tertiary-fixed-variant: '#474747'
  background: '#fbf9f7'
  on-background: '#1b1c1b'
  surface-variant: '#e4e2e0'
typography:
  display-lg:
    fontFamily: Newsreader
    fontSize: 48px
    fontWeight: '600'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Newsreader
    fontSize: 32px
    fontWeight: '500'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Newsreader
    fontSize: 28px
    fontWeight: '500'
    lineHeight: 36px
  headline-md:
    fontFamily: Newsreader
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
  body-lg:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Hanken Grotesk
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-max: 1280px
  gutter: 24px
  margin-desktop: 48px
  margin-mobile: 20px
---

## Brand & Style
The design system is built for a professional creator demographic—specifically women in their 30s and 40s—who value efficiency and high-end aesthetics over tech-heavy complexity. The brand personality is **Helpful, Professional, and Creative**, aiming for a "Human-First" editorial feeling that distances itself from typical AI-generated interfaces.

The design style is **Modern Editorial**. It prioritizes high-quality typography, generous whitespace, and a tactile sense of depth. It avoids futuristic neon accents or synthetic blurs in favor of organic textures, structured layouts, and a "physical paper" quality. The interface should feel like a premium lifestyle magazine that happens to be a powerful video creation tool.

## Colors
This design system utilizes a warm, grounded palette to establish trust and a premium feel. 

- **Primary (Soft Terracotta):** Used for primary actions and key brand moments. It is energetic yet sophisticated.
- **Secondary (Warm Linen):** The foundational surface color, providing a softer, more organic feel than pure white.
- **Tertiary (Elegant Charcoal):** Used for primary text and high-contrast UI elements to ensure grounded authority.
- **Accents (Peach Fuzz/Soft Rose):** Reserved for subtle highlights, "new" indicators, or soft promotional tags.

Avoid any high-saturation blues or purples typically associated with AI. All surface transitions should be low-contrast to maintain a calm, professional atmosphere.

## Typography
The typography strategy employs a high-contrast pairing between a literary serif and a contemporary sans-serif.

- **Newsreader** is the primary voice for storytelling, headlines, and "editorial moments." It provides the "non-AI," human-authored feel. Use Medium and SemiBold weights to maintain readability on screens.
- **Hanken Grotesk** handles the utilitarian work. It is chosen for its exceptional legibility and modern, clean geometry. It stays out of the way, ensuring that the shopping data and creation tools are easy to navigate.

For mobile layouts, keep serif headlines tight and avoid overly large display sizes that might break the sophisticated rhythm of the page.

## Layout & Spacing
The layout follows a **Fixed Grid** model for desktop to maintain a curated, editorial feel, while transitioning to a fluid model for mobile.

- **Desktop:** 12-column grid with wide 48px margins to allow the content to "breathe."
- **Tablet:** 8-column grid with 32px margins.
- **Mobile:** 4-column grid with 20px margins.

Spacing follows an 8px base rhythm, but use 4px increments for tight UI clusters (like input labels and fields). Generous vertical padding between sections is encouraged to emphasize the premium, unhurried nature of the brand.

## Elevation & Depth
The design system uses **Tonal Layers** combined with **Ambient Shadows**. 

Avoid heavy dropshadows. Instead, use "Soft Lift" effects: low-opacity (8-12%), large blur radii (16px-24px), often tinted with a hint of the Primary or Neutral color rather than pure black. This creates a soft, tactile depth that feels like layers of high-quality paper or matte-finish physical products.

Surface hierarchy:
- **Level 0 (Base):** Warm Linen (`#F7EBE1`).
- **Level 1 (Cards/Containers):** Off-white or Neutral (`#F9F7F5`) with a subtle 1px border in a slightly darker neutral.
- **Level 2 (Floating/Modals):** Pure white with a Soft Lift shadow.

## Shapes
The shape language is defined by **Softness and Intent**. 

A base roundedness of 12px is applied to standard UI elements like buttons and input fields. Larger containers, such as product cards and video preview frames, should use 16px to 24px (rounded-lg or rounded-xl) to emphasize a friendly, approachable aesthetic.

Iconography should follow this rounded theme—avoid sharp edges or "techy" geometric icons. Use a consistent stroke weight (1.5px to 2px) with rounded caps and joins.

## Components

- **Buttons:** Use a "Tactile" style. Primary buttons are Terracotta with white text, featuring a subtle inner-shadow to appear slightly pressed and a 12px corner radius. Secondary buttons use an outline or the Warm Linen background with Charcoal text.
- **Product Chips:** Small, pill-shaped tags used for video categorization or shopping tags. Use Soft Rose or Peach Fuzz backgrounds with low-opacity text.
- **Input Fields:** Large and clear with 16px vertical padding. The border should be a subtle grey that transitions to Terracotta on focus. 
- **Cards:** Product and video cards should have a 16px corner radius and a "Soft Lift" shadow. Ensure a clear separation between the image area and the metadata (price, title) using the Newsreader serif for titles.
- **Video Timeline:** A specialized component using Charcoal for the track and Terracotta for the playhead. Use rounded handles to reinforce the tactile theme.
- **Lists:** Use generous line heights (1.6) and subtle horizontal dividers in a very light neutral tone to maintain the editorial rhythm.