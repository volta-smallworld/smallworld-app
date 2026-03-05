// GLSL vertex + fragment shaders for the animated 3D orb
// Simplex noise displacement + multi-layered fragment coloring

export const vertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uSpeed;
  uniform float uNoiseAmplitude;

  varying vec3 vNormal;
  varying vec3 vPosition;
  varying float vDisplacement;
  varying vec3 vViewDir;

  // --- Simplex 3D noise (Ashima Arts) ---
  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

  float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

    vec3 i = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);

    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);

    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;

    i = mod289(i);
    vec4 p = permute(permute(permute(
      i.z + vec4(0.0, i1.z, i2.z, 1.0))
      + i.y + vec4(0.0, i1.y, i2.y, 1.0))
      + i.x + vec4(0.0, i1.x, i2.x, 1.0));

    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;

    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);

    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);

    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);

    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);

    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));

    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;

    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);

    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;

    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
  }

  void main() {
    float t = uTime * uSpeed;

    // 3-octave noise displacement (low frequencies for smooth, organic motion)
    float n1 = snoise(position * 0.8 + t * 0.4);
    float n2 = snoise(position * 1.5 + t * 0.5) * 0.3;
    float n3 = snoise(position * 2.5 + t * 0.6) * 0.1;
    float displacement = (n1 + n2 + n3) * uNoiseAmplitude;

    vec3 newPosition = position + normal * displacement;

    vNormal = normalize(normalMatrix * normal);
    vPosition = (modelViewMatrix * vec4(newPosition, 1.0)).xyz;
    vDisplacement = displacement;
    vViewDir = normalize(-vPosition);

    gl_Position = projectionMatrix * modelViewMatrix * vec4(newPosition, 1.0);
  }
`;

export const fragmentShader = /* glsl */ `
  uniform float uTime;
  uniform float uSpeed;
  uniform float uColorShift;
  uniform float uNoiseAmplitude;

  varying vec3 vNormal;
  varying vec3 vPosition;
  varying float vDisplacement;
  varying vec3 vViewDir;

  void main() {
    vec3 normal = normalize(vNormal);
    vec3 viewDir = normalize(vViewDir);

    // 1. Base gradient: deep blue -> purple based on Y + displacement
    float yFactor = normal.y * 0.5 + 0.5;
    float dispFactor = vDisplacement / uNoiseAmplitude;
    vec3 deepBlue = vec3(0.05, 0.02, 0.15);
    vec3 purple = vec3(0.35, 0.1, 0.55);
    vec3 baseColor = mix(deepBlue, purple, yFactor + dispFactor * 0.3);

    // 2. Iridescence: view-angle cyan <-> orange shift
    float viewAngle = dot(normal, viewDir);
    float iriTime = sin(uTime * uSpeed * 0.5) * 0.5 + 0.5;
    vec3 cyan = vec3(0.2, 0.75, 0.95);
    vec3 orange = vec3(0.95, 0.5, 0.1);
    vec3 iriColor = mix(cyan, orange, iriTime);
    float iriStrength = pow(1.0 - abs(viewAngle), 2.0) * 0.35;
    baseColor += iriColor * iriStrength;

    // 3. Fresnel rim glow: purple (idle) -> cyan (thinking) via uColorShift
    float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 3.0);
    vec3 rimIdle = vec3(0.5, 0.1, 0.9);
    vec3 rimActive = vec3(0.2, 0.8, 1.0);
    vec3 rimColor = mix(rimIdle, rimActive, uColorShift);
    baseColor += rimColor * fresnel * (0.6 + uColorShift * 0.4);

    // 4. Fake environment reflection: upward hemisphere glossy highlight
    vec3 reflected = reflect(-viewDir, normal);
    float envReflect = max(reflected.y, 0.0);
    envReflect = pow(envReflect, 4.0);
    baseColor += vec3(0.8, 0.85, 1.0) * envReflect * 0.15;

    // 5. Surface detail lines: fract-based contour edges
    float contour = fract(vDisplacement * 8.0);
    float lineStrength = smoothstep(0.0, 0.05, contour) * (1.0 - smoothstep(0.95, 1.0, contour));
    lineStrength = 1.0 - lineStrength;
    baseColor += vec3(0.4, 0.3, 0.7) * lineStrength * 0.12;

    // 6. Peak highlights: warm orange on most-displaced vertices
    float peakFactor = smoothstep(0.5, 1.0, dispFactor);
    vec3 peakColor = vec3(0.95, 0.55, 0.15);
    baseColor += peakColor * peakFactor * 0.2;

    gl_FragColor = vec4(baseColor, 1.0);
  }
`;
