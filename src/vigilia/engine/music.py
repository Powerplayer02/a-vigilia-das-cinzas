"""Presentation-only music sequencing; called by the composition event handler."""


class MusicDirector:
    def __init__(self, backend):
        self.backend = backend
        self.requested = ""
        self.pending = None
        self.followup = None
        self.clock = getattr(backend, "music_clock", None)
        self.deadline = 0.

    def request(self, event):
        track = event.track_id
        if track == self.requested and track:
            return
        previous = self.requested
        self.requested, self.pending, self.followup = track, None, None
        if not track:
            self.backend.stop_music(fade_sec=event.fade_sec)
        elif track.endswith("_phase1") and not previous.startswith(track[:-1]):
            self.backend.stop_music(fade_sec=.5)
            self.pending = (track, .5)
            if self.clock is not None:
                self.deadline = self.clock() + .5
        else:
            fade = 2 if track.endswith(("_phase2", "_phase3")) else event.fade_sec
            self.backend.play_music(track, fade_sec=fade)

    def set_options(self, opened):
        self.backend.set_music_duck(-6 if opened else 0)

    def play_postcredits(self, ambient):
        self.requested, self.pending = "post_credits", None
        self.followup = ambient
        self.backend.play_music("post_credits", fade_sec=1.5)

    def update(self, dt):
        if self.pending:
            track, remaining = self.pending
            remaining = self.deadline - self.clock() if self.clock is not None else remaining - max(0, dt)
            if remaining <= 1e-9:
                self.pending = None
                self.backend.play_music(track, fade_sec=1)
            else:
                self.pending = (track, remaining)
        if self.followup and self.backend.music_finished:
            track, self.followup = self.followup, None
            self.requested = track
            self.backend.play_music(track, fade_sec=1.5)
