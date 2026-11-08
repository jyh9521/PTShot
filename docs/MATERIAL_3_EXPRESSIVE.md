# PTShot: Material 3 Expressive implementation

The desktop UI is rebuilt rather than reskinning Tkinter. It runs locally in Electron;
the existing Python pipeline remains a separate worker reached over JSON-lines stdio.
No listening HTTP service or remote UI code is required.

## Design system

- Material 3 **Expressive**, not the older Material 2 or baseline Material 3 appearance.
- `@kyralabs/m3e-react`, `m3e-css`, `m3e-tokens` are pinned to 1.8.0. This is an independent
  implementation targeting Jetpack Compose Material3 1.5.0-beta01; it is not a Google product.
- Use the library's actual Expressive components for navigation, buttons, connected button
  groups, text fields, switches, dialogs, snackbars, and progress/loading indicators.
- Retain upstream spring motion, shape morphing, focus indicators, state layers, minimum
  interaction targets and reduced-motion behavior. Application CSS lays out components;
  it does not replace their internal states with home-made approximations.
- Use semantic color roles, Google Sans Flex (bundled), Material Symbols Rounded (bundled),
  emphasized type, container surfaces and expressive corner scale. Chinese text uses the
  local system's Chinese sans-serif fallback.
- Three main destinations: screenshot workspace, upload results, dependencies/settings.
  A compact navigation rail contains only the three named destinations; content panes scroll
  independently so actions remain reachable under Windows display scaling.
- User review: remove the design-system badge, decorative rail logo/menu, unused rail corner
  blocks, anonymous code-link button and redundant quality badge. Default to 1120×820 and
  keep the primary action outside the scroll pane. The project link lives in Settings.
- Light/dark themes, keyboard navigation, named icon buttons, visible focus and
  `prefers-reduced-motion` are validated alongside functional flows.

## Primary references

- https://m3.material.io/blog/building-with-m3-expressive
- https://m3.material.io/components/button-groups/overview
- https://m3.material.io/styles/motion
- https://m3e.kyralabs.dev/get-started/react/
- https://m3e.kyralabs.dev/foundations/
- https://github.com/kyra-labs/m3exp-web/blob/main/SOURCES.md

## Verification

Run `npm run build`, `npm test`, `npm run test:desktop`, and
`python -m unittest discover -v`. Desktop verification exercises the real Python worker,
local synthetic-video screenshot generation, result previews and clipboard copying.
Design-system tests inspect the actual rendered library components and light/dark,
compact-window and reduced-motion states, rather than claiming conformance from a screenshot.
