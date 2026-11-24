"""Compatibilidade do benchmark com o flight recorder compartilhado do QA."""
from vigilia.core.flight_recorder import FrameRecorder as PureRecorder

class FrameRecorder(PureRecorder):
    def __init__(self, directory, physics, **options):
        def contacts():
            manifolds = physics._world.get_manifolds()
            return dict(manifolds=len(manifolds), contacts=sum(m.get_num_manifold_points() for m in manifolds))
        super().__init__(directory, contacts, **options)
