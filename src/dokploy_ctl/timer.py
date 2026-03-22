"""Shared timer for timestamped CLI output."""

import time

import click


class Timer:
    def __init__(self) -> None:
        self._start = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def stamp(self) -> str:
        mins, secs = divmod(int(self.elapsed()), 60)
        return f"[{mins:02d}:{secs:02d}]"

    def log(self, msg: str) -> str:
        line = f"{self.stamp()} {msg}"
        click.echo(line)
        return line

    def summary(self, msg: str) -> str:
        total = int(self.elapsed())
        line = f"{self.stamp()} {msg} ({total}s total)"
        click.echo(line)
        return line
