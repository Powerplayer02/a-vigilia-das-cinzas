#version 130

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat3 p3d_NormalMatrix;

in vec4 p3d_Vertex;
in vec3 p3d_Normal;
out vec3 world_pos;
out vec3 world_normal;
out vec3 view_normal;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    world_normal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
    view_normal = normalize(p3d_NormalMatrix * p3d_Normal);
}
