#version 130

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
