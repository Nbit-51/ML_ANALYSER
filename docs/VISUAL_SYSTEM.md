# The Living Experiment Engine

## Architecture and storyboard

The FastAPI `/` route serves a standalone cinematic landing page. `/app`, `/login`, session handling and all experiment APIs remain separate. The page explains **Evidence Before Claims** with a single persistent scene. No scene interaction executes a repository or calls a model.

1. **Initialize / hero:** scattered point positions converge into a procedural experiment graph. The headline reveals after the first visual beat; both navigation actions are ordinary links and work before graphics initialize.
2. **Inspect / repository:** scrolling moves the camera into the graph. The selected node explains detected, declared and measured evidence; lightweight file rows reference committed fixtures.
3. **Branch / experiment:** a baseline fans into candidate paths. Selecting accepted/rejected/inconclusive scenarios changes branch colors and the diagnostic explanation. These are explicitly illustrative scenarios.
4. **Compare / benchmark:** a holographic comparison exposes deterministic reference values from the regression and CLI fixtures. Metric selection updates bars, direction, delta and provenance. No timing or live-execution claim is made.
5. **Approve / safety:** a restrained Fresnel envelope appears around the graph. A disclosure shows the exact kinds of fields bound by approval and the actual execution limits.
6. **Trace / evidence:** the scene settles around the evidence node; selectable ledger steps explain how an experiment becomes a retained report. A simple visible DAG connects original, candidate and verdict.
7. **Launch:** the final CTA opens the real workbench; the secondary action opens an offline demo.

## Modules

- `frontend/landing.html`: semantic content, navigation, accessible graph selectors, illustration labels and static SVG fallback.
- `frontend/landing.css`: black/cyan/violet/amber visual language, typography, holographic panels, responsive layout and motion overrides. It does not alter workbench styles.
- `frontend/engine-data.mjs`: seeded graph generation, concept definitions, fixture reference values and comparison transformations; independently tested in Node.
- `frontend/engine-scene.mjs`: Three.js rendering, shader particles, animated line pulses, projected node labels, camera interpolation and bounded bloom.
- `frontend/landing.mjs`: accessible interactions, lazy graphics initialization, GSAP/ScrollTrigger choreography, pause/reduced-motion handling and cleanup.
- `frontend/vendor/`: pinned library distributions and licenses, reproducibly copied by `npm ci --ignore-scripts && npm run vendor:landing`.

## Rendering budget and fallbacks

Point clouds batch thousands of particles into a small number of draw calls. Graph nodes/edges are bounded; no per-node geometry or network-fetched 3D assets are used. Device pixel ratio is capped, mobile uses fewer particles and skips postprocessing, and a frame cap limits continuous rendering. Hidden tabs stop the loop. Context loss disposes the scene and exposes the static fallback. Reduced motion begins with a still diagram and disables scroll/camera transitions; users can explicitly enable animation. Navigation, copy, comparison controls, keyboard node selection and the real workbench remain usable without WebGL. JavaScript-disabled users retain the complete document and static charts.

## Reference values and provenance

The regression fixture predicts `[1,2,3,4] + bias`: bias 2 produces RMSE 2; bias 0 produces RMSE 0. The CLI fixture executes redundant work 100 versus 10 times, preserving its checksum. Those are fixture reference values, not a freshly executed benchmark or a general speedup. The landing page never fetches private run reports or reuses a signed-in user's measurements for marketing.

## Design references

The reference study used [Ability AI / Trinity](https://www.ability.ai/trinity), [Space and Time](https://www.awwwards.com/sites/space-and-time), [Codrops demos](https://tympanus.net/codrops/demos/) and [the Cerebrium case study](https://tympanus.net/codrops/2026/07/23/building-cerebrium-making-serverless-infrastructure-tangible/). Their spatial storytelling and readable technical interactions informed the approach; no branding, assets or page layouts were copied. The implementation uses [Three.js](https://threejs.org/) and [GSAP ScrollTrigger](https://gsap.com/docs/v3/Plugins/ScrollTrigger/).

## Verification and review controls

Validated on 2026-10-15 at desktop (1440×1000) and mobile (390×844) viewport settings. The desktop WebGL2 scene initialized with no console or shader warnings. Graph selection, scroll links, all three outcome scenarios, both fixture comparisons, provenance disclosures and workbench navigation were exercised. Keyboard activation updated the concept explanation. Mobile overflow was corrected and checked against document width.

`?motion=reduce` exercises the still-view controller used for reduced motion; native `prefers-reduced-motion` is also observed, including changes while the page is open. `?graphics=off` exercises the same static presentation available when graphics cannot initialize. These are local review controls, not claims that a device's actual GPU was disabled. The canvas declares its configured particle count, frame cap, pixel ratio and initial draw calls as DOM data attributes for inspection. Desktop uses 4,627 points and a 45 fps cap, with DPR capped at 1.5. Initial mobile scenes use 1,747 points, a 30 fps cap and DPR capped at 1, without the bloom pass. These are budgets, not measured universal frame rates.

The browser also completed the actual regression workflow: select saved project → declared RMSE goal → preview → prepare → approve → measured accepted result → reopen saved report → download JSON. Those measured workbench results are separate from the landing's labeled reference data.

The automated suite covers seeded graph bounds/reproducibility, fixture comparison semantics, uncertainty, accessible concept metadata, local dependency availability, account isolation, legacy report reconstruction and browser-style numeric serialization. CI checks all new scripts and runs all frontend tests. Dependencies are pinned to Three.js 0.180.0 and GSAP 3.13.0; upstream copyright headers, the Three.js MIT license and the GSAP license notice are preserved under `frontend/vendor/`.
