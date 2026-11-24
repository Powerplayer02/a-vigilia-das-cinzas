"""Identidade geográfica estável, utilizável por save e mapa sem engine."""

from vigilia.core.mathx import Vec3

AREA_BOUNDS = {
    "patio_da_vigilia": (-12., -14., 24., 28.),
    "forge_arena": (-12., 14., 24., 23.),
    "catedral_submersa": (46., -16., 28., 40.),
    "pantano_das_cinzas": (106., -16., 28., 56.),
    "ruinas_subterraneas": (166., -16., 28., 56.),
    "forno_da_vigilia": (226., -16., 28., 56.),
}


def area_at(point: Vec3) -> str:
    for name, (x, y, width, height) in AREA_BOUNDS.items():
        if x <= point.x <= x + width and y <= point.y <= y + height:
            return name
    return "patio_da_vigilia"


def scene_at(point: Vec3) -> str:
    area = area_at(point)
    return "patio_da_vigilia" if area == "forge_arena" else area
