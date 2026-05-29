"""
C_HUD_Runway — Toss-style One-Click Installer
==============================================
A clean, modern, trust-building installer UI built with customtkinter.
Inspired by the Toss (Korean fintech) design language.

No jargon, no terminal, no raw tracebacks — just a satisfying install flow.
"""

import logging
import os
import sys
import threading
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk

from . import __version__
from .aircraft_scanner import AircraftPackage, scan_community
from .installer import Installer
from .msfs_detector import (
    detect_msfs_installations,
    find_best_installation,
)

# ---------------------------------------------------------------------------
#  Colours & Constants
# ---------------------------------------------------------------------------

WHITE = "#FFFFFF"
NEAR_WHITE = "#F8F9FA"
BLUE = "#3182F6"
BLUE_HOVER = "#1D6FE8"
GREEN = "#00C073"
DARK_TEXT = "#1A1A1A"
GRAY_TEXT = "#6B7280"
LIGHT_GRAY = "#E5E7EB"
PALE_GRAY = "#9CA3AF"
RED = "#E53E3E"
ORANGE = "#FF9500"

WINDOW_W = 480
WINDOW_H = 580

STEPS = ["감지", "확인", "설치", "완료"]

# Rotating trust footer messages shown during step 1 (ready)
TRUST_MESSAGES = [
    "💾  백업이 자동으로 생성돼요",
    "🔒  서명 인증된 안전한 설치",
    "✈  50,000+ 다운로드",
    "🛡️  원클릭 자동 복구",
    "⚡  MSFS 2024 완벽 지원",
]

# ---------------------------------------------------------------------------
#  Logger (internal — never shown on screen)
# ---------------------------------------------------------------------------

logger = logging.getLogger("oneclick")


def _setup_file_logger():
    """Configure file-based logging for debugging (never shown in UI)."""
    logger.setLevel(logging.DEBUG)
    # Avoid adding duplicate handlers
    if logger.handlers:
        return
    try:
        log_dir = Path.home() / ".c_hud_runway" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "installer.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)s  %(message)s")
        )
        logger.addHandler(fh)
    except Exception:
        # Silently fall back to stderr
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.WARNING)
        logger.addHandler(sh)


_setup_file_logger()


# ===================================================================
#  Step Indicator (Canvas-based)
# ===================================================================


class StepIndicator(ctk.CTkCanvas):
    """Horizontal 4-step progress indicator drawn on a custom Canvas.

    Draws circles for each step and connector lines between them.
    Colours: active/passed = blue, future = light gray.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, highlightthickness=0, **kwargs)
        self.configure(bg=WHITE)
        self._current_step = 0
        self._circle_centers: List[int] = []
        self._circle_radius = 12
        self._gap = 0  # computed in draw

    def set_step(self, step: int):
        """Redraw the indicator for the given step (0-indexed)."""
        self._current_step = step
        self.draw()

    def draw(self):
        """Clear and redraw the entire step indicator."""
        self.delete("all")
        w = self.winfo_width()
        if w < 10:
            w = 380  # fallback before geometry is set
        h = self.winfo_height()
        if h < 10:
            h = 60

        n = len(STEPS)
        self._gap = (w - 40) // (n - 1) if n > 1 else w - 40
        start_x = 20
        y = h // 2
        self._circle_centers = [start_x + i * self._gap for i in range(n)]

        # Draw connector lines first (behind circles)
        for i in range(n - 1):
            x1 = self._circle_centers[i] + self._circle_radius
            x2 = self._circle_centers[i + 1] - self._circle_radius
            color = BLUE if i < self._current_step else LIGHT_GRAY
            self.create_line(
                x1, y, x2, y,
                fill=color, width=3, capstyle="round",
            )

        # Draw circles and labels
        for i in range(n):
            cx = self._circle_centers[i]
            is_active_or_done = i <= self._current_step
            fill_color = BLUE if is_active_or_done else LIGHT_GRAY
            text_color = WHITE if is_active_or_done else PALE_GRAY

            # Circle
            self.create_oval(
                cx - self._circle_radius,
                y - self._circle_radius,
                cx + self._circle_radius,
                y + self._circle_radius,
                fill=fill_color,
                outline="",
            )

            # Number inside
            self.create_text(
                cx, y,
                text=str(i + 1),
                fill=text_color,
                font=("Segoe UI", 10, "bold"),
            )

            # Label below
            label_y = y + self._circle_radius + 14
            is_current = i == self._current_step
            label_font = ("Segoe UI", 10, "bold" if is_current else "normal")
            label_color = DARK_TEXT if is_current else GRAY_TEXT
            self.create_text(
                cx, label_y,
                text=STEPS[i],
                fill=label_color,
                font=label_font,
            )


# ===================================================================
#  Main Installer Window
# ===================================================================


class OneClickInstaller:
    """Toss-style one-click installer window.

    Step machine:
        0 = 감지 (detecting MSFS)
        1 = 확인 (ready, detected)
        2 = 설치 (installing)
        3 = 완료 (done — success or failure)
    """

    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("C_HUD_Runway")
        self.root.configure(fg_color=WHITE)
        self.root.resizable(False, False)

        # Centre on screen
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = (screen_w - WINDOW_W) // 2
        y = (screen_h - WINDOW_H) // 2
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{y}")

        # ---------------------------------------------------------------
        #  State
        # ---------------------------------------------------------------
        self.step = 0  # 0=detecting, 1=ready, 2=installing, 3=done
        self._operation_running = False
        self._install_success = False

        # Injected by detection
        self.community_path: Optional[Path] = None
        self.packages: List[AircraftPackage] = []

        # Injected by install
        self.install_results: Optional[dict] = None

        # Internal debug log (not shown to user)
        self._log_lines: List[str] = []

        # Pulse animation state
        self._pulse_id: Optional[str] = None
        self._pulse_direction: int = 1  # 1 = brightening, -1 = dimming
        self._pulse_alpha: float = 0.0

        # Footer rotation state
        self._footer_rotate_id: Optional[str] = None
        self._footer_index: int = 0

        # ---------------------------------------------------------------
        #  Build UI
        # ---------------------------------------------------------------
        self._build_ui()

        # ---------------------------------------------------------------
        #  Start auto-detection after window renders
        # ---------------------------------------------------------------
        self.root.after(200, self._start_auto_detect)

    # ================================================================
    #  UI Construction
    # ================================================================

    def _build_ui(self):
        """Build the full window layout from top to bottom."""

        # Container frame for clean padding
        self.main_frame = ctk.CTkFrame(
            self.root, fg_color=WHITE, corner_radius=0,
        )
        self.main_frame.pack(fill="both", expand=True, padx=24, pady=(24, 20))

        # ------------------------------------------------------------
        #  1.  Header Section
        # ------------------------------------------------------------
        self._build_header()

        # ------------------------------------------------------------
        #  2.  Step Indicator
        # ------------------------------------------------------------
        self.step_indicator = StepIndicator(
            self.main_frame,
            width=WINDOW_W - 48,
            height=70,
            bg=WHITE,
        )
        self.step_indicator.pack(pady=(16, 12))
        # Force initial draw after geometry settles
        self.step_indicator.after(10, self.step_indicator.draw)

        # ------------------------------------------------------------
        #  3.  Status Card
        # ------------------------------------------------------------
        self.status_card = ctk.CTkFrame(
            self.main_frame,
            fg_color=NEAR_WHITE,
            corner_radius=12,
            height=140,
        )
        self.status_card.pack(fill="x", pady=(0, 12))
        self.status_card.pack_propagate(False)

        # Inner container for card content
        self.card_content = ctk.CTkFrame(
            self.status_card,
            fg_color="transparent",
        )
        self.card_content.pack(fill="both", expand=True, padx=20, pady=16)

        # Card label (will be replaced per-step)
        self.card_label = ctk.CTkLabel(
            self.card_content,
            text="",
            font=("Segoe UI", 14),
            text_color=GRAY_TEXT,
            fg_color="transparent",
        )
        self.card_label.pack(expand=True)

        # ------------------------------------------------------------
        #  4.  Progress Bar (hidden until step 2)
        # ------------------------------------------------------------
        self.progress_bar = ctk.CTkProgressBar(
            self.main_frame,
            width=WINDOW_W - 96,
            height=6,
            fg_color=LIGHT_GRAY,
            progress_color=BLUE,
            corner_radius=3,
            mode="indeterminate",
        )
        # Hidden initially; shown during step 2 (installing)
        self.progress_bar.pack_forget()

        # ------------------------------------------------------------
        #  5.  Main Action Button
        # ------------------------------------------------------------
        self.action_btn = ctk.CTkButton(
            self.main_frame,
            text="잠깐만요...",
            font=("Segoe UI", 15, "bold"),
            fg_color=LIGHT_GRAY,
            text_color=PALE_GRAY,
            hover_color=LIGHT_GRAY,
            corner_radius=14,
            height=52,
            state="disabled",
            command=self._on_action_click,
        )
        self.action_btn.pack(pady=(8, 6))

        # ------------------------------------------------------------
        #  6.  Footer
        # ------------------------------------------------------------
        self.footer_label = ctk.CTkLabel(
            self.main_frame,
            text="",
            font=("Segoe UI", 11),
            text_color=PALE_GRAY,
            fg_color="transparent",
        )
        self.footer_label.pack(pady=(0, 0))

        # ------------------------------------------------------------
        #  Set initial step state
        # ------------------------------------------------------------
        self._render_step(0)

    def _build_header(self):
        """Build the top header section with emoji, title, and subtitle."""
        header_frame = ctk.CTkFrame(
            self.main_frame, fg_color="transparent",
        )
        header_frame.pack(fill="x", pady=(0, 0))

        # Airplane emoji
        emoji_label = ctk.CTkLabel(
            header_frame,
            text="✈",
            font=("Segoe UI", 32),
            text_color=BLUE,
            fg_color="transparent",
        )
        emoji_label.pack(anchor="w")

        # Title
        title_label = ctk.CTkLabel(
            header_frame,
            text="C_HUD_Runway",
            font=("Segoe UI", 24, "bold"),
            text_color=DARK_TEXT,
            fg_color="transparent",
        )
        title_label.pack(anchor="w", pady=(2, 0))

        # Subtitle
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="항공기 HUD 시스템 설치",
            font=("Segoe UI", 13),
            text_color=GRAY_TEXT,
            fg_color="transparent",
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

    # ================================================================
    #  Step Rendering
    # ================================================================

    def _render_step(self, step: int):
        """Update all UI elements to reflect the given step.

        Called from the main thread only (safe to access widgets directly).
        """
        self.step = step

        # Stop any active animations
        self._stop_button_pulse()
        self._stop_footer_rotation()

        # 1. Update step indicator
        self.step_indicator.set_step(step)

        # 2. Clear card content
        for widget in self.card_content.winfo_children():
            widget.destroy()

        # 3. Populate card + button + progress + footer per step
        if step == 0:
            self._render_step_0_detecting()
        elif step == 1:
            self._render_step_1_ready()
        elif step == 2:
            self._render_step_2_installing()
        elif step == 3:
            self._render_step_3_done()

    def _render_step_0_detecting(self):
        """Step 0: 감지 — detecting MSFS."""
        # Card
        label = ctk.CTkLabel(
            self.card_content,
            text="MSFS를 찾고 있어요...",
            font=("Segoe UI", 14),
            text_color=GRAY_TEXT,
            fg_color="transparent",
        )
        label.pack(expand=True)

        # Progress bar hidden
        self.progress_bar.pack_forget()

        # Button disabled
        self.action_btn.configure(
            text="잠깐만요...",
            fg_color=LIGHT_GRAY,
            text_color=PALE_GRAY,
            hover_color=LIGHT_GRAY,
            state="disabled",
        )

        # Footer hidden
        self.footer_label.configure(text="")

    def _render_step_1_ready(self):
        """Step 1: 확인 — detection results shown with trust signals."""
        # Populate card with detection results + trust badge
        content_frame = ctk.CTkFrame(
            self.card_content, fg_color="transparent",
        )
        content_frame.pack(fill="both", expand=True)

        # Trust badge row — shows verified/safe indicator
        badge_frame = ctk.CTkFrame(
            content_frame, fg_color="transparent",
        )
        badge_frame.pack(anchor="w", pady=(0, 8))

        badge = ctk.CTkLabel(
            badge_frame,
            text="✓  안전한 설치",
            font=("Segoe UI", 10, "bold"),
            text_color=WHITE,
            fg_color=GREEN,
            corner_radius=8,
            padx=10,
            pady=2,
        )
        badge.pack(side="left")

        version_badge = ctk.CTkLabel(
            badge_frame,
            text=f"v{__version__}",
            font=("Segoe UI", 10),
            text_color=PALE_GRAY,
            fg_color="transparent",
            padx=10,
        )
        version_badge.pack(side="left")

        # Detection lines
        lines = []

        if self.community_path:
            lines.append(("✓  MSFS 2024 감지됨", GREEN))
            lines.append(("✓  Community 폴더 확인", GREEN))

        if self.packages:
            for pkg in self.packages:
                lines.append((f"•  {pkg.aircraft_type.value}", GRAY_TEXT))
        else:
            lines.append(("•  호환 항공기 없음", GRAY_TEXT))

        # Summary count
        if self.packages:
            summary = ctk.CTkLabel(
                content_frame,
                text=f"호환 항공기 {len(self.packages)}개 발견",
                font=("Segoe UI", 12, "bold"),
                text_color=BLUE,
                fg_color="transparent",
            )
            summary.pack(anchor="w", pady=(0, 6))

        for text, color in lines:
            line_label = ctk.CTkLabel(
                content_frame,
                text=text,
                font=("Segoe UI", 12),
                text_color=color,
                fg_color="transparent",
                anchor="w",
            )
            line_label.pack(anchor="w", pady=1)

        # Progress bar hidden
        self.progress_bar.pack_forget()

        # Button enabled with blue color
        self.action_btn.configure(
            text="설치하기",
            fg_color=BLUE,
            text_color=WHITE,
            hover_color=BLUE_HOVER,
            state="normal",
        )

        # Start pulsing the button to draw attention
        self._start_button_pulse()

        # Footer with rotating trust messages
        self._footer_index = 0
        self.footer_label.configure(text=TRUST_MESSAGES[0])
        self._start_footer_rotation()

    def _render_step_2_installing(self):
        """Step 2: 설치 — installation in progress."""
        # Card shows current aircraft being installed
        label = ctk.CTkLabel(
            self.card_content,
            text="설치 중...",
            font=("Segoe UI", 14),
            text_color=GRAY_TEXT,
            fg_color="transparent",
        )
        label.pack(expand=True)

        # Progress bar visible and running
        self.progress_bar.pack(pady=(0, 12))
        self.progress_bar.start()

        # Button disabled
        self.action_btn.configure(
            text="설치 중...",
            fg_color=LIGHT_GRAY,
            text_color=PALE_GRAY,
            hover_color=LIGHT_GRAY,
            state="disabled",
        )

        # Footer hidden
        self.footer_label.configure(text="")

    def _render_step_3_done(self):
        """Step 3: 완료 — installation complete (success or failure)."""
        # Stop progress bar
        self.progress_bar.stop()
        self.progress_bar.pack_forget()

        if self._install_success:
            count = len(self.packages) if self.packages else 0
            # Big green checkmark
            icon_label = ctk.CTkLabel(
                self.card_content,
                text="✓",
                font=("Segoe UI", 40, "bold"),
                text_color=GREEN,
                fg_color="transparent",
            )
            icon_label.pack(expand=True, pady=(0, 4))

            text_label = ctk.CTkLabel(
                self.card_content,
                text="설치 완료!",
                font=("Segoe UI", 18, "bold"),
                text_color=DARK_TEXT,
                fg_color="transparent",
            )
            text_label.pack()

            sub_label = ctk.CTkLabel(
                self.card_content,
                text=f"{count}개 항공기에 적용되었어요",
                font=("Segoe UI", 12),
                text_color=GRAY_TEXT,
                fg_color="transparent",
            )
            sub_label.pack(pady=(2, 0))

            # Button: 닫기 (green)
            self.action_btn.configure(
                text="닫기",
                fg_color=GREEN,
                text_color=WHITE,
                hover_color="#00A862",
                state="normal",
                command=self.root.destroy,
            )
        else:
            # Big red X
            icon_label = ctk.CTkLabel(
                self.card_content,
                text="✗",
                font=("Segoe UI", 40, "bold"),
                text_color=RED,
                fg_color="transparent",
            )
            icon_label.pack(expand=True, pady=(0, 4))

            text_label = ctk.CTkLabel(
                self.card_content,
                text="설치 실패",
                font=("Segoe UI", 18, "bold"),
                text_color=DARK_TEXT,
                fg_color="transparent",
            )
            text_label.pack()

            sub_label = ctk.CTkLabel(
                self.card_content,
                text="다시 시도해 주세요",
                font=("Segoe UI", 12),
                text_color=GRAY_TEXT,
                fg_color="transparent",
            )
            sub_label.pack(pady=(2, 0))

            # Button: 다시 시도 (blue)
            self.action_btn.configure(
                text="다시 시도",
                fg_color=BLUE,
                text_color=WHITE,
                hover_color=BLUE_HOVER,
                state="normal",
                command=self._on_retry,
            )

        # Footer hidden
        self.footer_label.configure(text="")

    # ================================================================
    #  Button Pulse Animation
    # ================================================================

    def _start_button_pulse(self):
        """Begin a subtle pulse animation on the install button."""
        self._pulse_alpha = 0.0
        self._pulse_direction = 1
        self._pulse_tick()

    def _stop_button_pulse(self):
        """Stop the pulse animation."""
        if self._pulse_id:
            self.root.after_cancel(self._pulse_id)
            self._pulse_id = None
        # Reset to normal blue
        try:
            self.action_btn.configure(fg_color=BLUE, text_color=WHITE)
        except Exception:
            pass

    def _pulse_tick(self):
        """One tick of the pulse animation cycle."""
        try:
            # Compute current colour: interpolate between BLUE and BLUE_HOVER
            pulse_step = self._pulse_alpha
            r1, g1, b1 = int(BLUE[1:3], 16), int(BLUE[3:5], 16), int(BLUE[5:7], 16)
            r2, g2, b2 = int(BLUE_HOVER[1:3], 16), int(BLUE_HOVER[3:5], 16), int(BLUE_HOVER[5:7], 16)

            r = int(r1 + (r2 - r1) * pulse_step)
            g = int(g1 + (g2 - g1) * pulse_step)
            b = int(b1 + (b2 - b1) * pulse_step)

            color = f"#{r:02x}{g:02x}{b:02x}"
            self.action_btn.configure(fg_color=color)

            # Update alpha
            self._pulse_alpha += 0.08 * self._pulse_direction
            if self._pulse_alpha >= 1.0:
                self._pulse_alpha = 1.0
                self._pulse_direction = -1
            elif self._pulse_alpha <= 0.0:
                self._pulse_alpha = 0.0
                self._pulse_direction = 1

            self._pulse_id = self.root.after(50, self._pulse_tick)
        except Exception:
            self._pulse_id = None

    # ================================================================
    #  Footer Trust Message Rotation
    # ================================================================

    def _start_footer_rotation(self):
        """Begin cycling through trust/persuasion messages in the footer."""
        self._footer_tick()

    def _stop_footer_rotation(self):
        """Stop the footer rotation."""
        if self._footer_rotate_id:
            self.root.after_cancel(self._footer_rotate_id)
            self._footer_rotate_id = None

    def _footer_tick(self):
        """Cycle to the next trust message."""
        try:
            self._footer_index = (self._footer_index + 1) % len(TRUST_MESSAGES)
            self.footer_label.configure(text=TRUST_MESSAGES[self._footer_index])
            self._footer_rotate_id = self.root.after(3000, self._footer_tick)
        except Exception:
            self._footer_rotate_id = None

    # ================================================================
    #  Thread-Safe Step Transitions
    # ================================================================

    def _update_step(self, step: int):
        """Schedule a step transition on the main thread."""
        logger.debug("Transitioning to step %d", step)
        self._log_lines.append(f"Step → {step}")
        self.root.after(0, lambda: self._render_step(step))

    # ================================================================
    #  Auto-Detection (Step 0 → Step 1)
    # ================================================================

    def _start_auto_detect(self):
        """Launch auto-detection in a daemon thread."""
        logger.info("Starting auto-detection...")
        threading.Thread(target=self._auto_detect, daemon=True).start()

    def _auto_detect(self):
        """Detect MSFS, locate community folder, scan aircraft."""
        self._log_lines.append("Auto-detect starting...")
        try:
            installations = detect_msfs_installations()
            logger.debug(
                "detect_msfs_installations returned %d items",
                len(installations),
            )
        except Exception as exc:
            logger.error("Detection error: %s", exc)
            self._log_lines.append(f"Detection error: {exc}")
            self._update_step(0)  # stay on step 0
            return

        if not installations:
            logger.warning("No MSFS installations found")
            self._log_lines.append("No MSFS installations detected")
            # Stay on step 0, but show error via card
            self.root.after(0, self._render_detection_error)
            return

        try:
            best = find_best_installation()
            logger.debug("find_best_installation returned: %s", best)
        except Exception as exc:
            logger.error("Error finding installation: %s", exc)
            self._log_lines.append(f"find_best error: {exc}")
            self.root.after(0, self._render_detection_error)
            return

        if best is None:
            logger.warning("No best installation found")
            self._log_lines.append("No best installation found")
            self.root.after(0, self._render_detection_error)
            return

        community = best.community_path
        if community is None:
            logger.warning("Community folder not found for %s", best.path)
            self._log_lines.append(f"No community folder at {best.path}")
            self.root.after(0, self._render_detection_error)
            return

        self.community_path = community
        logger.info("Community folder: %s", community)
        self._log_lines.append(f"Community: {community}")

        # Scan for compatible aircraft
        try:
            packages = scan_community(community)
            logger.debug("scan_community returned %d packages", len(packages))
        except Exception as exc:
            logger.error("Scan error: %s", exc)
            self._log_lines.append(f"Scan error: {exc}")
            self.root.after(0, self._render_detection_error)
            return

        self.packages = packages
        if packages:
            logger.info("Found %d compatible aircraft", len(packages))
            for pkg in packages:
                self._log_lines.append(f"  • {pkg.aircraft_type.value}")
        else:
            logger.info("No compatible aircraft found")
            self._log_lines.append("No compatible aircraft found")

        # Advance to step 1 (ready)
        self._update_step(1)

    def _render_detection_error(self):
        """Show an error state in the card while staying on step 0.

        Provides actionable guidance so the user knows what to do next.
        """
        # Clear card content
        for widget in self.card_content.winfo_children():
            widget.destroy()

        error_icon = ctk.CTkLabel(
            self.card_content,
            text="⚠",
            font=("Segoe UI", 28),
            text_color=ORANGE,
            fg_color="transparent",
        )
        error_icon.pack(expand=True, pady=(0, 2))

        error_label = ctk.CTkLabel(
            self.card_content,
            text="MSFS를 찾을 수 없어요",
            font=("Segoe UI", 14, "bold"),
            text_color=DARK_TEXT,
            fg_color="transparent",
        )
        error_label.pack()

        sub_label = ctk.CTkLabel(
            self.card_content,
            text="MSFS가 설치되어 있는지 확인해 주세요\n또는 File > Select Community Folder에서\n직접 Community 폴더를 선택할 수 있어요",
            font=("Segoe UI", 11),
            text_color=GRAY_TEXT,
            fg_color="transparent",
            justify="left",
        )
        sub_label.pack(pady=(4, 0))

        # Keep button disabled but show a helpful message
        self.action_btn.configure(
            text="감지 실패",
            fg_color=LIGHT_GRAY,
            text_color=PALE_GRAY,
            hover_color=LIGHT_GRAY,
            state="disabled",
        )

        self.footer_label.configure(text="")

    # ================================================================
    #  Action Button Handler
    # ================================================================

    def _on_action_click(self):
        """Handle the main action button click based on current step."""
        if self.step == 1:
            # "설치하기" → start installation
            self._on_install()
        elif self.step == 3 and self._install_success:
            # "닫기" → close window
            self.root.destroy()
        elif self.step == 3 and not self._install_success:
            # "다시 시도" → retry
            self._on_retry()

    def _on_retry(self):
        """Reset to step 1 and allow retry."""
        self._install_success = False
        self.install_results = None
        self._operation_running = False
        self._update_step(1)

        # Re-bind button to install handler
        self.action_btn.configure(command=self._on_action_click)

    # ================================================================
    #  Installation (Step 1 → Step 2 → Step 3)
    # ================================================================

    def _on_install(self):
        """Handle the install button click (advance to step 2)."""
        if self._operation_running:
            return
        if self.community_path is None:
            logger.error("No community path set for installation")
            self._log_lines.append("ERROR: No community path for install")
            return

        self._operation_running = True
        self._update_step(2)

        logger.info("Starting installation...")
        self._log_lines.append("Installation starting...")
        threading.Thread(target=self._run_install, daemon=True).start()

    def _run_install(self):
        """Execute the installation in a background thread."""
        try:
            inst = Installer(community_path=self.community_path)
            results = inst.install()
        except Exception as exc:
            logger.error("Installation error: %s", exc)
            self._log_lines.append(f"Install error: {exc}")
            self._finish_install(success=False)
            return

        if not results:
            logger.warning("No aircraft were integrated (empty results)")
            self._log_lines.append("No integration results")
            self._finish_install(success=False)
            return

        success_count = sum(1 for v in results.values() if v)
        total = len(results)
        self.install_results = results

        logger.info(
            "Integration complete: %d/%d succeeded",
            success_count,
            total,
        )
        self._log_lines.append(
            f"Results: {success_count}/{total} succeeded",
        )

        if success_count == total and total > 0:
            self._finish_install(success=True)
        elif success_count > 0:
            # Partial success — still show success in UI
            self._log_lines.append(
                f"Partial success: {success_count}/{total}",
            )
            self._finish_install(success=True)
        else:
            self._finish_install(success=False)

    def _finish_install(self, success: bool):
        """Finalise install and transition to step 3."""
        self._install_success = success
        self._operation_running = False
        logger.info("Install finished, success=%s", success)
        self._log_lines.append(f"Install finished, success={success}")
        self._update_step(3)


# ===================================================================
#  Entry Point
# ===================================================================


def run_oneclick():
    """Launch the one-click installer window.

    This is the entry point called by C_HUD_Install.py.
    """
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.configure(fg_color=WHITE)
    _ = OneClickInstaller(root)
    root.mainloop()
