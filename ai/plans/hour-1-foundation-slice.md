# smallworld — The Algorithmic Photography Angle Finder

## Hackathon Plan (5 hours)

> No tool today algorithmically analyzes terrain to find optimal photography viewpoints using composition principles. Every technical component exists independently. The integration is the innovation.

---

## What It Does

A photographer or drone pilot specifies a location and search radius. smallworld analyzes the terrain geometry and **computes** the objectively best camera angles — positions and orientations that produce compositions following the golden ratio, rule of thirds, fibonacci spirals, leading lines, and other principles of visual beauty.

It also accepts a **style reference** (a painting, photo, or artwork) and finds terrain that geometrically resembles the reference when viewed from the right angle.

Results are rendered as photorealistic previews with GPS coordinates, altitude, and heading — ready to navigate to and shoot.

---

## Why It's Novel

- **Bratkova, Thompson & Shirley (2009)** proved the concept in a Eurographics paper but it remained academic
- **CACNet (CVPR 2021)** classifies 13 composition types but doesn't generate viewpoints
- **PhotoPills, TPE, PlanIt Pro** help you plan *when* to shoot a spot you already know — none discover *where* to shoot
- No product, startup, or GitHub repo connects these pieces

---

## The Key Algorithmic Insight

Traditional approach: generate millions of random camera angles, render each one, score for beauty. **Computationally impossible.**

Our approach: **composition rules are geometric constraints.** If you know where terrain features are in 3D and where you want them in the 2D frame, the camera position is a solvable equation — not a search problem.

This is the inverse of the Perspective-n-Point (PnP) problem from computer vision: given 3D points and *desired* 2D screen positions, solve for camera pose. The composition template defines the desired positions. The terrain geometry provides the 3D points.

```
10,000,000,000  possible viewpoints (brute force)
         ↓  Deterministic computation from geometry
       ~500  candidates, ALL compositionally valid by construction
         ↓  Score for non-composition beauty factors
        ~50  beautiful, well-composed viewpoints
         ↓  Render + neural aesthetic scoring
        ~20  top viewpoints
         ↓  CMA-ES fine-tuning
        ~10  optimized final viewpoints
         ↓  Nano Banana 2 photorealistic enhancement
        ~10  deliverables with GPS coordinates
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js)                         │
│                                                              │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Map      │ │ Filter    │ │ Results  │ │ Style         │  │
│  │ Picker   │ │ Panel     │ │ Gallery  │ │ Reference     │  │
│  │          │ │           │ │          │ │ Upload        │  │
│  └────┬─────┘ └─────┬─────┘ └────┬─────┘ └──────┬────────┘  │
│       └─────────────┴────────────┴───────────────┘           │
│                          │                                   │
│  ┌───────────────────────┴───────────────────────────────┐   │
│  │            CesiumJS 3D Terrain Viewer                 │   │
│  │   (interactive globe, renders viewpoints, exports)    │   │
│  └───────────────────────┬───────────────────────────────┘   │
└──────────────────────────┼───────────────────────────────────┘
                           │ API
┌──────────────────────────┼───────────────────────────────────┐
│                   BACKEND (Python FastAPI)                    │
│                          │                                   │
│  ┌───────────────────────▼──────────────────────────────┐    │
│  │  Phase 1: Terrain Analysis                           │    │
│  │  Fetch DEM → slope, curvature, flow accumulation     │    │
│  │  → peaks, ridges, cliffs, water, saddles             │    │
│  │  Tools: AWS Terrain Tiles, NumPy, SciPy, rasterio    │    │
│  └──────────────────────┬───────────────────────────────┘    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │  Phase 2: Scene Grouping                             │    │
│  │  Cluster features into "scenes" (peak + lake,        │    │
│  │  two peaks + ridge, cliff + valley, etc.)            │    │
│  └──────────────────────┬───────────────────────────────┘    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │  Phase 3: Deterministic Camera Computation           │    │
│  │  For each scene × composition template × fractal D:  │    │
│  │  SOLVE camera pose via inverse projection + ridge    │    │
│  │  fractal dim → distance. ~500 candidates, all valid  │    │
│  └──────────────────────┬───────────────────────────────┘    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │  Phase 4: Beauty Scoring (no composition scoring     │    │
│  │  needed — it's already guaranteed)                   │    │
│  │  Viewshed entropy, prospect-refuge, depth layering,  │    │
│  │  skyline fractal dim (from DEM), mystery score       │    │
│  └──────────────────────┬───────────────────────────────┘    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │  Phase 5: Render + Neural Scoring                    │    │
│  │  CesiumJS headless → LAION Aesthetics v2.5           │    │
│  │  + CACNet composition verification                   │    │
│  └──────────────────────┬───────────────────────────────┘    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │  Phase 6: CMA-ES Refinement                          │    │
│  │  Fine-tune top candidates (50 evals each)            │    │
│  │  CMA-ES handles non-convex, discontinuous landscape  │    │
│  └──────────────────────┬───────────────────────────────┘    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │  Phase 7: Enhancement                                │    │
│  │  Nano Banana 2 → photorealistic preview              │    │
│  │  Style reference → IP-Adapter + ControlNet           │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

## Phase-by-Phase Algorithm Detail

### Phase 1: Terrain Feature Extraction

**Input:** Lat/lng center point + radius (user clicks map).

**Fetch DEM** from AWS Terrain Tiles (free, unlimited, no API key). Tiles are RGB-encoded PNGs where pixel values encode elevation. Decode to a NumPy elevation grid at ~30-75m resolution depending on zoom.

**Compute terrain derivatives:**

| Derivative | What it finds | How |
|---|---|---|
| Slope | Steepness of terrain | First partial derivatives (Horn's formula) |
| Profile curvature | Cliff edges, convex/concave breaks | Second derivative along slope direction |
| Plan curvature | Ridge crests, valley bottoms | Second derivative perpendicular to slope |
| Laplacian | Dramatic terrain changes | Sum of second partial derivatives |

**Extract features:**

- **Peaks:** Local maxima in elevation grid, filtered by topographic prominence (minimum vertical drop to reach higher terrain). Prominence separates real landmarks from noise.
- **Ridgelines:** Invert the DEM (subtract from max), run D8 flow accumulation on the inverted surface. Water collection paths in the inverted map = ridgelines in real terrain. Elegant hydrology trick.
- **Cliffs:** Cells where absolute profile curvature exceeds the 95th percentile. Cliff = terrain goes from gentle slope → sudden drop → gentle slope; the curvature spikes at the transition.
- **Water (streams):** D8 flow accumulation on the normal DEM. Cells with high upstream drainage area are streams. Confluences are where streams merge.
- **Water (lakes):** Fill depressions in the DEM. Cells where the filled DEM exceeds the original DEM by a threshold are lake beds.
- **Saddle points:** Where Gaussian curvature is strongly negative — the terrain curves up in one direction and down in another. Mountain passes.

**Compute interest map** (user-adjustable weights via sliders):

```python
interest = (
    w_peaks   * distance_decay(peaks, sigma=2000) +
    w_ridges  * ridgelines.astype(float) +
    w_cliffs  * normalize(abs(profile_curvature)) +
    w_water   * distance_decay(streams | lakes, sigma=1000) +
    w_relief  * normalize(local_elevation_range(dem, window=21))
)
```

**Time estimate:** ~5 seconds for a 20km radius area.

### Phase 2: Scene Grouping

Cluster features into photographable "scenes" — groups of features that could appear together in one frame:

- Peak + nearby lake → classic mountain reflection shot
- Two peaks + connecting ridge → dramatic skyline
- Cliff face + valley floor → vertical drama
- Stream confluence + surrounding peaks → compositional anchor
- Ridge + distant peak behind → depth/layering

Use spatial proximity (features within 5km of each other) and elevation relationships (features at different heights provide depth).

Each scene has 2-5 anchor features with known 3D coordinates.

### Phase 3: Deterministic Camera Computation

**This is the core innovation.** For each scene, we compute camera positions that satisfy composition rules. No searching.

#### Composition Templates

**Rule of Thirds** — place primary feature at one of four power points:

```
Template: "Primary at upper-right, secondary at lower-left"

    ┌──────┬──────┬──────┐
    │      │      │  P₁  │  P₁ = primary feature → (2W/3, H/3)
    ├──────┼──────┼──────┤
    │      │      │      │
    ├──────┼──────┼──────┤
    │  P₂  │      │      │  P₂ = secondary feature → (W/3, 2H/3)
    └──────┴──────┴──────┘

Given P₁ at (x₁,y₁,z₁) should project to (2W/3, H/3)
  and P₂ at (x₂,y₂,z₂) should project to (W/3, 2H/3)
  → solve inverse PnP for camera position + orientation
```

**Golden Ratio** — same approach, features at φ intersections:

```
Feature positions: (W×0.618, H×0.382), (W×0.382, H×0.618), etc.
Horizon at 0.618 × H from top
```

**Leading Line** — ridge/river enters frame from edge, leads to subject:

```
Camera positioned behind the far end of a ridge, looking along it
toward the subject. The ridge projects as a diagonal leading line.

    Camera
      👁️ → along ridge → → → Peak ⭐

The camera position is determined by:
  - Ridge direction (camera is roughly behind the ridge start)
  - Subject position (camera looks toward it)
  - Desired entry corner (bottom-left, bottom-right, etc.)
```

**Symmetry** — camera on the perpendicular bisector of two features:

```
Camera on the line equidistant from both features,
looking at their midpoint. Horizon centered.
```

**Fibonacci Spiral** — for curved terrain features (meandering rivers, curving ridges):

```
1. Find curved features in terrain (high-curvature contours, meanders)
2. Fit logarithmic spiral to the curve
3. Position camera where the feature aligns with golden spiral overlay
```

**Fractal Dimension Distance** — compute the viewing distance that makes a ridgeline's skyline have D ≈ 1.3:

The skyline is just the terrain silhouette, which is dominated by ridgelines — already extracted from the DEM. We compute each ridgeline's fractal dimension directly from its elevation profile at multiple smoothing scales. Distance determines which scale you perceive, so we can solve for the distance that produces D ≈ 1.3:

```python
for ridge in ridgelines:
    profile = elevation_along(ridge)
    for scale in [50, 100, 200, 500, 1000]:  # meters
        fd_at_scale[scale] = box_counting_fd(smooth(profile, scale))

    # find scale where D ≈ 1.3
    optimal_scale = interpolate(fd_at_scale, target=1.3)

    # that scale → a viewing distance
    optimal_distance = optimal_scale * image_width_px / fov_radians

    # camera perpendicular to ridge at that distance
    camera = ridge.midpoint + ridge.normal * optimal_distance
```

No rendering needed — this is pure DEM math. The ridgeline geometry tells us exactly where to stand.

#### The Math: Solving for Camera Pose

**Pitch from horizon placement** (1 equation, instant):

```
pitch = arctan((desired_horizon_y - H/2) / focal_length)
```

Want horizon at lower third → tilt camera up. Upper third → tilt down. This directly gives pitch.

**Position + yaw from feature placement** (inverse PnP):

With 2 feature points assigned to 2 screen positions, and pitch known, we have 4 equations (2 per point × x,y screen coordinates) and 4 unknowns (camera x, y, z, yaw). This is a determined system with typically 1-2 solutions.

```python
def compute_camera_for_composition(features_3d, desired_2d, horizon_ratio, fov):
    pitch = pitch_for_horizon(horizon_ratio, fov)

    # Solve PnP with known pitch constraint
    camera_pos, yaw = solve_constrained_pnp(
        points_3d=features_3d,
        points_2d=desired_2d,
        pitch=pitch,
        fov=fov
    )

    # Validate physical feasibility
    ground_z = terrain_elevation_at(camera_pos.x, camera_pos.y)
    if camera_pos.z < ground_z + min_clearance:
        return None  # underground
    if not line_of_sight(camera_pos, features_3d[0], dem):
        return None  # obstructed

    return CameraPose(camera_pos, pitch, yaw, fov)
```

**Output per scene:** ~20-30 camera poses across all composition templates. Every single one is compositionally valid by construction.

**Total across all scenes:** ~300-500 candidates. All following known composition rules.

**Time estimate:** Under 1 second (pure linear algebra).

### Phase 4: Fast Beauty Scoring

Since composition is guaranteed, we only score for non-compositional beauty factors. All computed from DEM data, no rendering:

| Factor | What it measures | How | Weight |
|---|---|---|---|
| Viewshed richness | How much interesting terrain is visible | Ray-cast visibility × interest map | 0.20 |
| Viewpoint entropy | Diversity of terrain in view | Shannon entropy of elevation bins in visible area | 0.15 |
| Skyline fractal dimension | Skyline complexity sweet spot | Ray-cast max elevation angle per azimuth → 1D skyline profile → box-counting FD. Score = Gaussian at D=1.3 | 0.20 |
| Prospect-refuge | Balance of openness and enclosure | Viewshed area vs. terrain above horizon nearby | 0.15 |
| Depth layering | Foreground/midground/background balance | Bin visible terrain by distance, score evenness | 0.10 |
| Mystery score | Hidden-but-promising terrain | Ratio of "almost visible" interesting terrain to total visible | 0.10 |
| Water visibility | Water features in view | Count/area of visible water | 0.10 |

**Skyline fractal dimension explained:** The skyline silhouette is computable directly from the DEM — no rendering needed. For each camera position, cast rays across the horizontal FOV and record the maximum elevation angle terrain occupies per ray. This 1D profile IS the skyline. Apply box-counting to get fractal dimension. Score peaks at D ≈ 1.3 (Gaussian kernel, σ=0.15). This is essentially free — it reuses the same ray-casting already done for viewshed analysis.

**Mystery score explained:** From Kaplan & Kaplan's environmental psychology. Compute terrain that is just below the visibility threshold — hidden behind ridgelines but nearby and interesting. Views where valleys curve out of sight or terrain promises "more beyond" score higher. Ratio of near-viewshed-boundary interesting terrain to total visible terrain.

**Prospect-refuge explained:** From Appleton's evolutionary aesthetics. Prospect = viewshed area (can see far). Refuge = solid angle of terrain above horizon (feeling of shelter). Score = harmonic mean. Cliff edges overlooking valleys with mountains behind: perfect balance.

**Time estimate:** ~15 seconds for 500 candidates.

### Phase 5: Render + Neural Scoring

Top ~50 candidates get rendered via CesiumJS headless (Puppeteer captures screenshots) with satellite imagery draped over 3D terrain.

Each rendered image is scored by:

- **LAION Aesthetics Predictor v2.5** — pip-installable neural beauty score (1-10). Built on SigLIP, trained on hundreds of thousands of human aesthetic ratings. ~50ms per image.
- **CACNet composition verification** — Classifies image into 13 composition types. Confirms our deterministic computation actually produced the intended composition in the final render.

Note: skyline fractal dimension is already computed in Phase 4 from DEM data alone — no rendering needed.

```python
full_score = (
    0.35 * laion_aesthetics_score +
    0.15 * composition_verification +
    0.50 * proxy_beauty_score  # from Phase 4 (includes fractal dim)
)
```

**Time estimate:** ~30 seconds for 50 renders + scoring.

### Phase 6: CMA-ES Refinement

Top ~10 candidates get fine-tuned with CMA-ES (Covariance Matrix Adaptation Evolution Strategy).

**Why CMA-ES?** The 2024 paper "3D View Optimization for Improving Image Aesthetics" empirically showed CMA-ES achieves **3× better aesthetic improvement** than gradient descent for camera pose optimization. The beauty landscape is non-convex (small movements drastically change visibility), discontinuous (occlusion boundaries), and multi-modal (many local optima). CMA-ES handles all of this by maintaining a population and adapting its search distribution.

**How it works:**

1. Start with the candidate viewpoint as center of a search cloud
2. Sample 8 nearby viewpoints from a gaussian distribution
3. Render and score each one
4. Best ones inform CMA-ES which direction in 5D space improves beauty
5. It shifts and reshapes the search cloud toward promising directions
6. Repeat for ~50 iterations

```python
import cma

for candidate in top_10:
    x0 = [cam_x, cam_y, cam_z_offset, pitch, yaw]
    sigma0 = [100, 100, 30, 5, 15]  # initial step sizes

    result = cma.fmin(
        lambda p: -full_aesthetic_score(render(p)),
        x0, sigma0,
        options={'maxfevals': 50, 'popsize': 8}
    )
```

**Time estimate:** ~2 minutes (500 total renders across 10 candidates).

### Phase 7: Enhancement

**Photorealistic previews:** Pass CesiumJS renders through Nano Banana 2 (Gemini 3.1 Flash image generation, free API, launched Feb 26 2026) with a prompt like "Ultra-realistic landscape photograph, golden hour lighting, 85mm lens." Preserves composition and terrain while adding photorealistic quality.

**Style application (if reference provided):** Use IP-Adapter + ControlNet to apply the reference's visual style to the terrain render while preserving structure.

---

## Style Reference Pipeline

### The Problem

Comparing rendered images against a style reference at the end (e.g., CLIP similarity of 10 final candidates) is nearly useless — you're just picking the "least bad" of angles that weren't selected for style similarity. The style reference needs to change *what terrain we look for* and *how we aim cameras*.

### The Solution: Contour Topology Matching

**Key insight:** Contour lines on a DEM, viewed from the side, ARE the edges you'd see in a photograph. We can compare terrain geometry against a reference image without rendering.

#### Step 1: Extract Structural Fingerprint from Reference

```python
reference = load_image("user_upload.jpg")
edges = hed_edge_detection(reference)  # ~50ms

fingerprint = {
    'curvature_histogram': curvature_distribution(edges, bins=12, per_quadrant=True),  # 48 dims
    'orientation_histogram': edge_orientations(edges, bins=8, per_quadrant=True),       # 32 dims
    'spatial_density': edge_density_per_region(edges, grid=4x4),                        # 16 dims
    'parallelism': parallel_line_score(edges),                                          # 1 dim
    'dominant_direction': primary_edge_angle(edges),                                    # 1 dim
}
# Total: ~100-dimensional vector
```

#### Step 2: Scan DEM for Matching Terrain Geometry

Terrain patches whose contour patterns match the reference's structural fingerprint:

```python
for patch in sliding_window(dem, size=500m, stride=200m):
    contours = extract_contour_lines(patch, n_levels=20)

    terrain_descriptor = {
        'spacing': mean_contour_distance,
        'curvature': contour_curvature_distribution,
        'parallelism': how_parallel_adjacent_contours_are,
        'orientation': dominant_contour_direction,
        'sinuosity': contour_wiggliness,
    }

    similarity = cosine_similarity(terrain_descriptor, reference_terrain_archetype)
```

Matching patches become **style-driven POIs**, replacing or augmenting the generic interest map.

#### Step 3: Compute Camera from Surface Normals (Deterministic)

For each matching patch, the terrain surface normal tells us where to stand:

```python
for patch in matching_patches:
    surface_normal = average_surface_normal(patch)

    # Camera direction ≈ opposite of surface normal (face the terrain)
    camera_direction = -surface_normal

    # Distance from feature scale matching
    feature_scale = contour_pattern_extent(patch)
    camera_distance = feature_scale * (focal_length / reference_feature_scale)

    # Height from edge vertical distribution in reference
    edge_vertical_center = vertical_centroid_of_edges(reference)
    camera_height = patch_center_elevation + height_offset(edge_vertical_center)

    camera_pos = patch.center + camera_direction * camera_distance
    camera_pos.z = camera_height
```

#### Step 4: Gradient Refinement on Fingerprint Similarity

Fine-tune each camera pose by projecting contour lines onto the camera plane and optimizing the structural fingerprint match:

```python
def style_similarity(camera_params):
    contours_3d = get_contours_near(camera_params.position)
    contours_2d = project_to_camera_plane(contours_3d, camera_params)
    projected_fingerprint = compute_fingerprint(contours_2d)
    return cosine_similarity(projected_fingerprint, reference_fingerprint)

# Numerical gradient ascent — each iteration is microseconds
for iteration in range(50):
    gradient = numerical_gradient(style_similarity, camera_params, epsilon=small)
    camera_params += learning_rate * gradient
```

Contour projection is a matrix multiplication. Fingerprint comparison is a dot product. 50 iterations × 10 perturbations = 500 evaluations at microseconds each = under a second total.

#### Step 5: Final Rendered Comparison

Top 20 style-matched candidates are rendered and compared against the reference using CLIP embeddings and LPIPS (perceptual similarity). Now this comparison is meaningful because candidates were selected for geometric similarity — they should genuinely resemble the reference.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js + TypeScript | Fast to scaffold, good DX |
| 3D Globe | CesiumJS | Free, 3D terrain, camera API, screenshot capture |
| Backend | Python FastAPI | NumPy/SciPy ecosystem, ML model inference |
| DEM Data | AWS Terrain Tiles (Mapzen) | Free, unlimited, no API key, global coverage |
| Satellite Imagery | Mapbox satellite tiles | 750K tiles/month free, good quality |
| Land Cover | OSM Overpass API | Free, global, labels water/forest/urban |
| Terrain Analysis | NumPy + SciPy + rasterio | Slope, curvature, flow accumulation |
| Aesthetic Scoring | LAION Aesthetics v2.5 | `pip install aesthetic-predictor-v2-5`, fast |
| Composition Scoring | CACNet | 13 composition types, pretrained |
| Optimization | pycma | `pip install cma`, CMA-ES implementation |
| Image Enhancement | Nano Banana 2 (Gemini API) | Free tier, fast, up to 4K |
| Style Matching | HED edges + CLIP embeddings | Edge extraction + perceptual similarity |
| Headless Rendering | Puppeteer | Captures CesiumJS screenshots server-side |

### Key Data Sources

| Source | What | Resolution | Cost | Rate Limit |
|---|---|---|---|---|
| AWS Terrain Tiles | Global elevation (Terrarium PNG) | ~30-75m (zoom 12-14) | Free | Unlimited |
| Mapbox Satellite | Satellite imagery tiles | Sub-meter in many areas | Free (750K/mo) | Generous |
| OpenTopography | SRTM, Copernicus DEMs | 30-90m global | Free | 100 calls/day |
| Copernicus DEM | Global elevation (GeoTIFF) | 30m | Free | Unlimited (S3) |
| OSM Overpass | Features (water, buildings, etc.) | Vector data | Free | Generous |
| USGS 3DEP | US LiDAR point clouds | 1-3m (US only) | Free | Unlimited (S3) |

---

## User-Facing Features

### Map Interface
- Click anywhere on the globe to set search center
- Drag to set radius (1-50km)
- Real-time terrain preview in CesiumJS

### Filter Panel
- **Mode:** Ground photographer (2m height) / Drone (adjustable altitude range) / Overview
- **Feature weights (sliders):**
  - Mountains/peaks
  - Water features
  - Cliffs/drama
  - Ridgelines
  - Relief/elevation variety
- **Include/exclude:** Cities, roads, forests
- **Composition preference:** Rule of thirds / Golden ratio / Leading lines / Symmetry / All
- **Beauty weights (sliders):**
  - Panoramic openness vs. intimate enclosure (prospect-refuge balance)
  - Depth/layering (foreground-midground-background)
  - Mystery (hidden terrain beyond ridgelines)
  - Fractal complexity (skyline interest)

### Style Reference
- Upload a painting, photograph, or artwork
- System finds terrain with matching geometry viewed from the right angle
- Shows similarity score and which geometric features matched

### Results Gallery
- Grid of top results, each showing:
  - Terrain render from that angle
  - Beauty score breakdown (radar chart)
  - Composition type detected (rule of thirds, golden ratio, etc.)
  - GPS coordinates + altitude + heading + pitch
  - "Enhance" button → Nano Banana 2 photorealistic preview
  - "Navigate" → opens in Google Maps or drone flight planner
  - "Apply Style" → transfers reference style onto the terrain render

### Interactive Exploration
- Click any result to fly to that viewpoint in the CesiumJS globe
- Manually adjust camera and see scores update in real-time
- Save/bookmark viewpoints

---

## Hackathon Schedule (5 hours)

### Hour 1: Foundation (0:00 - 1:00)

- [ ] FastAPI backend skeleton with CORS
- [ ] Next.js frontend with CesiumJS globe integration
- [ ] Click-to-select location + radius on map
- [ ] DEM tile fetching from AWS Terrain Tiles
- [ ] DEM decoding (Terrarium RGB → elevation array)
- [ ] Basic API endpoint: POST location → return elevation data

### Hour 2: Terrain Analysis + Feature Extraction (1:00 - 2:00)

- [ ] Slope and curvature computation (NumPy)
- [ ] Peak detection with prominence filtering
- [ ] Ridgeline extraction (inverted hydrology)
- [ ] Water feature detection (flow accumulation)
- [ ] Cliff detection (profile curvature threshold)
- [ ] Interest map computation with configurable weights
- [ ] Scene grouping (cluster nearby features)

### Hour 3: Camera Computation + Scoring (2:00 - 3:00)

- [ ] Ridgeline fractal dimension at multiple scales → optimal viewing distance
- [ ] Composition templates (rule of thirds, golden ratio, leading line, symmetry)
- [ ] Inverse PnP solver for camera pose from composition constraints
- [ ] Physical feasibility validation (underground check, line-of-sight)
- [ ] Fast proxy beauty scoring (viewshed, entropy, skyline fractal dim, prospect-refuge, depth, mystery)
- [ ] API endpoint: POST location + filters → return ranked camera poses

### Hour 4: Rendering + Neural Scoring (3:00 - 4:00)

- [ ] CesiumJS headless rendering via Puppeteer
- [ ] LAION Aesthetics v2.5 integration
- [ ] CMA-ES refinement on top candidates
- [ ] Results gallery UI with score breakdowns
- [ ] Nano Banana 2 photorealistic enhancement

### Hour 5: Style Reference + Polish (4:00 - 5:00)

- [ ] Style reference upload UI
- [ ] HED edge extraction + structural fingerprint
- [ ] Contour topology matching on DEM patches
- [ ] Deterministic camera computation from surface normals
- [ ] Gradient refinement on fingerprint similarity
- [ ] CLIP/LPIPS rendered comparison
- [ ] Demo polish, edge cases, presentation prep

---

## Beauty Scoring: The Mathematical Foundation

### Fractal Dimension ≈ 1.3

Multiple studies (Sprott 2003, Hagerhall 2004) consistently find humans prefer visual patterns with fractal dimension around 1.3-1.5. This matches clouds, coastlines, tree canopies — patterns our visual system evolved to process fluently.

**Computation (no rendering needed):** The skyline is computable directly from the DEM. For each camera position, cast rays across the horizontal FOV and record the maximum elevation angle terrain occupies per ray. This 1D profile IS the skyline. Apply box-counting: overlay grids of decreasing box size, count boxes touching the profile. D = -log(N)/log(s). Score = Gaussian kernel centered at 1.3 with σ=0.15. This reuses the same ray-casting done for viewshed analysis, so it's essentially free.

**Camera distance computation:** Ridgeline fractal dimension can be computed at multiple smoothing scales directly from the DEM. Since viewing distance determines which scale you perceive, we can solve for the distance at which a ridgeline's skyline will have D ≈ 1.3 — making this another deterministic camera constraint rather than a search-and-filter metric.

### Prospect-Refuge Theory (Appleton 1975)

Evolutionary psychology: we prefer views balancing open vistas (prospect — can see predators) and nearby enclosure (refuge — can hide). Cliff edges overlooking valleys with mountains behind = perfect.

**Computation:** Prospect = viewshed area. Refuge = solid angle of terrain above camera's horizon. Score = harmonic_mean(prospect, refuge).

### Kaplan & Kaplan Preference Matrix (1989)

Four factors predicting landscape preference:

| Factor | Definition | How to compute |
|---|---|---|
| Coherence | Visual order, organization | Texture homogeneity, moderate entropy of segmented image |
| Complexity | Richness, number of elements | Edge density × color entropy (optimal is intermediate) |
| Legibility | Sense of place, navigability | Number of visible landmarks (prominent peaks) + open areas |
| Mystery | Promise of more information | Ratio of "almost visible" interesting terrain to total visible |

### Viewpoint Entropy (Vázquez et al. 2001)

Information theory applied to views. Shannon entropy of the visibility distribution — how diverse is the terrain visible from this point?

**Computation:** Bin visible terrain by elevation. Compute H = -Σ p_i × log(p_i). High entropy = diverse terrain = interesting view.

### Scenic Beauty Estimation (Schirpke et al.)

GIS-based model achieving R²=0.72 in predicting scenic beauty. Key factors:
- Shape complexity of visible terrain (positive)
- Landscape diversity (positive)
- Presence of water/lakes/glaciers (strongly positive)
- High-altitude viewpoints with long vistas (positive)
- Proximity to infrastructure (negative)

---

## Key Research Papers

| Paper | Year | Relevance |
|---|---|---|
| Bratkova, Thompson & Shirley — "Automatic Views of Natural Scenes" | 2009 | Most direct precedent. Energy minimization for viewpoint optimization over USGS terrain. |
| Vázquez et al. — "Viewpoint Selection using Viewpoint Entropy" | 2001 | Foundational information-theoretic viewpoint quality measure. |
| "3D View Optimization for Improving Image Aesthetics" | 2024 | CMA-ES beats gradient descent 3× for camera pose optimization. |
| "Aesthetic Camera Viewpoint Suggestion with 3D Aesthetic Field" | 2025 | Coarse-to-fine search with gradient refinement. State of the art. |
| Sprott — "Universal Aesthetic of Fractals" | 2003 | Fractal dimension ≈ 1.3 as beauty predictor. |
| Hagerhall et al. — "Fractal Dimension as Predictor of Preference" | 2004 | Validates D ≈ 1.3 preference in natural landscapes. |
| Schirpke et al. — "Predicting Scenic Beauty of Mountain Regions" | 2013 | GIS-based scenic beauty model (R²=0.72). |
| CACNet (CVPR 2021) — Composition-Aware Cropping | 2021 | Classifies 13 composition types. Rule of thirds, golden ratio, etc. |
| LAION Aesthetics Predictor | 2022 | Lightweight neural beauty score on SigLIP embeddings. |
| Appleton — Prospect-Refuge Theory | 1975 | Evolutionary basis for landscape preference. |
| Kaplan & Kaplan — The Experience of Nature | 1989 | Coherence, complexity, legibility, mystery preference matrix. |
| Yokoyama — Topographic Openness | 2002 | Positive/negative openness for landform classification. |
| Jasiewicz & Stepinski — Geomorphons | 2013 | Pattern recognition landform classification from DEMs. |

---

## Stretch Goals / Cool Additions

- **Golden hour simulation:** Score angles accounting for sun position at golden hour. Compute shadow maps on DEM from low-angle directional light. Dramatic shadows = higher score.
- **Seasonal variation:** Google Earth Engine temporal satellite imagery to preview the same angle in different seasons (fall foliage, snow, spring).
- **Drone flight path export:** Connect top N viewpoints with a TSP solver into an optimal drone route. Export as DJI/Litchi waypoint file.
- **Astrophotography mode:** Factor in light pollution maps (VIIRS nighttime satellite data) and Milky Way position for night photography scouting.
- **Waterfall finder:** Streams crossing cells with extremely high slope = likely waterfall. Automatic detection and prioritization.
- **Reflection scoring:** For lakes, score views that would show mountain reflections — camera near water level, mountain behind the lake.
- **AR mode:** Phone GPS + compass shows live camera view overlaid with the ideal composition grid, guiding the photographer to the computed angle.
- **Community feedback loop:** Photographers upload actual photos taken at suggested angles, building training data to improve the algorithm over time.
