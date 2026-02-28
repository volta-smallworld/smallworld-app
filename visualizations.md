# Pipeline Visualizations

10 algorithm animations to show during processing.

1. **Flow accumulation (ridgelines + streams)** — Water particles flowing uphill along ridgelines on the inverted DEM, branching like a river network in reverse. Flip and show streams forming downhill.

2. **Viewshed ray-casting** — Rays fan out from camera across terrain like a radar sweep. Visible cells light up, occluded cells go dark as each ray hits blocking terrain.

3. **Inverse PnP solve** — Composition grid overlaid on a frame, terrain features labeled in 3D. Camera flies to the exact position where features land on grid intersections.

4. **Skyline fractal dimension** — 1D skyline profile extracted from rays, then progressively smaller box grids overlay the profile. Boxes light up on contact, D value converges toward 1.3.

5. **Shadow casting timelapse** — Shadow map evolving across terrain as the sun moves sunrise to sunset. Shadows stretch, rotate, shrink. Score graph peaks at golden hour.

6. **CMA-ES population evolution** — 8 camera dots on terrain, clustering tighter each generation. Covariance ellipse shrinks and rotates as it homes in. Beauty score climbs alongside.

7. **Contour topology matching** — Sliding window scans the DEM, each patch's contours flash red/green against the reference fingerprint. Match hits zoom in to show contour alignment.

8. **Prospect-refuge balance** — Viewshed area expanding outward (prospect, blue) vs. terrain above horizon closing in (refuge, warm). Harmonic mean bar fills as both balance.

9. **Interest map construction** — Raw elevation, then peaks glow, ridgelines light up, cliffs highlight, water shimmers, relief warms — each layer stacking into the final heatmap.

10. **Style fingerprint gradient ascent** — Camera nudges incrementally, projected contour lines shift each step, similarity score ticks upward, projected view morphs toward the reference image side-by-side.
