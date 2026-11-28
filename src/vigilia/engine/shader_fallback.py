"""Built-in arena material when assets/shaders are missing or invalid."""

VERTEX = """#version 130

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat4 p3d_ViewMatrix;
uniform mat3 p3d_NormalMatrix;
uniform float osg_FrameTime;
uniform vec3 light_clock;

in vec4 p3d_Vertex;
in vec3 p3d_Normal;
out vec3 world_pos;
out vec3 world_normal;
out vec3 view_normal;
out vec3 view_pos;
out float fire_pulse;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    view_pos = (p3d_ViewMatrix * vec4(world_pos,1.0)).xyz;
    float age = light_clock.z > 0.5 ? light_clock.y : osg_FrameTime-light_clock.x;
    fire_pulse = 0.8 + 0.1*sin(age*9.0);
    world_normal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
    view_normal = normalize(p3d_NormalMatrix * p3d_Normal);
}
"""

FRAGMENT = """#version 130

uniform vec4 p3d_ColorScale;
uniform float masonry;
uniform float draw_distance;
uniform vec4 area_fog;
uniform vec4 area_light;
uniform vec4 fire_glow;

in vec3 world_pos;
in vec3 world_normal;
in vec3 view_normal;
in vec3 view_pos;
in float fire_pulse;
out vec4 result;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void main() {
    vec3 n = normalize(world_normal);
    vec2 uv = abs(n.z) > .5 ? world_pos.xy :
              vec2(abs(n.x) > .5 ? world_pos.y : world_pos.x, world_pos.z * 1.8);
    vec2 brick = uv * .86;
    brick.x += floor(brick.y) * .5;
    vec2 tile = fract(brick);
    vec2 edges = min(tile, 1.0 - tile);
    float bevel = smoothstep(.015, .042, min(edges.x, edges.y));
    float tonal = .77 + .21 * hash(floor(brick));
    float grain = hash(floor(uv * 34.0)) * .09;
    float surface = mix(1.0, mix(.44, tonal + grain, bevel), masonry);

    float incident = max(dot(n, normalize(vec3(-.64, -.34, .91))), 0.0);
    float light = .63 + .57 * smoothstep(.23, .26, incident);
    float rim = pow(1.0 - abs(normalize(view_normal).z), 2.4) * .13;
    vec3 base = p3d_ColorScale.rgb * (surface * light + rim) * area_light.rgb;
    vec3 fire_delta = world_pos - fire_glow.xyz;
    base += vec3(.42,.18,.055) * fire_glow.w * fire_pulse / (1.0 + dot(fire_delta,fire_delta));
    float distance_to_eye = length(view_pos);
    float fog = max(1.0 - exp(-distance_to_eye * .019), smoothstep(draw_distance * .65, draw_distance, distance_to_eye));
    result = vec4(mix(base, area_fog.rgb, fog), 1.0);
}
"""
