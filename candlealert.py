import customtkinter as ctk
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
from datetime import datetime, timedelta, time
import threading
import os
import sys
import json
import shutil

# System Tray and Audio libraries
from PIL import Image
import pystray
from pystray import MenuItem as item
try:
    import winsound
except ImportError:
    winsound = None

try:
    import winreg
except ImportError:
    winreg = None

# ---------------------------------------------------------------------------
# Windows Startup Registry Helpers
# ---------------------------------------------------------------------------
APP_NAME = "CandleAlert"
STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def get_startup_command():
    """Return the command to register for Windows startup."""
    if getattr(sys, 'frozen', False):
        # Running as compiled .exe (PyInstaller)
        return f'"{sys.executable}"'
    else:
        # Running as a .py script
        script_path = os.path.abspath(__file__)
        python_exe = sys.executable
        return f'"{python_exe}" "{script_path}"'

def is_startup_enabled():
    """Check if the app is registered to launch on Windows startup."""
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False

def set_startup_enabled(enable: bool):
    """Write or remove the Windows startup registry entry for this app."""
    if winreg is None:
        return
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, get_startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError as e:
        print(f"[Startup] Registry error: {e}")

# Frame and Theme Configurations
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Premium Theme Palette
COLOR_BG_MAIN = "#080b11"
COLOR_BG_CARD = "#121620"
COLOR_SIDEBAR = "#0c0f16"
COLOR_TEXT_MAIN = "#ffffff"
COLOR_TEXT_MUTED = "#64748b"
COLOR_GREEN = "#22c55e"
COLOR_BLUE = "#3b82f6"
COLOR_PURPLE = "#a855f7"
COLOR_RED = "#ef4444"
COLOR_ROW_SELECTED = "#1e293b" 

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_settings_path():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "settings.json")

def discover_sounds():
    sounds_dir = os.path.abspath("sounds")
    if not os.path.exists(sounds_dir):
        os.makedirs(sounds_dir)
        
    local_sounds = {
        "Default Beep": resource_path(os.path.join("sounds", "beep.wav")),
        "Soft Chime": resource_path(os.path.join("sounds", "chime.wav")),
        "Alert Bell": resource_path(os.path.join("sounds", "bell.wav")),
        "Cash Register": resource_path(os.path.join("sounds", "cash_register.wav"))
    }
    
    try:
        for filename in os.listdir(sounds_dir):
            if filename.lower().endswith(".wav"):
                name = os.path.splitext(filename)[0].replace("_", " ").title()
                path = os.path.join(sounds_dir, filename)
                if name not in local_sounds:
                    local_sounds[name] = path
    except Exception:
        pass
    return local_sounds

SOUNDS = discover_sounds()

# Master Global Session Architecture Database
MARKET_RULES = {
    "Indian Stock Market (NSE)":          {"open": "09:15", "close": "15:30", "type": "equities"},
    "US Stock Market (NYSE)":             {"open": "09:30", "close": "16:00", "type": "equities"},
    "London Stock Exchange (LSE)":        {"open": "08:00", "close": "16:30", "type": "equities"},
    "Tokyo Stock Exchange (TSE)":         {"open": "09:00", "close": "15:00", "type": "split", "lunch_open": "11:30", "lunch_close": "12:30"},
    "Hong Kong Stock Exchange (HKEX)":    {"open": "09:30", "close": "16:00", "type": "split", "lunch_open": "12:00", "lunch_close": "13:00"},
    "Forex Market (Continuous 24/5)":     {"open": "00:00", "close": "24:00", "type": "forex"},
    "Crypto Market (Continuous 24/7)":    {"open": "00:00", "close": "24:00", "type": "continuous"}
}

class AdvancedCandleAlertApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("CandleAlert Pro Workstation")
        self.geometry("1020x680")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_MAIN)
        
        self.is_running = False
        self.tray_icon = None
        self.slot_triggers = {}
        
        # Swappable Tabs States
        self.current_page = "Countdown"
        self.alerts_log = []
        self.sidebar_buttons = {}
        
        # Load persisted config
        self.loaded_config = self.load_settings()
        self.selected_market = self.loaded_config.get("selected_market", "Indian Stock Market (NSE)")

        # Full professional-tier timeframe library natively populated
        self.timeframe_settings = self.loaded_config.get("timeframe_settings", {
            "1 Minute":   {"mins": 1,    "buffer": "10 Seconds", "sound": "Alert Bell", "enabled": True},
            "3 Minutes":  {"mins": 3,    "buffer": "10 Seconds", "sound": "Default Beep", "enabled": True},
            "5 Minutes":  {"mins": 5,    "buffer": "10 Seconds", "sound": "Cash Register", "enabled": True},
            "15 Minutes": {"mins": 15,   "buffer": "30 Seconds", "sound": "Soft Chime", "enabled": True},
            "30 Minutes": {"mins": 30,   "buffer": "30 Seconds", "sound": "Alert Bell", "enabled": True},
            "1 Hour":     {"mins": 60,   "buffer": "1 Minute",   "sound": "Default Beep", "enabled": True},
            "4 Hours":    {"mins": 240,  "buffer": "1 Minute",   "sound": "Soft Chime", "enabled": True},
            "1 Day":      {"mins": 1440, "buffer": "5 Minutes",  "sound": "Cash Register", "enabled": True}
        })

        self.protocol('WM_DELETE_WINDOW', self.handle_close_window)
        self.setup_ui_layout()
        
        default_tf = list(self.timeframe_settings.keys())[0] if self.timeframe_settings else "5 Minutes"
        self.on_param_change(default_tf)
        self.update_live_dashboard_loop()

    def load_settings(self):
        path = get_settings_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_settings(self):
        config = {
            "selected_market": self.selected_market,
            "enable_audio_alerts": self.loaded_config.get("enable_audio_alerts", True),
            "show_system_notifications": self.loaded_config.get("show_system_notifications", True),
            "close_minimizes_to_tray": self.loaded_config.get("close_minimizes_to_tray", True),
            "timeframe_settings": self.timeframe_settings
        }
        try:
            with open(get_settings_path(), "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def setup_ui_layout(self):
        # 1. SIDEBAR
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=COLOR_SIDEBAR, border_width=0)
        self.sidebar.pack(side="left", fill="y")

        brand_lbl = ctk.CTkLabel(self.sidebar, text="🔔 CandleAlert", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_TEXT_MAIN)
        brand_lbl.pack(pady=(25, 2), padx=20, anchor="w")
        ctk.CTkLabel(self.sidebar, text="Professional Workstation", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(pady=(0, 30), padx=20, anchor="w")

        tabs = [
            ("⏱s Countdown", "Countdown"),
            ("🔔 Alerts", "Alerts"),
            ("⚙️ Settings", "Settings"),
            ("🔊 Sound", "Sound"),
            ("🛡️ General", "General"),
            ("ℹ️ About", "About")
        ]

        for display_name, tab_id in tabs:
            btn = ctk.CTkButton(
                self.sidebar, text=display_name, anchor="w", height=38, 
                fg_color="transparent",
                text_color=COLOR_TEXT_MAIN, 
                font=ctk.CTkFont(size=13, weight="normal"),
                hover_color="#1c2331", corner_radius=8,
                command=lambda tid=tab_id: self.show_page(tid)
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.sidebar_buttons[tab_id] = btn

        self.status_card = ctk.CTkFrame(self.sidebar, fg_color="#0e131f", height=90, corner_radius=10)
        self.status_card.pack(side="bottom", fill="x", padx=12, pady=15)
        
        status_header = ctk.CTkFrame(self.status_card, fg_color="transparent")
        status_header.pack(pady=(10, 0), padx=15, anchor="w")
        
        self.status_dot = ctk.CTkLabel(status_header, text="●", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.status_dot.pack(side="left", padx=(0, 5))
        
        ctk.CTkLabel(status_header, text="Engine Status", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
        
        self.status_text = ctk.CTkLabel(self.status_card, text="IDLE", font=ctk.CTkFont(size=15, weight="bold"), text_color=COLOR_TEXT_MUTED)
        self.status_text.pack(pady=(2, 2), padx=15, anchor="w")
        
        ctk.CTkLabel(self.sidebar, text="Version 1.0.0  |  © 2026", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="bottom", pady=(0, 5))

        # 2. MAIN CONTAINER
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(side="left", fill="both", expand=True)
        
        # Render initial page
        self.show_page("Countdown")

    def show_page(self, page_name):
        self.current_page = page_name
        self.clear_main_container()
        
        # Update sidebar tabs styling
        for tab_id, btn in self.sidebar_buttons.items():
            if tab_id == page_name:
                btn.configure(
                    fg_color="#161b26", 
                    text_color=COLOR_GREEN, 
                    font=ctk.CTkFont(size=13, weight="bold")
                )
            else:
                btn.configure(
                    fg_color="transparent", 
                    text_color=COLOR_TEXT_MAIN, 
                    font=ctk.CTkFont(size=13, weight="normal")
                )
                
        # Build views
        if page_name == "Countdown":
            self.create_countdown_page()
        elif page_name == "Alerts":
            self.create_alerts_page()
        elif page_name == "Settings":
            self.create_settings_page()
        elif page_name == "Sound":
            self.create_sound_page()
        elif page_name == "General":
            self.create_general_page()
        elif page_name == "About":
            self.create_about_page()

    def clear_main_container(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()

    # -----------------------
    # Views Implementation
    # -----------------------
    
    def create_countdown_page(self):
        # 2. CENTER PANEL (MAIN DISPLAY)
        center_panel = ctk.CTkFrame(self.main_container, fg_color="transparent")
        center_panel.pack(side="left", fill="both", expand=True, padx=20, pady=20)

        main_clock_card = ctk.CTkFrame(center_panel, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        main_clock_card.pack(fill="x", pady=(0, 15))

        hdr = tk.Frame(main_clock_card, bg=COLOR_BG_CARD)
        hdr.pack(fill="x", padx=20, pady=(15, 0))
        ctk.CTkLabel(hdr, text="Next Candle Close", font=ctk.CTkFont(size=15, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")
        
        default_tf = list(self.timeframe_settings.keys())[0] if self.timeframe_settings else "5 Minutes"
        self.active_tf_pill = ctk.CTkLabel(hdr, text=f"🕒 {default_tf}", font=ctk.CTkFont(size=11), fg_color="#1c2436", text_color=COLOR_TEXT_MAIN, corner_radius=20, height=22, padx=10)
        self.active_tf_pill.pack(side="right")

        self.lbl_big_clock = ctk.CTkLabel(main_clock_card, text="00:00:00", font=ctk.CTkFont(family="Consolas", size=58, weight="bold"), text_color=COLOR_GREEN)
        self.lbl_big_clock.pack(pady=(10, 5))
        self.lbl_clock_sub = ctk.CTkLabel(main_clock_card, text="HOURS          MINUTES          SECONDS", font=ctk.CTkFont(size=9, weight="bold"), text_color=COLOR_TEXT_MUTED)
        self.lbl_clock_sub.pack(pady=(0, 15))

        sub_m = tk.Frame(main_clock_card, bg=COLOR_BG_CARD)
        sub_m.pack(fill="x", padx=20, pady=(5, 20))
        for text, color, attr in [("🗓️ Target Schedule Node", COLOR_BLUE, "lbl_target_time"), ("🕒 Current Local Time", COLOR_PURPLE, "lbl_local_time")]:
            m = ctk.CTkFrame(sub_m, fg_color="#171e2e", corner_radius=8, height=55)
            m.pack(side="left", fill="x", expand=True, padx=5)
            ctk.CTkLabel(m, text=text, font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(pady=(6, 0), padx=12, anchor="w")
            setattr(self, attr, ctk.CTkLabel(m, text="--:--:--", font=ctk.CTkFont(size=13, weight="bold"), text_color=color))
            getattr(self, attr).pack(pady=(0, 4), padx=12, anchor="w")

        # TIME INTERFACES GRID TABLE
        self.table_card = ctk.CTkFrame(center_panel, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        self.table_card.pack(fill="both", expand=True)

        thdr = tk.Frame(self.table_card, bg=COLOR_BG_CARD)
        thdr.pack(fill="x", padx=20, pady=(15, 10))
        
        ctk.CTkLabel(thdr, text="Tracked Timeframes", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        
        instruction_frame = tk.Frame(thdr, bg=COLOR_BG_CARD)
        instruction_frame.pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(instruction_frame, text="💡 Click any row below to edit its individual ", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkLabel(instruction_frame, text="Alert Configurations", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkLabel(instruction_frame, text=" on the right panel.", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")

        self.table_container = ctk.CTkScrollableFrame(self.table_card, fg_color="transparent")
        self.table_container.pack(fill="both", expand=True, padx=10, pady=5)
        self.refresh_table_ui()

        btn_row = tk.Frame(center_panel, bg=COLOR_BG_MAIN)
        btn_row.pack(fill="x", side="bottom", pady=(15, 0))
        
        self.btn_start = ctk.CTkButton(btn_row, text="▶  Start", fg_color="transparent", text_color=COLOR_GREEN, border_color=COLOR_GREEN, border_width=1.5, height=42, font=ctk.CTkFont(weight="bold"), command=self.start_tracking_engine)
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 6))
        
        self.btn_stop = ctk.CTkButton(btn_row, text="⏹  Stop", fg_color="transparent", text_color=COLOR_RED, border_color=COLOR_RED, border_width=1.5, height=42, font=ctk.CTkFont(weight="bold"), command=self.stop_tracking_engine)
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=(6, 0))
        
        if self.is_running:
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
        else:
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")

        # 3. RIGHT PANEL (ADVANCED CONTROLS)
        right_panel = ctk.CTkFrame(self.main_container, width=280, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        right_panel.pack(side="right", fill="y", padx=(0, 20), pady=20)
        right_panel.pack_propagate(False)

        ctk.CTkLabel(right_panel, text="Alert Configurations", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 15), padx=20, anchor="w")
        
        ctk.CTkLabel(right_panel, text="Select Trading Market", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(padx=20, anchor="w")
        self.opt_market = ctk.CTkOptionMenu(right_panel, values=list(MARKET_RULES.keys()), fg_color="#1c2436", button_color="#2b3752", height=35, command=self.on_market_profile_changed)
        self.opt_market.pack(fill="x", padx=20, pady=(0, 15))
        self.opt_market.set(self.selected_market)

        tf_hdr_row = tk.Frame(right_panel, bg=COLOR_BG_CARD)
        tf_hdr_row.pack(fill="x", padx=20, pady=(5, 2))
        
        ctk.CTkLabel(tf_hdr_row, text="Timeframe", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkButton(tf_hdr_row, text="+ Add Custom", width=85, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="#1e293b", hover_color="#2b3752", command=self.add_custom_interval).pack(side="right")
        
        self.opt_focus_tf = ctk.CTkOptionMenu(right_panel, values=list(self.timeframe_settings.keys()), fg_color="#1c2436", button_color="#2b3752", height=35, command=self.on_param_change)
        self.opt_focus_tf.pack(fill="x", padx=20, pady=(0, 15))
        self.opt_focus_tf.set(default_tf)

        buffer_hdr_row = tk.Frame(right_panel, bg=COLOR_BG_CARD)
        buffer_hdr_row.pack(fill="x", padx=20, pady=(5, 2))
        
        ctk.CTkLabel(buffer_hdr_row, text="Alert Me Before Close", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkButton(buffer_hdr_row, text="+ Custom", width=65, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="#1e293b", hover_color="#2b3752", command=self.add_custom_advance_time).pack(side="right")
        
        self.opt_buffer_sec = ctk.CTkOptionMenu(right_panel, values=["0 Seconds", "5 Seconds", "10 Seconds", "15 Seconds", "30 Seconds", "1 Minute", "2 Minutes", "5 Minutes"], fg_color="#1c2436", button_color="#2b3752", height=35, command=self.on_buffer_dropdown_change)
        self.opt_buffer_sec.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(right_panel, text="Active Notification Sound", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(padx=20, anchor="w", pady=(0, 4))
        self.opt_sound_cue = ctk.CTkOptionMenu(right_panel, values=list(SOUNDS.keys()), fg_color="#1c2436", button_color="#2b3752", height=35, command=self.on_sound_dropdown_change)
        self.opt_sound_cue.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkButton(right_panel, text="🔊 Test Alert Sound", font=ctk.CTkFont(size=11, weight="bold"), fg_color="#1e293b", height=30, command=self.audition_sound_cue).pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkOptionMenu(right_panel, values=["Dark Slate Pro Theme"], fg_color="#0e131f", button_color="#1c2436", height=32).pack(side="bottom", fill="x", padx=20, pady=15)
        
        # Trigger parameter display updates
        self.on_param_change(default_tf)

    def create_alerts_page(self):
        container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        hdr = tk.Frame(container, bg=COLOR_BG_MAIN)
        hdr.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(hdr, text="Alerts Log History", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkButton(hdr, text="🧹 Clear Logs", width=95, height=28, fg_color="#251214", text_color=COLOR_RED, hover_color=COLOR_RED, command=self.clear_alerts_log).pack(side="right")
        
        log_scroll = ctk.CTkScrollableFrame(container, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        log_scroll.pack(fill="both", expand=True)
        
        if not self.alerts_log:
            ctk.CTkLabel(log_scroll, text="No alert events recorded yet.", font=ctk.CTkFont(size=13), text_color=COLOR_TEXT_MUTED).pack(pady=40)
        else:
            for entry in reversed(self.alerts_log):
                row = ctk.CTkFrame(log_scroll, fg_color="#161b26", height=42, corner_radius=6)
                row.pack(fill="x", pady=3, padx=5)
                
                # Active Status Badge
                ctk.CTkLabel(row, text="● Close Triggered", text_color=COLOR_GREEN, font=ctk.CTkFont(size=11, weight="bold"), width=120, anchor="w").pack(side="left", padx=15)
                # Timestamp
                ctk.CTkLabel(row, text=entry["timestamp"], font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_BLUE, width=100, anchor="w").pack(side="left")
                # Details
                details = f"Timeframe: {entry['timeframe']}  |  Market: {entry['market']}  |  Sound: {entry['sound']}"
                ctk.CTkLabel(row, text=details, font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MAIN, anchor="w").pack(side="left", fill="x", expand=True)

    def clear_alerts_log(self):
        self.alerts_log.clear()
        self.show_page("Alerts")

    def create_settings_page(self):
        container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(container, text="Market Sessions & Configurations", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(0, 15))
        
        # Grid layout
        body_frame = tk.Frame(container, bg=COLOR_BG_MAIN)
        body_frame.pack(fill="both", expand=True)
        
        # Left Panel - Session Architect
        left_card = ctk.CTkFrame(body_frame, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(left_card, text="Trading Markets Architecture", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=15, padx=20, anchor="w")
        
        # Market rules summary table
        tbl_scroll = ctk.CTkScrollableFrame(left_card, fg_color="transparent")
        tbl_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        for idx, (market_name, rules) in enumerate(MARKET_RULES.items()):
            row = ctk.CTkFrame(tbl_scroll, fg_color="#161b26" if idx % 2 == 0 else "transparent", height=40, corner_radius=6)
            row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(row, text=market_name, font=ctk.CTkFont(size=11, weight="bold"), width=180, anchor="w").pack(side="left", padx=10)
            session_str = f"Hours: {rules['open']} - {rules['close']}"
            if rules["type"] == "split":
                session_str += f" (Lunch: {rules['lunch_open']}-{rules['lunch_close']})"
            ctk.CTkLabel(row, text=session_str, font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=10)

        # Right Panel - Custom Timeframes List Manager
        right_card = ctk.CTkFrame(body_frame, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1, width=320)
        right_card.pack(side="right", fill="both", padx=(10, 0))
        right_card.pack_propagate(False)
        
        ctk.CTkLabel(right_card, text="Manage Tracking Intervals", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=15, padx=20, anchor="w")
        
        tf_scroll = ctk.CTkScrollableFrame(right_card, fg_color="transparent")
        tf_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        for tf_label, profile in self.timeframe_settings.items():
            row = ctk.CTkFrame(tf_scroll, fg_color="#161b26", height=38, corner_radius=6)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)
            
            ctk.CTkLabel(row, text=tf_label, font=ctk.CTkFont(size=11, weight="bold"), width=120, anchor="w").pack(side="left", padx=10)
            
            # Simple delete row in settings
            ctk.CTkButton(
                row, text="Delete", width=50, height=20, 
                fg_color="#251214", text_color=COLOR_RED, hover_color=COLOR_RED,
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda tf=tf_label: self.delete_timeframe(tf)
            ).pack(side="right", padx=10)
            
        btn_add = ctk.CTkButton(right_card, text="+ Add Custom Timeframe", height=32, font=ctk.CTkFont(weight="bold"), command=self.add_custom_interval)
        btn_add.pack(fill="x", padx=15, pady=15)

    def create_sound_page(self):
        container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(container, text="Audio Notification Manager", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(0, 15))
        
        # Test cues card
        test_card = ctk.CTkFrame(container, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        test_card.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(test_card, text="Audition Registered Sounds", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(15, 5), padx=20, anchor="w")
        ctk.CTkLabel(test_card, text="Select any tone and audition it using the speaker button below.", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(padx=20, anchor="w")
        
        control_row = tk.Frame(test_card, bg=COLOR_BG_CARD)
        control_row.pack(fill="x", padx=20, pady=15)
        
        self.opt_sound_test = ctk.CTkOptionMenu(control_row, values=list(SOUNDS.keys()), fg_color="#1c2436", button_color="#2b3752", height=35)
        self.opt_sound_test.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.opt_sound_test.set(list(SOUNDS.keys())[0])
        
        ctk.CTkButton(control_row, text="🔊 Play Sound", font=ctk.CTkFont(size=12, weight="bold"), width=120, height=35, command=lambda: self.play_sound_by_name(self.opt_sound_test.get())).pack(side="right")
        
        # Upload card
        upload_card = ctk.CTkFrame(container, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        upload_card.pack(fill="both", expand=True)
        
        ctk.CTkLabel(upload_card, text="Import Custom WAV Audio", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(15, 5), padx=20, anchor="w")
        ctk.CTkLabel(upload_card, text="Upload sound files in .wav format. They will automatically register in sound menus.", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(padx=20, anchor="w")
        
        btn_upload = ctk.CTkButton(upload_card, text="📂 Select & Upload Custom WAV File", height=38, font=ctk.CTkFont(weight="bold"), command=self.upload_custom_sound)
        btn_upload.pack(fill="x", padx=20, pady=15)
        
        # Scrollable list of loaded sound nodes
        snd_scroll = ctk.CTkScrollableFrame(upload_card, fg_color="transparent")
        snd_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        
        ctk.CTkLabel(snd_scroll, text="Loaded Audio Library:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", pady=(0, 5))
        
        for name, filepath in SOUNDS.items():
            row = ctk.CTkFrame(snd_scroll, fg_color="#161b26", height=36, corner_radius=6)
            row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(row, text=f"🎵  {name}", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=10)
            
            is_default = name in ["Default Beep", "Soft Chime", "Alert Bell", "Cash Register"]
            if is_default:
                ctk.CTkLabel(row, text="System Standard", font=ctk.CTkFont(size=10, slant="italic"), text_color=COLOR_TEXT_MUTED).pack(side="right", padx=15)
            else:
                ctk.CTkButton(
                    row, text="Delete", width=50, height=20, 
                    fg_color="#251214", text_color=COLOR_RED, hover_color=COLOR_RED,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    command=lambda n=name, p=filepath: self.delete_custom_sound(n, p)
                ).pack(side="right", padx=10)

    def upload_custom_sound(self):
        filepath = filedialog.askopenfilename(
            parent=self, 
            title="Upload Custom Sound", 
            filetypes=[("WAV Audio Files", "*.wav")]
        )
        if not filepath:
            return
            
        sounds_dir = os.path.abspath("sounds")
        if not os.path.exists(sounds_dir):
            os.makedirs(sounds_dir)
            
        filename = os.path.basename(filepath)
        # Normalize filename
        safe_filename = "".join([c if c.isalnum() or c in [".", "_", "-"] else "_" for c in filename])
        target_path = os.path.join(sounds_dir, safe_filename)
        
        try:
            shutil.copy(filepath, target_path)
            
            # Reload sound engine
            global SOUNDS
            SOUNDS = discover_sounds()
            
            # Refresh view
            self.show_page("Sound")
            messagebox.showinfo("Sound Manager", f"Sound '{safe_filename}' uploaded and registered successfully!")
            self.save_settings()
        except Exception as e:
            messagebox.showerror("Upload Error", f"Failed to upload sound file: {e}")

    def delete_custom_sound(self, name, filepath):
        confirm = messagebox.askyesno(
            "Delete Sound", 
            f"Are you sure you want to delete the custom sound '{name}'?",
            parent=self
        )
        if not confirm:
            return
            
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            
            # Reload sound engine
            global SOUNDS
            SOUNDS = discover_sounds()
            
            # Fallback if timeframe was using deleted sound
            for tf_label, profile in self.timeframe_settings.items():
                if profile["sound"] == name:
                    profile["sound"] = "Default Beep"
            
            self.show_page("Sound")
            self.save_settings()
        except Exception as e:
            messagebox.showerror("Delete Error", f"Failed to delete sound file: {e}")

    def create_general_page(self):
        container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(container, text="System Preferences", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(0, 15))
        
        pref_card = ctk.CTkFrame(container, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        pref_card.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(pref_card, text="General Engine Workstation Settings", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(15, 5), padx=20, anchor="w")
        ctk.CTkLabel(pref_card, text="Select preferences for alert channels and application shutdown rules.", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(padx=20, anchor="w")
        
        box_frame = tk.Frame(pref_card, bg=COLOR_BG_CARD)
        box_frame.pack(fill="x", padx=20, pady=20)
        
        self.chk_audio_play = ctk.CTkCheckBox(box_frame, text="Enable Audio Alerts (Speaker Alarms)", font=ctk.CTkFont(size=12), checkbox_width=18, checkbox_height=18, command=self.save_preference)
        self.chk_audio_play.pack(fill="x", pady=6)
        if self.loaded_config.get("enable_audio_alerts", True):
            self.chk_audio_play.select()
        else:
            self.chk_audio_play.deselect()

        self.chk_notify = ctk.CTkCheckBox(box_frame, text="Show System Notifications (Toast Banners)", font=ctk.CTkFont(size=12), checkbox_width=18, checkbox_height=18, command=self.save_preference)
        self.chk_notify.pack(fill="x", pady=6)
        if self.loaded_config.get("show_system_notifications", True):
            self.chk_notify.select()
        else:
            self.chk_notify.deselect()

        self.chk_minimize = ctk.CTkCheckBox(box_frame, text="Close Minimizes to Windows System Tray", font=ctk.CTkFont(size=12), checkbox_width=18, checkbox_height=18, command=self.save_preference)
        self.chk_minimize.pack(fill="x", pady=6)
        if self.loaded_config.get("close_minimizes_to_tray", True):
            self.chk_minimize.select()
        else:
            self.chk_minimize.deselect()

        # Divider
        tk.Frame(box_frame, bg="#1e2538", height=1).pack(fill="x", pady=12)

        ctk.CTkLabel(box_frame, text="STARTUP", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", pady=(0, 4))

        self.chk_startup = ctk.CTkCheckBox(box_frame, text="Launch CandleAlert on Windows Startup", font=ctk.CTkFont(size=12), checkbox_width=18, checkbox_height=18, command=self.save_preference)
        self.chk_startup.pack(fill="x", pady=6)
        # Read live state directly from registry, not from settings.json
        if is_startup_enabled():
            self.chk_startup.select()
        else:
            self.chk_startup.deselect()
        ctk.CTkLabel(box_frame, text="Registers CandleAlert in Windows Registry (HKCU\\...\\Run). No admin rights required.", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=24)

    def save_preference(self):
        # Update config dictionary directly
        self.loaded_config["enable_audio_alerts"] = self.chk_audio_play.get() == 1
        self.loaded_config["show_system_notifications"] = self.chk_notify.get() == 1
        self.loaded_config["close_minimizes_to_tray"] = self.chk_minimize.get() == 1
        # Apply startup registry change immediately
        if hasattr(self, "chk_startup"):
            set_startup_enabled(self.chk_startup.get() == 1)
        self.save_settings()

    def create_about_page(self):
        container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        about_card = ctk.CTkFrame(container, fg_color=COLOR_BG_CARD, corner_radius=12, border_color="#1e2538", border_width=1)
        about_card.pack(fill="both", expand=True)
        
        logo_lbl = ctk.CTkLabel(about_card, text="🔔", font=ctk.CTkFont(size=52))
        logo_lbl.pack(pady=(40, 5))
        
        ctk.CTkLabel(about_card, text="CandleAlert Pro Workstation", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=5)
        ctk.CTkLabel(about_card, text="Version 1.0.0 (Workstation Release)", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MUTED).pack(pady=(0, 20))
        
        desc_text = (
            "Never miss a candle close again. CandleAlert is a dedicated utility designed "
            "for active financial traders. By tracking target session profiles and providing "
            "precise buffer-time alert calls, the software ensures confirmations are made "
            "exactly at the candle close border."
        )
        ctk.CTkLabel(about_card, text=desc_text, font=ctk.CTkFont(size=13), text_color=COLOR_TEXT_MAIN, wraplength=520, justify="center").pack(pady=10)
        
        tech_text = "Built using Python, CustomTkinter, pystray System Tray API, and winsound Engine."
        ctk.CTkLabel(about_card, text=tech_text, font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(pady=(20, 10))
        
        ctk.CTkLabel(about_card, text="© 2026 CandleAlert Workstation. All rights reserved.", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="bottom", pady=25)

    # -----------------------
    # Back-end Calculations
    # -----------------------
    
    def check_and_trigger_alerts(self, now):
        if not self.is_running:
            return
            
        market_open = self.is_market_open_now(self.selected_market, now)
        if not market_open:
            return
            
        for label, profile in list(self.timeframe_settings.items()):
            is_enabled = profile.get("enabled", True)
            if not is_enabled:
                continue
                
            row_schedule = self.generate_market_schedule(self.selected_market, profile["mins"])
            node_target = None
            for slot in row_schedule:
                if slot > now:
                    node_target = slot
                    break
                    
            if node_target:
                d = int((node_target - now).total_seconds())
                buf_seconds = self.parse_buffer_to_seconds(profile["buffer"])
                
                if d == buf_seconds:
                    if not self.slot_triggers.get(label, False):
                        # Play sound and notification
                        if self.loaded_config.get("enable_audio_alerts", True): 
                            self.play_sound_by_name(profile["sound"])
                        if self.loaded_config.get("show_system_notifications", True):
                            self.show_toast_notification(label)
                        
                        # Add to alerts log
                        log_entry = {
                            "timestamp": now.strftime("%I:%M:%S %p"),
                            "market": self.selected_market,
                            "timeframe": label,
                            "sound": profile["sound"]
                        }
                        self.alerts_log.append(log_entry)
                        
                        # Keep max 50 log items
                        if len(self.alerts_log) > 50:
                            self.alerts_log.pop(0)
                            
                        # If active on Alerts page, auto refresh log list
                        if self.current_page == "Alerts":
                            self.show_page("Alerts")
                            
                        self.slot_triggers[label] = True
                else:
                    self.slot_triggers[label] = False

    def update_live_dashboard_loop(self):
        now = datetime.now()
        
        # 1. Run alarm checks in background regardless of active page
        self.check_and_trigger_alerts(now)
        
        # 2. Update UI if on the Countdown page
        if self.current_page == "Countdown":
            focus_tf = self.opt_focus_tf.get()
            market_open = self.is_market_open_now(self.selected_market, now)
            
            if focus_tf in self.timeframe_settings:
                active_node = None
                if market_open:
                    schedule = self.generate_market_schedule(self.selected_market, self.timeframe_settings[focus_tf]["mins"])
                    for slot in schedule:
                        if slot > now:
                            active_node = slot
                            break
                
                if active_node:
                    diff = int((active_node - now).total_seconds())
                    self.lbl_big_clock.configure(text=f"{diff//3600:02}:{(diff%3600)//60:02}:{diff%60:02}", text_color=COLOR_GREEN)
                    self.lbl_clock_sub.configure(text="HOURS          MINUTES          SECONDS", text_color=COLOR_TEXT_MUTED)
                    
                    if active_node.date() == now.date():
                        self.lbl_target_time.configure(text=active_node.strftime("%I:%M:%S %p"))
                    else:
                        self.lbl_target_time.configure(text=active_node.strftime("%a %I:%M:%S %p"))
                else:
                    self.lbl_big_clock.configure(text="CLOSED", text_color=COLOR_RED)
                    self.lbl_clock_sub.configure(text="MARKET ACTIVE HOURS CONCLUDED", text_color=COLOR_RED)
                    self.lbl_target_time.configure(text="--:--:--")
            
            self.lbl_local_time.configure(text=now.strftime("%I:%M:%S %p"))

            for label, profile in list(self.timeframe_settings.items()):
                is_enabled = profile.get("enabled", True)
                
                node_target = None
                if market_open:
                    row_schedule = self.generate_market_schedule(self.selected_market, profile["mins"])
                    for slot in row_schedule:
                        if slot > now:
                            node_target = slot
                            break
                
                if label in self.table_rows:
                    row_data = self.table_rows[label]
                    
                    if node_target:
                        d = int((node_target - now).total_seconds())
                        
                        if node_target.date() == now.date():
                            row_data["close"].configure(text=node_target.strftime("%I:%M:%S %p"))
                        else:
                            row_data["close"].configure(text=node_target.strftime("%a %I:%M %p"))
                            
                        row_data["countdown"].configure(text=f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}")
                        
                        if label == focus_tf and is_enabled:
                            row_data["name_lbl"].configure(text=f"●  {label} (Active)", text_color=COLOR_GREEN)
                            row_data["frame"].configure(fg_color=COLOR_ROW_SELECTED)
                            row_data["actions_frame"].configure(bg=COLOR_ROW_SELECTED)
                        elif not is_enabled:
                            row_data["name_lbl"].configure(text=f"●  {label} (Muted)", text_color=COLOR_TEXT_MUTED)
                            row_data["frame"].configure(fg_color=row_data["base_bg"])
                            row_data["actions_frame"].configure(bg=row_data["actions_base_bg"])
                        else:
                            row_data["name_lbl"].configure(text=f"●  {label}", text_color=COLOR_TEXT_MAIN)
                            row_data["frame"].configure(fg_color=row_data["base_bg"])
                            row_data["actions_frame"].configure(bg=row_data["actions_base_bg"])
                    else:
                        row_data["close"].configure(text="Closed")
                        row_data["countdown"].configure(text="--:--:--")
                        row_data["name_lbl"].configure(text=f"●  {label}", text_color=COLOR_TEXT_MUTED)
                        row_data["frame"].configure(fg_color=row_data["base_bg"])
                        row_data["actions_frame"].configure(bg=row_data["actions_base_bg"])

        self.after(200, self.update_live_dashboard_loop)

    def is_market_open_now(self, market_name, now):
        rules = MARKET_RULES[market_name]
        
        # 1. Check weekend
        if rules["type"] in ["equities", "split", "forex"]:
            if now.weekday() in [5, 6]:
                return False
                
        # 2. Check time range
        if rules["type"] == "continuous" or rules["type"] == "forex":
            return True
            
        current_time = now.time()
        open_h, open_m = map(int, rules["open"].split(":"))
        close_h, close_m = map(int, rules["close"].split(":"))
        market_open = time(open_h, open_m)
        market_close = time(close_h, close_m)
        
        if rules["type"] == "equities":
            return market_open <= current_time <= market_close
            
        if rules["type"] == "split":
            l_open_h, l_open_m = map(int, rules["lunch_open"].split(":"))
            l_close_h, l_close_m = map(int, rules["lunch_close"].split(":"))
            lunch_open = time(l_open_h, l_open_m)
            lunch_close = time(l_close_h, l_close_m)
            return (market_open <= current_time <= lunch_open) or (lunch_close <= current_time <= market_close)
            
        return False

    def is_trading_day(self, market_type, target_date):
        # Weekday 5 = Saturday, 6 = Sunday
        if market_type in ["equities", "split", "forex"]:
            if target_date.weekday() in [5, 6]:
                return False
        return True

    def generate_market_schedule(self, market_name, interval_mins):
        now = datetime.now()
        target_date = now.date()
        rules = MARKET_RULES[market_name]
        
        for _ in range(10):
            if not self.is_trading_day(rules["type"], target_date):
                target_date += timedelta(days=1)
                continue
            
            slots = []
            if rules["type"] == "continuous" or rules["type"] == "forex":
                start_dt = datetime.combine(target_date, datetime.min.time())
                for m in range(0, 1440, interval_mins):
                    slots.append(start_dt + timedelta(minutes=m + interval_mins))
            else:
                open_h, open_m = map(int, rules["open"].split(":"))
                close_h, close_m = map(int, rules["close"].split(":"))
                market_open = datetime.combine(target_date, time(open_h, open_m))
                market_close = datetime.combine(target_date, time(close_h, close_m))
                
                def build_segment(start_dt, end_dt):
                    if interval_mins == 1440:
                        return [end_dt]
                    segment_slots = []
                    curr = start_dt
                    while True:
                        next_slot = curr + timedelta(minutes=interval_mins)
                        if next_slot >= end_dt:
                            if end_dt not in segment_slots and end_dt > curr:
                                segment_slots.append(end_dt)
                            break
                        segment_slots.append(next_slot)
                        curr = next_slot
                    return segment_slots

                if rules["type"] == "equities":
                    slots = build_segment(market_open, market_close)
                elif rules["type"] == "split":
                    l_open_h, l_open_m = map(int, rules["lunch_open"].split(":"))
                    l_close_h, l_close_m = map(int, rules["lunch_close"].split(":"))
                    lunch_open = datetime.combine(target_date, time(l_open_h, l_open_m))
                    lunch_close = datetime.combine(target_date, time(l_close_h, l_close_m))
                    
                    if interval_mins == 1440:
                        slots = [market_close]
                    else:
                        slots = build_segment(market_open, lunch_open) + build_segment(lunch_close, market_close)
            
            future_slots = [s for s in slots if s > now]
            if future_slots:
                return slots
            
            target_date += timedelta(days=1)
            
        return []

    def on_market_profile_changed(self, choice):
        self.selected_market = choice
        self.refresh_table_ui()
        self.save_settings()

    def refresh_table_ui(self):
        for widget in self.table_container.winfo_children():
            widget.destroy()
        
        self.table_rows = {}
        colors = [COLOR_GREEN, COLOR_BLUE, COLOR_PURPLE, "#f97316"]
        
        for i, (tf_label, profile) in enumerate(self.timeframe_settings.items()):
            is_enabled = profile.get("enabled", True)
            row_bg = "#161b26" if i % 2 == 0 else "transparent"
            actions_bg = "#161b26" if i % 2 == 0 else COLOR_BG_CARD
            
            r = ctk.CTkFrame(self.table_container, fg_color=row_bg, height=38, corner_radius=6)
            r.pack(fill="x", pady=2)
            r.pack_propagate(False)
            
            name_color = COLOR_TEXT_MAIN if is_enabled else COLOR_TEXT_MUTED
        
            name_lbl = ctk.CTkLabel(r, text=f"●  {tf_label}", font=ctk.CTkFont(size=12, weight="bold"), text_color=name_color, width=120, anchor="w")
            name_lbl.pack(side="left", padx=15)
            
            c_lbl = ctk.CTkLabel(r, text="--:--:--", font=ctk.CTkFont(size=12), text_color=name_color, width=95, anchor="w")
            c_lbl.pack(side="left")
            
            t_lbl = ctk.CTkLabel(r, text="00:00:00", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color=colors[i % 4] if is_enabled else COLOR_TEXT_MUTED, width=85, anchor="w")
            t_lbl.pack(side="left")
            
            actions_frame = tk.Frame(r, bg=actions_bg)
            actions_frame.pack(side="right", padx=10)
            
            toggle_txt = "Disable" if is_enabled else "Enable"
            toggle_color = "#1e293b" if is_enabled else "#157347"
            toggle_btn = ctk.CTkButton(
                actions_frame, text=toggle_txt, width=54, height=22, 
                font=ctk.CTkFont(size=11, weight="bold"), fg_color=toggle_color, 
                hover_color="#ef4444" if is_enabled else "#1e7e34",
                command=lambda tf=tf_label: self.toggle_timeframe_status(tf)
            )
            toggle_btn.pack(side="left", padx=2)
            
            del_btn = ctk.CTkButton(
                actions_frame, text="Delete", width=54, height=22, 
                font=ctk.CTkFont(size=11, weight="bold"), fg_color="#251214", 
                text_color=COLOR_RED, hover_color=COLOR_RED,
                command=lambda tf=tf_label: self.delete_timeframe(tf)
            )
            del_btn.pack(side="left", padx=2)
            
            self.table_rows[tf_label] = {
                "close": c_lbl, 
                "countdown": t_lbl, 
                "name_lbl": name_lbl, 
                "frame": r, 
                "actions_frame": actions_frame,
                "base_bg": row_bg,
                "actions_base_bg": actions_bg
            }
            if tf_label not in self.slot_triggers:
                self.slot_triggers[tf_label] = False

            for w in (name_lbl, c_lbl, t_lbl, r):
                w.bind("<Button-1>", lambda event, tf=tf_label: self.select_focus_timeframe(tf))
                w.configure(cursor="hand2")

    def toggle_timeframe_status(self, tf_label):
        if tf_label in self.timeframe_settings:
            self.timeframe_settings[tf_label]["enabled"] = not self.timeframe_settings[tf_label]["enabled"]
            self.refresh_table_ui()
            self.save_settings()

    def delete_timeframe(self, tf_label):
        if len(self.timeframe_settings) <= 1:
            messagebox.showwarning("Engine Alert", "Workstation requires at least one tracking row.")
            return
        
        if tf_label in self.timeframe_settings:
            del self.timeframe_settings[tf_label]
            if tf_label in self.slot_triggers: 
                del self.slot_triggers[tf_label]
            if self.opt_focus_tf.get() == tf_label:
                fallback_tf = list(self.timeframe_settings.keys())[0]
                self.opt_focus_tf.set(fallback_tf)
                self.on_param_change(fallback_tf)
            self.opt_focus_tf.configure(values=list(self.timeframe_settings.keys()))
            self.refresh_table_ui()
            self.save_settings()

    def add_custom_advance_time(self):
        sec = simpledialog.askinteger("Custom Buffer", "Enter alert buffer seconds:", parent=self, minvalue=0, maxvalue=3600)
        if sec is not None:
            label = f"{sec // 60} Minute" if sec % 60 == 0 else f"{sec} Seconds"
            curr_vals = list(self.opt_buffer_sec.cget("values"))
            if label not in curr_vals:
                curr_vals.append(label)
                self.opt_buffer_sec.configure(values=curr_vals)
            self.opt_buffer_sec.set(label)
            self.on_buffer_dropdown_change(label)

    def parse_buffer_to_seconds(self, buffer_str):
        try:
            parts = buffer_str.split()
            val = int(parts[0])
            return val * 60 if "minute" in parts[1].lower() else val
        except (ValueError, IndexError): 
            return 0

    def select_focus_timeframe(self, tf_label):
        if self.current_page == "Countdown":
            self.opt_focus_tf.set(tf_label)
            self.on_param_change(tf_label)

    def add_custom_interval(self):
        m = simpledialog.askinteger("Add Timeframe", "Enter interval length in minutes:", parent=self, minvalue=1, maxvalue=1440)
        if m:
            label = f"{m} Minutes" if m < 60 else ( "1 Hour" if m == 60 else f"{m//60} Hours" )
            self.timeframe_settings[label] = {"mins": m, "buffer": "10 Seconds", "sound": "Cash Register", "enabled": True}
            if self.current_page == "Countdown":
                self.opt_focus_tf.configure(values=list(self.timeframe_settings.keys()))
            self.refresh_table_ui()
            self.save_settings()

    def on_param_change(self, choice):
        if self.current_page == "Countdown" and hasattr(self, 'active_tf_pill'):
            self.active_tf_pill.configure(text=f"🕒 {choice}")
            if choice in self.timeframe_settings:
                target_buffer = self.timeframe_settings[choice]["buffer"]
                curr_vals = list(self.opt_buffer_sec.cget("values"))
                if target_buffer not in curr_vals:
                    curr_vals.append(target_buffer)
                    self.opt_buffer_sec.configure(values=curr_vals)
                self.opt_buffer_sec.set(target_buffer)
                self.opt_sound_cue.set(self.timeframe_settings[choice]["sound"])

    def on_buffer_dropdown_change(self, choice):
        focus_tf = self.opt_focus_tf.get()
        if focus_tf in self.timeframe_settings: 
            self.timeframe_settings[focus_tf]["buffer"] = choice
            self.save_settings()

    def on_sound_dropdown_change(self, choice):
        focus_tf = self.opt_focus_tf.get()
        if focus_tf in self.timeframe_settings: 
            self.timeframe_settings[focus_tf]["sound"] = choice
            self.save_settings()

    def play_sound_by_name(self, sound_name):
        s = SOUNDS.get(sound_name, "")
        if os.path.exists(s) and winsound:
            threading.Thread(target=winsound.PlaySound, args=(s, winsound.SND_FILENAME | winsound.SND_ASYNC), daemon=True).start()

    def audition_sound_cue(self):
        self.play_sound_by_name(self.opt_sound_cue.get())

    def start_tracking_engine(self):
        self.is_running = True
        self.status_text.configure(text="RUNNING", text_color=COLOR_GREEN)
        self.status_dot.configure(text_color=COLOR_GREEN)
        self.status_card.configure(fg_color="#092613")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

    def stop_tracking_engine(self):
        self.is_running = False
        self.status_text.configure(text="IDLE", text_color=COLOR_TEXT_MUTED)
        self.status_dot.configure(text_color=COLOR_TEXT_MUTED)
        self.status_card.configure(fg_color="#0e131f")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def show_toast_notification(self, label):
        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)
        toast.geometry("280x65+40+40")
        toast.configure(fg_color=COLOR_BG_CARD, border_color=COLOR_GREEN, border_width=1)
        toast.attributes("-topmost", True)
        lbl = ctk.CTkLabel(toast, text=f"⚠️ {label} Close Imminent!", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_GREEN)
        lbl.pack(expand=True, fill="both", padx=10, pady=10)
        toast.after(2500, toast.destroy)

    def handle_close_window(self):
        if self.loaded_config.get("close_minimizes_to_tray", True): 
            self.minimize_to_tray()
        else: 
            self.exit_app()

    def create_tray_icon(self):
        icon_path = resource_path("app_icon.png")
        img = Image.open(icon_path) if os.path.exists(icon_path) else Image.new('RGB', (64, 64), color=(12, 15, 22))
        self.tray_icon = pystray.Icon("CandleAlert", img, "CandleAlert Pro", (item('Show Workstation', self.restore_from_tray), item('Exit Engine', self.exit_app)))
        self.tray_icon.run()

    def minimize_to_tray(self):
        self.withdraw()
        threading.Thread(target=self.create_tray_icon, daemon=True).start()

    def restore_from_tray(self):
        if self.tray_icon: 
            self.tray_icon.stop()
        self.deiconify()

    def exit_app(self):
        if self.tray_icon: 
            self.tray_icon.stop()
        self.quit()

if __name__ == "__main__":
    app = AdvancedCandleAlertApp()
    app.mainloop()