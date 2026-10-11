"""A fake project with made-up clips, for exploring the UI before import exists."""

from __future__ import annotations

from .model import Clip, Project, Transition


def demo_project() -> Project:
    project = Project.new("Demo movie")
    video = project.main_track
    video.add_clip(Clip.from_video("Temple pond.mp4", 23.7))
    video.add_clip(Clip.from_video("Street walk.mp4", 12.4,
                                   transition_in=Transition("fade", 1.0)))
    video.add_clip(Clip.from_image("Sunset.jpg", 7.0))
    video.add_clip(Clip.from_video("Market.mp4", 31.2, effect="sepia"))
    video.add_clip(Clip.from_video("Family dinner.mp4", 15.0))
    project.tracks[1].add_clip(Clip.from_audio("Background music.mp3", 60.0))
    return project
