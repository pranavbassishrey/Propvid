"""Terminal styling, ANSI colors, progress bars, and display components."""

import os
import sys
import time
from typing import List, Optional, Tuple


def supports_color() -> bool:
    """Return True if the current terminal supports ANSI escape sequences."""
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    # Check if stdout or stderr is attached to a real TTY
    return sys.stdout.isatty() or sys.stderr.isatty()


# Color escape codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# Foreground colors
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

# Bright foreground colors
BRIGHT_BLACK = "\033[90m"
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"


def colorize(text: str, code: str) -> str:
    """Wrap text in ANSI escape code if color is supported."""
    if not supports_color():
        return text
    return f"{code}{text}{RESET}"


def bold(text: str) -> str:
    return colorize(text, BOLD)


def dim(text: str) -> str:
    return colorize(text, DIM)


def cyan(text: str) -> str:
    return colorize(text, CYAN)


def green(text: str) -> str:
    return colorize(text, GREEN)


def yellow(text: str) -> str:
    return colorize(text, YELLOW)


def red(text: str) -> str:
    return colorize(text, RED)


def blue(text: str) -> str:
    return colorize(text, BLUE)


def magenta(text: str) -> str:
    return colorize(text, MAGENTA)


# Showcase badges
def badge_ok() -> str:
    return f"{colorize('[OK]', BOLD + GREEN)}"


def badge_warn() -> str:
    return f"{colorize('[WARN]', BOLD + YELLOW)}"


def badge_err() -> str:
    return f"{colorize('[ERR]', BOLD + RED)}"


def badge_info() -> str:
    return f"{colorize('[INFO]', BOLD + CYAN)}"


def badge_ai() -> str:
    return f"{colorize('[AI]', BOLD + MAGENTA)}"


def badge_tts() -> str:
    return f"{colorize('[TTS]', BOLD + BLUE)}"


def badge_render() -> str:
    return f"{colorize('[RENDER]', BOLD + CYAN)}"


def badge_skip() -> str:
    return f"{colorize('[SKIP]', DIM + WHITE)}"


def print_banner() -> None:
    """Print the high-impact Propvid ASCII showcase banner."""
    c_cyan = CYAN if supports_color() else ""
    c_blue = BLUE if supports_color() else ""
    c_bold = BOLD if supports_color() else ""
    c_reset = RESET if supports_color() else ""
    c_dim = DIM if supports_color() else ""

    banner = f"""{c_cyan}{c_bold}  ____  ____  ____  ______ _    _______ ____ 
 / __ \\/ __ \\/ __ \\/ ____/| |  / /  _/ __ \\
/ /_/ / /_/ / / / / /_   | | / // // / / /
/ ____/ _, _/ /_/ / __/   | |/ // // /_/ / 
/_/   /_/ |_|\\____/_/      |___/___/_____/  {c_reset}
{c_blue}{c_bold}Propvid // AI Property Video Studio{c_reset} {c_dim}• Deterministic-First Promo Engine{c_reset}
"""
    print(banner)


def print_step(step_idx: int, total_steps: int, title: str) -> None:
    """Print a clean step progress header."""
    step_tag = colorize(f"[{step_idx}/{total_steps}]", BOLD + CYAN)
    print(f"\n{step_tag} {bold(title)}")


class ProgressBar:
    """Smooth dynamic terminal progress bar with FPS and ETA calculation."""

    def __init__(self, total: int, label: str = "Encoding", width: int = 28):
        self.total = max(1, total)
        self.label = label
        self.width = width
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.is_tty = supports_color()
        self._finished = False

    def update(self, current: int) -> None:
        if self._finished:
            return
        now = time.time()
        # Rate limit updates to avoid terminal flicker
        if current < self.total and (now - self.last_update_time) < 0.08:
            return
        self.last_update_time = now

        pct = min(1.0, current / float(self.total))
        filled_len = int(self.width * pct)
        empty_len = self.width - filled_len

        bar_filled = "▰" * filled_len
        bar_empty = "▱" * empty_len
        bar_str = colorize(bar_filled, BOLD + CYAN) + colorize(bar_empty, DIM)

        elapsed = max(0.001, now - self.start_time)
        fps = current / elapsed
        remaining_sec = (self.total - current) / fps if fps > 0 and current < self.total else 0.0

        eta_str = f"{int(remaining_sec // 60):02d}:{int(remaining_sec % 60):02d}"
        badge = badge_render()

        line = f"\r{badge} {bold(self.label)}: [{bar_str}] {int(pct * 100):3d}% ({current}/{self.total}) • {fps:.1f} fps • ETA {eta_str}"
        sys.stderr.write(line)
        sys.stderr.flush()

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        elapsed = time.time() - self.start_time
        fps = self.total / max(0.001, elapsed)
        badge = badge_ok()
        bar_str = colorize("▰" * self.width, BOLD + GREEN)
        line = f"\r{badge} {bold(self.label)}: [{bar_str}] 100% ({self.total}/{self.total}) • {fps:.1f} fps • {elapsed:.1f}s total\n"
        sys.stderr.write(line)
        sys.stderr.flush()


def print_card(title: str, items: List[Tuple[str, str]], footer: Optional[str] = None) -> None:
    """Print an aligned, beautiful box card for summaries."""
    title_text = f" {title} "
    width = 72
    pad_left = (width - len(title_text)) // 2
    pad_right = width - len(title_text) - pad_left

    top_border = "┌" + ("─" * pad_left) + bold(title_text) + ("─" * pad_right) + "┐"
    bot_border = "└" + ("─" * width) + "┘"

    print("\n" + top_border)
    for label, value in items:
        lbl = colorize(f"{label}:", BOLD).ljust(22 if not supports_color() else 31)
        print(f"│  {lbl} {value.ljust(width - 25)} │")
    if footer:
        print("├" + ("─" * width) + "┤")
        print(f"│  {footer.ljust(width - 4)}  │")
    print(bot_border)


def print_table(headers: List[str], rows: List[List[str]], title: Optional[str] = None) -> None:
    """Print a clean ASCII table with aligned columns."""
    if title:
        print(f"\n{bold(title)}")

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            # Strip ANSI when calculating raw width
            import re
            raw_cell = re.sub(r"\033\[[0-9;]*m", "", cell)
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(raw_cell))

    # Header
    hdr_parts = [colorize(h.ljust(col_widths[i]), BOLD) for i, h in enumerate(headers)]
    sep_parts = ["─" * col_widths[i] for i in range(len(headers))]
    print("  " + "   ".join(hdr_parts))
    print("  " + "───".join(sep_parts))

    # Rows
    for row in rows:
        formatted_cells = []
        for i, cell in enumerate(row):
            import re
            raw_len = len(re.sub(r"\033\[[0-9;]*m", "", cell))
            pad = col_widths[i] - raw_len
            formatted_cells.append(cell + (" " * pad))
        print("  " + "   ".join(formatted_cells))
    print("  " + "───".join(sep_parts))
