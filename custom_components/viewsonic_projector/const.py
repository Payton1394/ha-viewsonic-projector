"""Constants and the ViewSonic command table.

Every control the projector exposes over RS-232 is declared here as data, and
the entity platforms are generated from it. Adding a command means adding a row,
not writing a class.

All opcodes are transcribed from the PJD7820HD user guide, "RS232 command table"
(pp. 66-73). Each control names a `group` and the command byte(s) within it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

DOMAIN: Final = "viewsonic_projector"

DEFAULT_PORT: Final = 8888
DEFAULT_NAME: Final = "ViewSonic Projector"

CONF_SCAN_INTERVAL: Final = "scan_interval"

# Power is polled every cycle; everything else rotates through a queue so no
# single cycle stalls on 30-odd serialised round trips.
DEFAULT_SCAN_INTERVAL: Final = 3
MIN_SCAN_INTERVAL: Final = 2
MAX_SCAN_INTERVAL: Final = 60
SLOW_READS_PER_CYCLE: Final = 4

# Controls the projector refuses drop out of the rotation. They come back on any
# power-state change, and otherwise after this long -- the projector can be
# switched on at its own panel or by remote, which we only notice via polling.
REARM_AFTER: Final = 300

# The projector answers in well under 100ms when it answers at all, and refusals
# come back immediately as a NAK. This only bounds the case where it stays silent
# -- which it does for some queries in standby -- so it can be tight.
REPLY_TIMEOUT: Final = 1.0

# The projector keeps reporting the old power state while the lamp strikes or
# cools. Trust the commanded state for this long rather than let the switch flap.
POWER_CONFIRM_SETTLE: Final = 6.0

# Settle delay before re-reading a plain setting we just wrote.
WRITE_CONFIRM: Final = 0.4

# Before each query, whatever is already on the line is thrown away: a reply
# that came after its query timed out would otherwise be read as the answer to
# the next query. The line counts as quiet after this long without a byte (a
# 34-byte frame takes 3 ms at 115200 baud).
STALE_QUIET: Final = 0.03
# After a query went unanswered its reply may still be on its way: wait longer.
STALE_QUIET_AFTER_MISS: Final = 0.3

# A missed power reply keeps the last known state; only this many misses in a
# row mark the projector unavailable.
POWER_MISSES_ALLOWED: Final = 3

# Controls of these kinds answer with a single byte after three of padding.
# A wider frame is somebody else's late reply, never theirs.
SINGLE_BYTE_PAYLOAD: Final = 4

KEY_ERROR_STATUS: Final = "error_status"
KEY_LAMP_HOURS: Final = "lamp_hours"


class Kind(StrEnum):
    """What sort of entity a control becomes."""

    SWITCH = "switch"
    SELECT = "select"
    STEP = "step"  # increment/decrement only: two buttons plus a value sensor
    EXECUTE = "execute"  # fire-and-forget button
    READONLY = "readonly"  # sensor


@dataclass(frozen=True)
class Control:
    """One projector control.

    `on`/`off`/`up`/`down`/`execute` are (command_byte, value) pairs. Most
    controls keep one command byte and vary the value, but a few -- power and
    volume -- vary the command byte instead, so the pair is always explicit.
    """

    key: str
    name: str
    group: int
    kind: Kind
    read_cmd: int | None = None
    on: tuple[int, int] | None = None
    off: tuple[int, int] | None = None
    up: tuple[int, int] | None = None
    down: tuple[int, int] | None = None
    execute: tuple[int, int] | None = None
    options: dict[str, int] = field(default_factory=dict)
    option_cmd: int | None = None
    icon: str | None = None
    diagnostic: bool = False
    primary: bool = False  # excluded from the config category; shown up front

    @property
    def options_by_code(self) -> dict[int, str]:
        """Reverse the option map for decoding replies."""
        return {v: k for k, v in self.options.items()}


# --------------------------------------------------------------------------
# Power. The one control whose on/off differ in the COMMAND byte rather than
# the value byte -- both carry value 0x00:
#     on  06 14 00 04 00 34 11 00 00 5D
#     off 06 14 00 04 00 34 11 01 00 5E
# Encoding it as a value toggle yields 11 00 01: a different command with an
# identical checksum, so it validates cleanly and does the wrong thing.
# --------------------------------------------------------------------------
POWER: Final = Control(
    key="power",
    name="Power",
    group=0x11,
    kind=Kind.SWITCH,
    read_cmd=0x00,
    on=(0x00, 0x00),
    off=(0x01, 0x00),
    icon="mdi:projector",
    primary=True,
)


CONTROLS: Final[tuple[Control, ...]] = (
    # ---- Picture source and framing -------------------------------------
    Control(
        key="source",
        name="Source",
        group=0x13,
        kind=Kind.SELECT,
        read_cmd=0x01,
        option_cmd=0x01,
        options={"VGA": 0x00, "VGA2": 0x08, "HDMI": 0x03, "Composite": 0x05, "S-Video": 0x06},
        icon="mdi:video-input-hdmi",
        primary=True,
    ),
    Control(
        key="aspect_ratio",
        name="Aspect ratio",
        group=0x12,
        kind=Kind.SELECT,
        read_cmd=0x04,
        option_cmd=0x04,
        options={"Auto": 0x00, "4:3": 0x02, "16:9": 0x03, "Wide": 0x06},
        icon="mdi:aspect-ratio",
        primary=True,
    ),
    Control(
        key="color_mode",
        name="Color mode",
        group=0x12,
        kind=Kind.SELECT,
        read_cmd=0x0B,
        option_cmd=0x0B,
        options={
            "Brightest": 0x00,
            "Movie": 0x01,
            "User 1": 0x02,
            "User 2": 0x03,
            "PC / Gaming": 0x04,
            "ViewMatch": 0x05,
            "Dynamic PC": 0x06,
            "Dynamic Movie": 0x07,
        },
        icon="mdi:palette",
        primary=True,
    ),
    Control(
        key="blank",
        name="Blank",
        group=0x12,
        kind=Kind.SWITCH,
        read_cmd=0x09,
        on=(0x09, 0x01),
        off=(0x09, 0x00),
        icon="mdi:monitor-off",
        primary=True,
    ),
    Control(
        key="freeze",
        name="Freeze",
        group=0x13,
        kind=Kind.SWITCH,
        read_cmd=0x00,
        on=(0x00, 0x01),
        off=(0x00, 0x00),
        icon="mdi:snowflake",
        primary=True,
    ),
    # ---- Lamp -----------------------------------------------------------
    Control(
        key="lamp_mode",
        name="Lamp mode",
        group=0x11,
        kind=Kind.SELECT,
        read_cmd=0x10,
        option_cmd=0x10,
        options={"Normal": 0x00, "Economic": 0x01},
        icon="mdi:lightbulb-on-outline",
        primary=True,
    ),
    Control(
        key=KEY_LAMP_HOURS,
        name="Lamp hours",
        group=0x15,
        kind=Kind.READONLY,
        read_cmd=0x01,
        icon="mdi:lightbulb-alert",
        diagnostic=True,
    ),
    Control(
        key=KEY_ERROR_STATUS,
        name="Error status",
        group=0x0C,
        kind=Kind.READONLY,
        read_cmd=0x0D,
        icon="mdi:alert-circle-outline",
        diagnostic=True,
    ),
    # ---- Audio ----------------------------------------------------------
    Control(
        key="mute",
        name="Mute",
        group=0x14,
        kind=Kind.SWITCH,
        read_cmd=0x00,
        on=(0x00, 0x01),
        off=(0x00, 0x00),
        icon="mdi:volume-off",
        primary=True,
    ),
    # Volume is the other command-byte oddity: up and down are separate
    # commands (0x01 / 0x02) and the value read lives at 0x03.
    Control(
        key="volume",
        name="Volume",
        group=0x14,
        kind=Kind.STEP,
        read_cmd=0x03,
        up=(0x01, 0x00),
        down=(0x02, 0x00),
        icon="mdi:volume-high",
        primary=True,
    ),
    # ---- Image adjustment (increment/decrement only) --------------------
    Control(
        key="contrast", name="Contrast", group=0x12, kind=Kind.STEP,
        read_cmd=0x02, up=(0x02, 0x01), down=(0x02, 0x00), icon="mdi:contrast-circle",
    ),
    Control(
        key="brightness", name="Brightness", group=0x12, kind=Kind.STEP,
        read_cmd=0x03, up=(0x03, 0x01), down=(0x03, 0x00), icon="mdi:brightness-6",
    ),
    Control(
        key="hue", name="Hue", group=0x12, kind=Kind.STEP,
        read_cmd=0x11, up=(0x11, 0x01), down=(0x11, 0x00), icon="mdi:palette-swatch",
    ),
    Control(
        key="saturation", name="Saturation", group=0x12, kind=Kind.STEP,
        read_cmd=0x12, up=(0x12, 0x01), down=(0x12, 0x00), icon="mdi:water",
    ),
    Control(
        key="gain", name="Gain", group=0x12, kind=Kind.STEP,
        read_cmd=0x13, up=(0x13, 0x01), down=(0x13, 0x00), icon="mdi:tune",
    ),
    Control(
        key="keystone_v", name="Keystone vertical", group=0x12, kind=Kind.STEP,
        read_cmd=0x0A, up=(0x0A, 0x01), down=(0x0A, 0x00), icon="mdi:crop-rotate",
    ),
    # Horizontal position: 0x01 shifts right, 0x00 shifts left.
    Control(
        key="h_position", name="Horizontal position", group=0x12, kind=Kind.STEP,
        read_cmd=0x06, up=(0x06, 0x01), down=(0x06, 0x00), icon="mdi:arrow-left-right",
    ),
    # Vertical position: the manual maps 0x00 to up and 0x01 to down -- the
    # opposite polarity to every other stepped control.
    Control(
        key="v_position", name="Vertical position", group=0x12, kind=Kind.STEP,
        read_cmd=0x07, up=(0x07, 0x00), down=(0x07, 0x01), icon="mdi:arrow-up-down",
    ),
    # ---- Colour ---------------------------------------------------------
    Control(
        key="color_temp",
        name="Color temperature",
        group=0x12,
        kind=Kind.SELECT,
        read_cmd=0x08,
        option_cmd=0x08,
        options={"T1": 0x00, "T2": 0x01, "T3": 0x02, "T4": 0x03},
        icon="mdi:thermometer",
    ),
    Control(
        key="primary_color",
        name="Primary color",
        group=0x12,
        kind=Kind.SELECT,
        read_cmd=0x10,
        option_cmd=0x10,
        options={"Red": 0x00, "Green": 0x01, "Blue": 0x02, "Cyan": 0x03, "Magenta": 0x04, "Yellow": 0x05},
        icon="mdi:invert-colors",
    ),
    Control(
        key="gamma",
        name="Gamma",
        group=0x11,
        kind=Kind.SELECT,
        read_cmd=0x2C,
        option_cmd=0x2C,
        options={f"Gamma {n}": n for n in range(1, 9)},
        icon="mdi:chart-bell-curve",
    ),
    Control(
        key="brilliant_color",
        name="BrilliantColor",
        group=0x12,
        kind=Kind.SWITCH,
        read_cmd=0x0F,
        on=(0x0F, 0x01),
        off=(0x0F, 0x00),
        icon="mdi:auto-fix",
    ),
    # ---- HDMI -----------------------------------------------------------
    Control(
        key="hdmi_format",
        name="HDMI format",
        group=0x11,
        kind=Kind.SELECT,
        read_cmd=0x28,
        option_cmd=0x28,
        options={"RGB": 0x00, "YUV": 0x01, "Auto": 0x02},
        icon="mdi:hdmi-port",
    ),
    Control(
        key="hdmi_range",
        name="HDMI range",
        group=0x11,
        kind=Kind.SELECT,
        read_cmd=0x29,
        option_cmd=0x29,
        options={"Enhanced": 0x00, "Normal": 0x01},
        icon="mdi:hdmi-port",
    ),
    Control(
        key="cec",
        name="CEC",
        group=0x11,
        kind=Kind.SWITCH,
        read_cmd=0x2B,
        on=(0x2B, 0x01),
        off=(0x2B, 0x00),
        icon="mdi:remote-tv",
    ),
    # ---- 3D -------------------------------------------------------------
    Control(
        key="sync_3d",
        name="3D sync",
        group=0x12,
        kind=Kind.SELECT,
        read_cmd=0x20,
        option_cmd=0x20,
        options={
            "Off": 0x00,
            "Auto": 0x01,
            "Frame Sequential": 0x02,
            "Frame Packing": 0x03,
            "Top-Bottom": 0x04,
            "Side-by-Side": 0x05,
        },
        icon="mdi:video-3d",
    ),
    Control(
        key="sync_3d_invert",
        name="3D sync invert",
        group=0x12,
        kind=Kind.SWITCH,
        read_cmd=0x21,
        on=(0x21, 0x01),
        off=(0x21, 0x00),
        icon="mdi:video-3d",
    ),
    # ---- Installation ---------------------------------------------------
    Control(
        key="position",
        name="Projector position",
        group=0x12,
        kind=Kind.SELECT,
        read_cmd=0x00,
        option_cmd=0x00,
        options={"Front Table": 0x00, "Rear Table": 0x01, "Rear Ceiling": 0x02, "Front Ceiling": 0x03},
        icon="mdi:screen-rotation",
    ),
    Control(
        key="high_altitude",
        name="High altitude mode",
        group=0x11,
        kind=Kind.SWITCH,
        read_cmd=0x0C,
        on=(0x0C, 0x01),
        off=(0x0C, 0x00),
        icon="mdi:image-filter-hdr",
    ),
    Control(
        key="splash_screen",
        name="Splash screen",
        group=0x11,
        kind=Kind.SELECT,
        read_cmd=0x0A,
        option_cmd=0x0A,
        options={"Black": 0x00, "Blue": 0x01, "ViewSonic": 0x02, "Screen Capture": 0x03, "Off": 0x04},
        icon="mdi:image",
    ),
    Control(
        key="message",
        name="On-screen messages",
        group=0x11,
        kind=Kind.SWITCH,
        read_cmd=0x27,
        on=(0x27, 0x01),
        off=(0x27, 0x00),
        icon="mdi:message-text",
    ),
    Control(
        key="quick_auto_search",
        name="Quick auto search",
        group=0x13,
        kind=Kind.SWITCH,
        read_cmd=0x02,
        on=(0x02, 0x01),
        off=(0x02, 0x00),
        icon="mdi:magnify-scan",
    ),
    Control(
        key="quick_power_off",
        name="Quick power off",
        group=0x11,
        kind=Kind.SWITCH,
        read_cmd=0x0B,
        on=(0x0B, 0x01),
        off=(0x0B, 0x00),
        icon="mdi:power-sleep",
    ),
    Control(
        key="remote_code",
        name="Remote control code",
        group=0x0C,
        kind=Kind.SELECT,
        read_cmd=0x48,
        option_cmd=0x48,
        options={"Code A": 0x00, "Code B": 0x01},
        icon="mdi:remote",
    ),
    # ---- One-shot actions ------------------------------------------------
    Control(
        key="auto_adjust",
        name="Auto adjust",
        group=0x12,
        kind=Kind.EXECUTE,
        execute=(0x05, 0x00),
        icon="mdi:auto-fix",
    ),
    Control(
        key="reset_color",
        name="Reset color settings",
        group=0x11,
        kind=Kind.EXECUTE,
        execute=(0x2A, 0x00),
        icon="mdi:palette-outline",
    ),
    # Destructive: factory-resets the projector. Kept because the command
    # exists, but it is deliberately the least convenient thing here.
    Control(
        key="reset_all",
        name="Reset all settings",
        group=0x11,
        kind=Kind.EXECUTE,
        execute=(0x02, 0x00),
        icon="mdi:restore-alert",
    ),
    # Destructive: clears the lamp-life counter. Only correct after a
    # physical lamp replacement.
    Control(
        key="reset_lamp_hours",
        name="Reset lamp hours",
        group=0x15,
        kind=Kind.EXECUTE,
        execute=(0x01, 0x00),
        icon="mdi:lightbulb-question",
    ),
)

CONTROLS_BY_KEY: Final[dict[str, Control]] = {c.key: c for c in (POWER, *CONTROLS)}
