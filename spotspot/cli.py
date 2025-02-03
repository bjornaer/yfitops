import click
import pygame
import os
from pathlib import Path
import sys
import termios
import tty
import threading
import time
from mutagen import File
from datetime import timedelta


class MusicPlayer:
    def __init__(self):
        pygame.mixer.init()
        self.current_track = None
        self.playing = False
        self.current_volume = 0.5
        pygame.mixer.music.set_volume(self.current_volume)
        self.paused = False
        self.duration = 0
        self.start_time = 0
        self.pause_start = 0
        self.total_pause_time = 0
        self.pause_position = 0
        self.first_display = True

    def play_file(self, file_path):
        try:
            # Get audio file duration using mutagen
            audio = File(file_path)
            self.duration = audio.info.length if audio else 0

            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            self.current_track = file_path
            self.playing = True
            self.paused = False
            self.start_time = time.time()
            self.total_pause_time = 0
            self.pause_position = 0
            self.first_display = True
            self.display_progress_bar(0)
        except pygame.error as e:
            click.echo(f"\rError playing file: {e}", err=True)

    def get_current_position(self):
        if not self.playing:
            return 0
        if self.paused:
            return self.pause_position
        return time.time() - self.start_time - self.total_pause_time

    def clear_lines(self, num_lines):
        """Clear the specified number of lines from the terminal."""
        # Move up num_lines lines
        click.echo(f"\x1b[{num_lines}A", nl=False)
        # Clear each line
        for _ in range(num_lines):
            click.echo("\x1b[2K", nl=False)  # Clear the entire line
            click.echo("\x1b[1B", nl=False)  # Move down one line
        # Move back up
        click.echo(f"\x1b[{num_lines}A", nl=False)

    def display_progress_bar(self, position):
        if self.duration <= 0:
            return

        # Calculate progress
        progress = min(position / self.duration, 1.0)
        percentage = int(progress * 100)

        # Format times
        current_time = str(timedelta(seconds=int(position))).split(".")[0]
        total_time = str(timedelta(seconds=int(self.duration))).split(".")[0]

        # Clear the screen from current position to bottom
        if not self.first_display:
            # Move up 3 lines and clear to bottom
            click.echo("\033[3F\033[J", nl=False)
        else:
            self.first_display = False
            click.echo()

        # Print the status
        click.secho(
            f"{os.path.basename(self.current_track)}", fg="bright_blue", bold=True
        )

        # Create progress bar
        width = 30
        filled = int(width * progress)
        bar = "━" * filled
        if filled < width:
            bar += "╺"
            bar += "━" * (width - filled - 1)

        # Format and print the progress line
        progress_text = (
            f"{percentage:3d}% |{click.style(bar, fg='green')}| "
            f"{click.style(current_time + '/' + total_time, fg='bright_black')} "
            f"{click.style(f'🔊 {int(self.current_volume * 100)}%', fg='yellow')} "
            f"{click.style('⏸️ ' if self.paused else '▶️ ', fg='bright_green' if not self.paused else 'yellow')}"
        )
        click.echo(progress_text)
        click.echo()  # Add an empty line for spacing

    def pause(self):
        if self.playing and not self.paused:
            pygame.mixer.music.pause()
            self.paused = True
            self.pause_start = time.time()
            self.pause_position = self.get_current_position()
            self.display_progress_bar(self.pause_position)
        elif self.playing and self.paused:
            pygame.mixer.music.unpause()
            self.paused = False
            self.total_pause_time += time.time() - self.pause_start
            self.display_progress_bar(self.get_current_position())

    def stop(self):
        if self.playing:
            pygame.mixer.music.stop()
            self.playing = False
            self.paused = False

    def adjust_volume(self, up=True):
        if up and self.current_volume < 1.0:
            self.current_volume = min(1.0, self.current_volume + 0.1)
        elif not up and self.current_volume > 0.0:
            self.current_volume = max(0.0, self.current_volume - 0.1)
        pygame.mixer.music.set_volume(self.current_volume)
        self.display_progress_bar(self.get_current_position())

    def is_playing(self):
        return pygame.mixer.music.get_busy()


def get_char():
    """Get a single character from standard input."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def print_controls():
    """Print the control instructions."""
    click.echo("\nControls:")
    click.echo(" space - play/pause")
    click.echo(" + - volume up")
    click.echo(" - - volume down")
    click.echo(" q - quit")
    click.echo(" n - next track (in directory mode)")
    click.echo(" p - previous track (in directory mode)")


def handle_keyboard_input(player, music_files=None, current_index=None):
    """Handle keyboard input for music controls."""
    while True:
        char = get_char()

        if char == " ":  # space bar
            player.pause()
        elif char == "+":
            player.adjust_volume(up=True)
        elif char == "-":
            player.adjust_volume(up=False)
        elif char == "q":
            player.stop()
            click.echo("\nQuitting...")
            sys.exit(0)
        elif char == "n" and music_files and current_index is not None:
            return "next"
        elif char == "p" and music_files and current_index is not None:
            return "prev"


def update_progress_bar(player):
    """Update the progress bar in a separate thread."""
    last_position = -1
    last_update = 0
    while player.playing:
        if not player.paused:
            current_time = time.time()
            position = player.get_current_position()
            # Update only if position changed and enough time has passed
            if (
                position != last_position
                and position <= player.duration
                and current_time - last_update >= 0.1
            ):
                player.display_progress_bar(position)
                last_position = position
                last_update = current_time
        time.sleep(0.1)


@click.command()
@click.argument("path", type=click.Path(exists=True))
def main(path):
    """
    Play music from a file or directory.

    PATH can be either a music file or a directory containing music files.
    """
    player = MusicPlayer()
    path = Path(path)
    print_controls()

    if path.is_file():
        player.play_file(str(path))
        # Start progress bar thread
        progress_thread = threading.Thread(target=update_progress_bar, args=(player,))
        progress_thread.daemon = True
        progress_thread.start()
        handle_keyboard_input(player)

    elif path.is_dir():
        supported_formats = {".mp3", ".wav", ".ogg"}
        music_files = [
            f for f in path.iterdir() if f.suffix.lower() in supported_formats
        ]

        if not music_files:
            click.echo("No supported music files found in directory")
            return

        click.echo(f"Found {len(music_files)} music files")
        current_index = 0

        while 0 <= current_index < len(music_files):
            player.play_file(str(music_files[current_index]))

            # Start progress bar thread
            progress_thread = threading.Thread(
                target=update_progress_bar, args=(player,)
            )
            progress_thread.daemon = True
            progress_thread.start()

            # Handle keyboard input
            action = handle_keyboard_input(player, music_files, current_index)

            if action == "next":
                current_index += 1
            elif action == "prev":
                current_index -= 1

            player.stop()


if __name__ == "__main__":
    main()
