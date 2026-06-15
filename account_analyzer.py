#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPlace 账号分析器 - 分析多个账号的日期和作画区块重合度
支持自定义日期间隔筛选，具备完整 GUI 界面
"""

import os
import json
import csv
import re
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.error import URLError
from tkinter import Tk, Toplevel, Frame, Label, Button, Entry, Text, Scrollbar
from tkinter import ttk, messagebox, filedialog
from tkinter import BOTH, LEFT, RIGHT, TOP, BOTTOM, X, Y, END, NSEW, NS, EW, W, E
from tkinter.font import Font


class AccountAnalyzer:
    """WPlace 账号重合度分析器"""

    # 远程服务器地址
    REMOTE_BASE = "https://wplace-analytics.linalg.tech"

    def __init__(self, root: Tk):
        self.root = root
        self.root.title("WPlace 账号重合度分析器")
        self.root.geometry("1280x820")
        self.root.minsize(1000, 650)

        # ---- 模式 ----
        self.mode: str = "local"        # "local" 或 "remote"
        self._cancel_event = threading.Event()  # 取消当前加载线程的标志
        self._loading_lock = threading.Lock()    # 防止并发加载

        # ---- 数据存储 ----
        self.all_data: dict[str, dict] = {}          # {date_str: {player_id: {...}}}
        self.available_dates: list[str] = []          # 排序后的日期列表
        self.available_ids: set[str] = set()          # 所有出现过的 player ID
        self.id_to_name: dict[str, str] = {}          # ID -> name 映射
        self.name_to_ids: dict[str, list[str]] = {}   # name -> [ID, ...] (可能同名)

        # ---- 样式 ----
        self._setup_styles()
        self._build_ui()
        self._auto_load_data()

    # ------------------------------------------------------------------
    # 样式
    # ------------------------------------------------------------------
    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("Title.TLabel", font=("Microsoft YaHei", 13, "bold"))
        style.configure("Section.TLabel", font=("Microsoft YaHei", 10, "bold"))
        style.configure("Info.TLabel", foreground="#666")
        style.configure("Accent.TButton", font=("Microsoft YaHei", 9, "bold"))

        # Treeview 样式
        style.configure("Treeview", rowheight=26, font=("Microsoft YaHei", 9))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 9, "bold"))

        self.root.option_add("*Font", ("Microsoft YaHei", 9))

    # ------------------------------------------------------------------
    # UI 搭建
    # ------------------------------------------------------------------
    def _build_ui(self):
        # ---- 顶部：标题与数据加载 ----
        top_bar = Frame(self.root, bg="#f0f0f0", height=44)
        top_bar.pack(fill=X, padx=0, pady=0)
        top_bar.pack_propagate(False)

        Label(top_bar, text="🔍 WPlace 账号重合度分析器", font=("Microsoft YaHei", 14, "bold"),
              bg="#f0f0f0", fg="#333").pack(side=LEFT, padx=14, pady=8)

        self.lbl_status = Label(top_bar, text="正在加载数据...", font=("Microsoft YaHei", 9),
                                bg="#f0f0f0", fg="#888")
        self.lbl_status.pack(side=RIGHT, padx=14, pady=8)

        self.btn_mode = Button(top_bar, text="🌐 网络模式", command=self._toggle_mode,
                               bg="#9C27B0", fg="white", borderwidth=0, padx=12, pady=3,
                               cursor="hand2", font=("Microsoft YaHei", 9))
        self.btn_mode.pack(side=RIGHT, padx=6, pady=8)

        btn_reload = Button(top_bar, text="🔄 重新加载数据", command=self._auto_load_data,
                            bg="#2196F3", fg="white", borderwidth=0, padx=12, pady=3,
                            cursor="hand2", font=("Microsoft YaHei", 9))
        btn_reload.pack(side=RIGHT, padx=6, pady=8)

        # ---- 主内容区域（左右分栏） ----
        main_paned = ttk.PanedWindow(self.root, orient="horizontal")
        main_paned.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        # -- 左侧控制面板 --
        left_frame = Frame(main_paned, width=420)
        main_paned.add(left_frame, weight=0)

        self._build_left_panel(left_frame)

        # -- 右侧结果面板 --
        right_frame = Frame(main_paned)
        main_paned.add(right_frame, weight=1)

        self._build_right_panel(right_frame)

    # ------------------------------------------------------------------
    # 左侧面板
    # ------------------------------------------------------------------
    def _build_left_panel(self, parent: Frame):
        # 日期筛选
        date_frame = ttk.LabelFrame(parent, text="📅 日期范围筛选", padding=10)
        date_frame.pack(fill=X, padx=4, pady=(6, 4))

        row1 = Frame(date_frame)
        row1.pack(fill=X, pady=2)
        Label(row1, text="起始日期:").pack(side=LEFT)
        self.entry_start = Entry(row1, width=12)
        self.entry_start.pack(side=LEFT, padx=(6, 12))
        Label(row1, text="结束日期:").pack(side=LEFT)
        self.entry_end = Entry(row1, width=12)
        self.entry_end.pack(side=LEFT, padx=(6, 12))

        Label(date_frame, text="留空则使用全部数据范围；格式: YYYY-MM-DD 或 YYYYMMDD",
              foreground="#888", font=("Microsoft YaHei", 8)).pack(anchor=W, pady=(4, 2))

        btn_date = Button(date_frame, text="📆 应用日期筛选", command=self._on_analyze,
                          bg="#4CAF50", fg="white", borderwidth=0, padx=14, pady=4,
                          cursor="hand2")
        btn_date.pack(pady=(6, 2))

        # 快速日期选择按钮
        quick_frame = Frame(date_frame)
        quick_frame.pack(fill=X, pady=(2, 0))
        for label_text, days in [("近7天", 7), ("近30天", 30), ("近90天", 90), ("全部", 0)]:
            btn = Button(quick_frame, text=label_text,
                         command=lambda d=days: self._quick_date(d),
                         bg="#e0e0e0", borderwidth=0, padx=8, pady=2,
                         cursor="hand2", font=("Microsoft YaHei", 8))
            btn.pack(side=LEFT, padx=2)

        # 账号输入
        acc_frame = ttk.LabelFrame(parent, text="👤 账号输入（每行一个 ID 或名称）", padding=10)
        acc_frame.pack(fill=BOTH, expand=True, padx=4, pady=(4, 4))

        self.text_accounts = Text(acc_frame, height=8, width=46, wrap="none",
                                   font=("Consolas", 10))
        self.text_accounts.pack(fill=BOTH, expand=True)

        # 搜索提示
        search_frame = Frame(acc_frame)
        search_frame.pack(fill=X, pady=(6, 0))
        Label(search_frame, text="快速查找ID/名称:").pack(side=LEFT)
        self.entry_search = Entry(search_frame, width=18)
        self.entry_search.pack(side=LEFT, padx=(6, 6))
        self.entry_search.bind("<KeyRelease>", self._on_search_key)
        Button(search_frame, text="🔍", command=self._search_account,
               bg="#2196F3", fg="white", borderwidth=0, padx=8, cursor="hand2").pack(side=LEFT)

        # 搜索建议列表
        self.listbox_suggestions = ttk.Treeview(acc_frame, height=4, columns=("id", "name"),
                                                 show="headings")
        self.listbox_suggestions.heading("id", text="ID")
        self.listbox_suggestions.heading("name", text="名称")
        self.listbox_suggestions.column("id", width=100)
        self.listbox_suggestions.column("name", width=250)
        self.listbox_suggestions.pack(fill=X, pady=(4, 0))
        self.listbox_suggestions.bind("<Double-1>", self._add_suggestion)

        # 操作按钮
        btn_frame = Frame(acc_frame)
        btn_frame.pack(fill=X, pady=(8, 0))

        Button(btn_frame, text="🔬 开始分析", command=self._on_analyze,
               bg="#FF5722", fg="white", borderwidth=0, padx=16, pady=4,
               cursor="hand2", font=("Microsoft YaHei", 10, "bold")).pack(side=LEFT, padx=(0, 8))

        Button(btn_frame, text="🗑 清空输入", command=lambda: self.text_accounts.delete("1.0", END),
               bg="#9E9E9E", fg="white", borderwidth=0, padx=12, pady=4,
               cursor="hand2").pack(side=LEFT)

        Button(btn_frame, text="📋 复制结果", command=self._copy_results,
               bg="#607D8B", fg="white", borderwidth=0, padx=12, pady=4,
               cursor="hand2").pack(side=RIGHT)

        Button(btn_frame, text="💾 导出CSV", command=self._export_csv,
               bg="#009688", fg="white", borderwidth=0, padx=12, pady=4,
               cursor="hand2").pack(side=RIGHT, padx=(0, 6))

    # ------------------------------------------------------------------
    # 右侧面板
    # ------------------------------------------------------------------
    def _build_right_panel(self, parent: Frame):
        # 使用 Notebook 分页
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=BOTH, expand=True)

        # ---- Tab 1: 日期重合 ----
        tab_date = Frame(self.notebook)
        self.notebook.add(tab_date, text="📅 日期重合")

        self.tree_date = ttk.Treeview(tab_date, columns=("accounts", "common_dates_count",
                                       "total_dates_pair", "overlap_rate", "common_dates"),
                                       show="headings", selectmode="extended")
        self.tree_date.heading("accounts", text="账号对")
        self.tree_date.heading("common_dates_count", text="共同活跃天数")
        self.tree_date.heading("total_dates_pair", text="两人总活跃天数")
        self.tree_date.heading("overlap_rate", text="日期重合率")
        self.tree_date.heading("common_dates", text="共同日期列表")
        self.tree_date.column("accounts", width=180)
        self.tree_date.column("common_dates_count", width=100, anchor="center")
        self.tree_date.column("total_dates_pair", width=110, anchor="center")
        self.tree_date.column("overlap_rate", width=90, anchor="center")
        self.tree_date.column("common_dates", width=400)

        scroll_y = Scrollbar(tab_date, orient="vertical", command=self.tree_date.yview)
        self.tree_date.configure(yscrollcommand=scroll_y.set)
        self.tree_date.pack(side=LEFT, fill=BOTH, expand=True)
        scroll_y.pack(side=RIGHT, fill=Y)

        # ---- Tab 2: 区块重合 ----
        tab_region = Frame(self.notebook)
        self.notebook.add(tab_region, text="🎨 作画区块重合")

        self.tree_region = ttk.Treeview(tab_region, columns=("accounts", "common_regions",
                                          "total_regions_pair", "overlap_rate"),
                                         show="headings", selectmode="extended")
        self.tree_region.heading("accounts", text="账号对")
        self.tree_region.heading("common_regions", text="共同区块数")
        self.tree_region.heading("total_regions_pair", text="两人总区块数")
        self.tree_region.heading("overlap_rate", text="区块重合率")
        self.tree_region.column("accounts", width=200)
        self.tree_region.column("common_regions", width=100, anchor="center")
        self.tree_region.column("total_regions_pair", width=110, anchor="center")
        self.tree_region.column("overlap_rate", width=100, anchor="center")

        scroll_y2 = Scrollbar(tab_region, orient="vertical", command=self.tree_region.yview)
        self.tree_region.configure(yscrollcommand=scroll_y2.set)
        self.tree_region.pack(side=LEFT, fill=BOTH, expand=True)
        scroll_y2.pack(side=RIGHT, fill=Y)

        # 双击查看详细区块列表
        self.tree_region.bind("<Double-1>", self._show_region_detail)

        # ---- Tab 3: 综合摘要 ----
        tab_summary = Frame(self.notebook)
        self.notebook.add(tab_summary, text="📊 综合摘要")

        self.text_summary = Text(tab_summary, wrap="word", font=("Consolas", 10),
                                  bg="#fafafa", borderwidth=0)
        self.text_summary.pack(fill=BOTH, expand=True, padx=4, pady=4)

        # ---- Tab 4: 原始数据 ----
        tab_raw = Frame(self.notebook)
        self.notebook.add(tab_raw, text="📋 账号活动概览")

        self.tree_raw = ttk.Treeview(tab_raw, columns=("account", "active_dates",
                                      "total_pixels", "total_regions", "avg_pixels_per_day"),
                                      show="headings", selectmode="extended")
        self.tree_raw.heading("account", text="账号 (ID / 名称)")
        self.tree_raw.heading("active_dates", text="活跃天数")
        self.tree_raw.heading("total_pixels", text="总像素数")
        self.tree_raw.heading("total_regions", text="涉及区块数")
        self.tree_raw.heading("avg_pixels_per_day", text="日均像素")
        self.tree_raw.column("account", width=200)
        self.tree_raw.column("active_dates", width=80, anchor="center")
        self.tree_raw.column("total_pixels", width=100, anchor="center")
        self.tree_raw.column("total_regions", width=90, anchor="center")
        self.tree_raw.column("avg_pixels_per_day", width=90, anchor="center")

        scroll_y3 = Scrollbar(tab_raw, orient="vertical", command=self.tree_raw.yview)
        self.tree_raw.configure(yscrollcommand=scroll_y3.set)
        self.tree_raw.pack(side=LEFT, fill=BOTH, expand=True)
        scroll_y3.pack(side=RIGHT, fill=Y)

        # ---- Tab 5: 软件信息 ----
        tab_info = Frame(self.notebook)
        self.notebook.add(tab_info, text="ℹ️ 软件信息")

        self.text_info = Text(tab_info, wrap="word", font=("Microsoft YaHei", 10),
                               bg="#fafafa", borderwidth=0, padx=10, pady=10)
        self.text_info.pack(fill=BOTH, expand=True)

        # 组装软件信息内容
        info_text = (
            "=" * 62 + "\n"
            "  WPlace 账号重合度分析器\n"
            "📦 数据来源\n"
            "  GitHub 仓库: https://github.com/lin-alg/Wplace_Analytics\n"
            "  在线部署:   https://wplace-analytics.linalg.tech/\n\n"
            "💻 本地模式使用说明\n"
            "  1. 克隆仓库到本地:\n"
            '     git clone https://github.com/lin-alg/Wplace_Analytics.git\n'
            "  2. 将仓库内容放置在程序根目录下\n"
            "  3. data/ 目录中需包含 wplace_players_today_*.json 文件\n"
            "  4. 启动程序后默认为本地模式，自动加载 data/ 下的数据\n\n"
            "🌐 网络模式说明\n"
            "  直接从 wplace-analytics.linalg.tech 拉取数据到内存\n"
            "  关闭程序后数据自动释放，不会写入本地磁盘\n\n"
            "📄 开源协议 (LICENSE)\n"
            + "-" * 62 + "\n"
        )
        # 加载 LICENSE 文本（优先读文件，打包后回退到摘要）
        license_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LICENSE")
        try:
            with open(license_path, "r", encoding="utf-8") as lf:
                license_text = lf.read()
        except Exception:
            license_text = (
                "  GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007\n\n"
                "  本软件采用 GPLv3 开源协议发布。\n"
                "  完整协议文本请访问: https://www.gnu.org/licenses/gpl-3.0.html\n"
            )
        info_text += license_text
        self.text_info.insert("1.0", info_text)
        self.text_info.config(state="disabled")

        # 存储分析结果（用于导出和复制）
        self.last_date_results: list[dict] = []
        self.last_region_results: list[dict] = []
        self.last_target_ids: list[str] = []

    # ------------------------------------------------------------------
    # 模式切换
    # ------------------------------------------------------------------
    def _toggle_mode(self):
        """切换本地/网络模式"""
        if self.mode == "local":
            self.mode = "remote"
            self.btn_mode.config(text="💻 本地模式", bg="#4CAF50")
            self._update_status("🔄 切换到网络模式，正在拉取远程数据...", "#FF9800")
        else:
            self.mode = "local"
            self.btn_mode.config(text="🌐 网络模式", bg="#9C27B0")
            self._update_status("🔄 切换到本地模式，正在加载本地数据...", "#FF9800")
        self._auto_load_data()

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _auto_load_data(self):
        """根据当前模式加载数据（自动取消上一次加载）"""
        # 1. 取消上一次加载
        self._cancel_event.set()
        # 2. 创建新的事件给本次加载
        self._cancel_event = threading.Event()
        cancel = self._cancel_event  # 捕获当前事件引用

        if self.mode == "remote":
            self._load_remote_data(cancel)
        else:
            self._load_local_data(cancel)

    def _load_local_data(self, cancel: threading.Event):
        """从本地 data/ 目录加载玩家数据"""
        self.lbl_status.config(text="正在加载本地数据...", fg="#FF9800")
        self.root.update_idletasks()

        def _load():
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
            if not os.path.isdir(data_dir):
                self._update_status("❌ data/ 目录不存在", "#F44336")
                return

            self.all_data.clear()
            self.available_ids.clear()
            self.id_to_name.clear()
            self.name_to_ids.clear()

            pattern = re.compile(r"wplace_players_today_(\d{8})\.json$")
            loaded = 0

            for fname in sorted(os.listdir(data_dir)):
                if cancel.is_set():
                    return  # 被取消，直接退出
                m = pattern.match(fname)
                if not m:
                    continue
                date_str = m.group(1)
                fpath = os.path.join(data_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if cancel.is_set():
                        return
                    self._index_data(date_str, data)
                    loaded += 1
                except Exception:
                    continue

            if not cancel.is_set():
                self._finish_loading(loaded)

        threading.Thread(target=_load, daemon=True).start()

    def _load_remote_data(self, cancel: threading.Event):
        """从远程服务器拉取玩家数据到内存"""
        self.lbl_status.config(text="正在拉取远程数据...", fg="#FF9800")
        self.root.update_idletasks()

        def _load():
            # 1. 获取远程文件列表
            try:
                file_list_url = f"{self.REMOTE_BASE}/data/file_list.json"
                self._update_status("🌐 正在获取远程文件列表...", "#2196F3")

                req = Request(file_list_url, headers={"User-Agent": "WPlace-Analyzer/1.0"})
                with urlopen(req, timeout=15) as resp:
                    file_list = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                if not cancel.is_set():
                    self._update_status(f"❌ 无法连接远程服务器: {e}", "#F44336")
                return

            if cancel.is_set():
                return

            # 筛选玩家当天数据文件
            pattern = re.compile(r"data/wplace_players_today_(\d{8})\.json$")
            player_files = []
            for fname in file_list:
                m = pattern.match(fname)
                if m:
                    player_files.append((m.group(1), f"{self.REMOTE_BASE}/{fname}"))

            if not player_files:
                if not cancel.is_set():
                    self._update_status("❌ 远程服务器上没有找到玩家数据", "#F44336")
                return

            # 按日期排序
            player_files.sort(key=lambda x: x[0])

            self.all_data.clear()
            self.available_ids.clear()
            self.id_to_name.clear()
            self.name_to_ids.clear()

            total = len(player_files)
            loaded = 0
            failed = 0

            for idx, (date_str, url) in enumerate(player_files):
                if cancel.is_set():
                    return  # 被取消，直接退出
                pct = int((idx + 1) / total * 100)
                self._update_status(
                    f"🌐 正在拉取: {self._fmt_date(date_str)}  ({idx + 1}/{total}, {pct}%)",
                    "#2196F3"
                )
                try:
                    req = Request(url, headers={"User-Agent": "WPlace-Analyzer/1.0"})
                    with urlopen(req, timeout=20) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    if cancel.is_set():
                        return
                    self._index_data(date_str, data)
                    loaded += 1
                except Exception:
                    failed += 1
                    continue

            if not cancel.is_set():
                self._finish_loading(loaded, extra=f" | 失败 {failed} 天" if failed else "")

        threading.Thread(target=_load, daemon=True).start()

    def _index_data(self, date_str: str, data: dict):
        """将一天的数据索引到内存结构中"""
        self.all_data[date_str] = data
        for pid, pinfo in data.items():
            self.available_ids.add(pid)
            name = pinfo.get("name", pid)
            self.id_to_name[pid] = name
            self.name_to_ids.setdefault(name.lower(), []).append(pid)

    def _finish_loading(self, loaded: int, extra: str = ""):
        """数据加载完成后的统一收尾"""
        self.available_dates = sorted(self.all_data.keys())

        # 更新日期输入框：起始用最早数据日期，结束用本地当前日期
        today_str = datetime.now().strftime("%Y%m%d")
        if self.available_dates:
            first = f"{self.available_dates[0][:4]}-{self.available_dates[0][4:6]}-{self.available_dates[0][6:8]}"
            last_data = self.available_dates[-1]
            if last_data < today_str:
                last = f"{today_str[:4]}-{today_str[4:6]}-{today_str[6:8]}"
            else:
                last = f"{last_data[:4]}-{last_data[4:6]}-{last_data[6:8]}"
            self.entry_start.delete(0, END)
            self.entry_start.insert(0, first)
            self.entry_end.delete(0, END)
            self.entry_end.insert(0, last)

        mode_label = "🌐 远程" if self.mode == "remote" else "💻 本地"
        self._update_status(
            f"✅ [{mode_label}] 已加载 {loaded} 天数据 | {len(self.available_ids):,} 个账号 | "
            f"{self._fmt_date(self.available_dates[0]) if self.available_dates else '—'} ~ "
            f"{self._fmt_date(self.available_dates[-1]) if self.available_dates else '—'}"
            f"{extra}",
            "#4CAF50"
        )
        self.last_date_results = []
        self.last_region_results = []
        self.last_target_ids = []

    def _update_status(self, text: str, color: str):
        self.root.after(0, lambda: self.lbl_status.config(text=text, fg=color))

    # ------------------------------------------------------------------
    # 日期解析
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_date(raw: str) -> str | None:
        """将用户输入的日期转为 YYYYMMDD"""
        raw = raw.strip().replace("-", "").replace("/", "")
        if len(raw) == 8 and raw.isdigit():
            return raw
        return None

    @staticmethod
    def _fmt_date(d: str) -> str:
        """YYYYMMDD -> YYYY-MM-DD"""
        if len(d) == 8:
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return d

    def _quick_date(self, days: int):
        """快速设置日期范围"""
        if days <= 0:
            self.entry_start.delete(0, END)
            self.entry_end.delete(0, END)
            if self.available_dates:
                first = self._fmt_date(self.available_dates[0])
                # 结束日期用本地当前时间
                last = datetime.now().strftime("%Y-%m-%d")
                self.entry_start.insert(0, first)
                self.entry_end.insert(0, last)
            return
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days - 1)
        self.entry_start.delete(0, END)
        self.entry_start.insert(0, start_date.strftime("%Y-%m-%d"))
        self.entry_end.delete(0, END)
        self.entry_end.insert(0, end_date.strftime("%Y-%m-%d"))

    # ------------------------------------------------------------------
    # 账号搜索
    # ------------------------------------------------------------------
    def _on_search_key(self, event):
        """键盘输入时实时搜索"""
        self._search_account()

    def _search_account(self):
        """搜索账号并显示建议"""
        query = self.entry_search.get().strip().lower()
        self.listbox_suggestions.delete(*self.listbox_suggestions.get_children())
        if not query or len(query) < 1:
            return

        results = []
        for pid, name in self.id_to_name.items():
            if query in pid.lower() or query in name.lower():
                results.append((pid, name))

        # 限制显示数量
        for pid, name in results[:30]:
            self.listbox_suggestions.insert("", END, values=(pid, name))

    def _add_suggestion(self, event):
        """双击搜索建议，添加到输入框"""
        sel = self.listbox_suggestions.selection()
        if sel:
            item = self.listbox_suggestions.item(sel[0])
            pid = item["values"][0]
            current = self.text_accounts.get("1.0", END).strip()
            if current:
                self.text_accounts.insert(END, f"\n{pid}")
            else:
                self.text_accounts.insert("1.0", pid)

    # ------------------------------------------------------------------
    # 解析用户输入的账号
    # ------------------------------------------------------------------
    def _parse_input_accounts(self) -> list[str]:
        """从输入框解析账号 ID 列表（支持 ID 或 name）"""
        raw = self.text_accounts.get("1.0", END).strip()
        if not raw:
            return []

        ids = set()
        for line in raw.replace(",", "\n").split("\n"):
            token = line.strip()
            if not token:
                continue
            # 如果是纯数字，当作 ID
            if token.isdigit():
                if token in self.available_ids:
                    ids.add(token)
            else:
                # 按名称搜索
                found = self.name_to_ids.get(token.lower(), [])
                if not found:
                    # 模糊匹配
                    for name_lower, id_list in self.name_to_ids.items():
                        if token.lower() in name_lower:
                            found.extend(id_list)
                for pid in found:
                    ids.add(pid)

        return sorted(ids)

    # ------------------------------------------------------------------
    # 分析
    # ------------------------------------------------------------------
    def _on_analyze(self):
        """执行分析"""
        target_ids = self._parse_input_accounts()
        if len(target_ids) < 2:
            messagebox.showwarning("提示", "请至少输入 2 个有效的账号 ID 或名称")
            return

        # 日期范围
        start_raw = self.entry_start.get().strip()
        end_raw = self.entry_end.get().strip()
        date_start = self._parse_date(start_raw) if start_raw else (self.available_dates[0] if self.available_dates else None)
        date_end = self._parse_date(end_raw) if end_raw else (self.available_dates[-1] if self.available_dates else None)

        # 筛选可用日期
        filtered_dates = [d for d in self.available_dates
                          if (date_start is None or d >= date_start)
                          and (date_end is None or d <= date_end)]

        if not filtered_dates:
            messagebox.showwarning("提示", "所选日期范围内没有可用数据")
            return

        self.lbl_status.config(text="正在分析中...", fg="#FF9800")
        self.root.update_idletasks()

        def _analyze():
            results_date, results_region, summary_lines, raw_lines = self._do_analysis(
                target_ids, filtered_dates
            )
            self.root.after(0, lambda: self._display_results(
                results_date, results_region, summary_lines, raw_lines, target_ids
            ))
            self.root.after(0, lambda: self.lbl_status.config(
                text=f"✅ 分析完成 | {len(target_ids)} 个账号 | {len(filtered_dates)} 天数据",
                fg="#4CAF50"
            ))

        threading.Thread(target=_analyze, daemon=True).start()

    def _do_analysis(self, target_ids: list[str], filtered_dates: list[str]):
        """执行核心分析计算"""
        # 构建每个账号的日期 -> places 映射
        account_date_places: dict[str, dict[str, set]] = {}  # {id: {date: set(region_ids)}}
        account_dates: dict[str, set] = {}                    # {id: set(dates)}
        account_all_regions: dict[str, set] = {}              # {id: set(all_region_ids)}
        account_total_pixels: dict[str, int] = {}             # {id: total_pixels}

        for pid in target_ids:
            account_date_places[pid] = {}
            account_dates[pid] = set()
            account_all_regions[pid] = set()
            account_total_pixels[pid] = 0

            for d in filtered_dates:
                data = self.all_data.get(d, {})
                if pid in data:
                    account_dates[pid].add(d)
                    places = data[pid].get("places", {})
                    region_set = set(places.keys())
                    account_date_places[pid][d] = region_set
                    account_all_regions[pid].update(region_set)
                    account_total_pixels[pid] += data[pid].get("totalPixelsPainted", 0)

        # ---- 日期重合 ----
        date_results = []
        for i in range(len(target_ids)):
            for j in range(i + 1, len(target_ids)):
                id_a, id_b = target_ids[i], target_ids[j]
                name_a = self.id_to_name.get(id_a, id_a)
                name_b = self.id_to_name.get(id_b, id_b)

                dates_a = account_dates[id_a]
                dates_b = account_dates[id_b]
                common = sorted(dates_a & dates_b)
                union = dates_a | dates_b
                rate = len(common) / len(union) * 100 if union else 0

                date_results.append({
                    "accounts": f"[{id_a}] {name_a}  ↔  [{id_b}] {name_b}",
                    "common_dates_count": len(common),
                    "total_dates_pair": len(union),
                    "overlap_rate": f"{rate:.1f}%",
                    "common_dates": ", ".join(self._fmt_date(d) for d in common[:20])
                                   + (f" 等{len(common)}天" if len(common) > 20 else ""),
                    "_common_set": common,
                    "_rate": rate,
                })

        date_results.sort(key=lambda x: (-x["common_dates_count"], -x["_rate"]))

        # ---- 区块重合 ----
        region_results = []
        for i in range(len(target_ids)):
            for j in range(i + 1, len(target_ids)):
                id_a, id_b = target_ids[i], target_ids[j]
                name_a = self.id_to_name.get(id_a, id_a)
                name_b = self.id_to_name.get(id_b, id_b)

                regions_a = account_all_regions[id_a]
                regions_b = account_all_regions[id_b]
                common_reg = regions_a & regions_b
                union_reg = regions_a | regions_b
                rate = len(common_reg) / len(union_reg) * 100 if union_reg else 0

                region_results.append({
                    "accounts": f"[{id_a}] {name_a}  ↔  [{id_b}] {name_b}",
                    "common_regions": len(common_reg),
                    "total_regions_pair": len(union_reg),
                    "overlap_rate": f"{rate:.1f}%",
                    "_common_set": common_reg,
                    "_rate": rate,
                    "_id_a": id_a, "_id_b": id_b,
                })

        region_results.sort(key=lambda x: (-x["common_regions"], -x["_rate"]))

        # ---- 综合摘要 ----
        summary_lines = []
        summary_lines.append("=" * 70)
        summary_lines.append("  WPlace 账号重合度分析报告")
        summary_lines.append("=" * 70)
        summary_lines.append(f"  分析日期范围: {self._fmt_date(filtered_dates[0])} ~ {self._fmt_date(filtered_dates[-1])}")
        summary_lines.append(f"  数据天数: {len(filtered_dates)}")
        summary_lines.append(f"  分析账号数: {len(target_ids)}")
        summary_lines.append("")

        summary_lines.append("【参与分析的账号】")
        for pid in target_ids:
            name = self.id_to_name.get(pid, pid)
            days = len(account_dates[pid])
            regions = len(account_all_regions[pid])
            pixels = account_total_pixels[pid]
            summary_lines.append(f"  [{pid}] {name}  —  活跃 {days} 天, "
                                 f"{regions} 个区块, {pixels:,} 像素")

        summary_lines.append("")
        summary_lines.append("【日期重合度 (Top 10)】")
        for r in date_results[:10]:
            summary_lines.append(f"  {r['accounts']}")
            summary_lines.append(f"    共同活跃: {r['common_dates_count']} 天 / "
                                 f"共 {r['total_dates_pair']} 天, 重合率 {r['overlap_rate']}")

        summary_lines.append("")
        summary_lines.append("【区块重合度 (Top 10)】")
        for r in region_results[:10]:
            summary_lines.append(f"  {r['accounts']}")
            summary_lines.append(f"    共同区块: {r['common_regions']} 个 / "
                                 f"共 {r['total_regions_pair']} 个, 重合率 {r['overlap_rate']}")

        summary_lines.append("")
        summary_lines.append("=" * 70)

        # ---- 原始数据概览 ----
        raw_lines = []
        for pid in target_ids:
            name = self.id_to_name.get(pid, pid)
            days = len(account_dates[pid])
            regions = len(account_all_regions[pid])
            pixels = account_total_pixels[pid]
            avg_p = pixels / days if days else 0
            raw_lines.append({
                "account": f"[{pid}] {name}",
                "active_dates": days,
                "total_pixels": f"{pixels:,}",
                "total_regions": regions,
                "avg_pixels_per_day": f"{avg_p:,.0f}",
            })

        return date_results, region_results, summary_lines, raw_lines

    def _display_results(self, date_results, region_results, summary_lines, raw_lines, target_ids):
        """将分析结果显示到 UI"""
        self.last_date_results = date_results
        self.last_region_results = region_results
        self.last_target_ids = target_ids

        # 日期重合
        self.tree_date.delete(*self.tree_date.get_children())
        for i, r in enumerate(date_results):
            tag = "high" if (r["common_dates_count"] / max(r["total_dates_pair"], 1)) > 0.5 else ""
            self.tree_date.insert("", END, values=(
                r["accounts"], r["common_dates_count"], r["total_dates_pair"],
                r["overlap_rate"], r["common_dates"]
            ), tags=(tag,))
        self.tree_date.tag_configure("high", background="#FFF3E0")

        # 区块重合
        self.tree_region.delete(*self.tree_region.get_children())
        for i, r in enumerate(region_results):
            tag = "high" if r["_rate"] > 50 else ""
            self.tree_region.insert("", END, values=(
                r["accounts"], r["common_regions"], r["total_regions_pair"],
                r["overlap_rate"]
            ), tags=(tag,))
        self.tree_region.tag_configure("high", background="#E8F5E9")

        # 摘要
        self.text_summary.delete("1.0", END)
        self.text_summary.insert("1.0", "\n".join(summary_lines))

        # 原始数据
        self.tree_raw.delete(*self.tree_raw.get_children())
        for r in raw_lines:
            self.tree_raw.insert("", END, values=(
                r["account"], r["active_dates"], r["total_pixels"],
                r["total_regions"], r["avg_pixels_per_day"]
            ))

        # 切换到综合摘要
        self.notebook.select(2)

    # ------------------------------------------------------------------
    # 区块详情弹窗
    # ------------------------------------------------------------------
    def _show_region_detail(self, event):
        """双击区块重合行，显示共同区块详情"""
        sel = self.tree_region.selection()
        if not sel:
            return
        idx = self.tree_region.index(sel[0])
        if idx >= len(self.last_region_results):
            return

        r = self.last_region_results[idx]
        common = r.get("_common_set", set())

        detail_win = Toplevel(self.root)
        detail_win.title(f"共同区块详情 - {r['accounts']}")
        detail_win.geometry("600x400")

        Label(detail_win, text=f"账号对: {r['accounts']}",
              font=("Microsoft YaHei", 10, "bold")).pack(pady=8)
        Label(detail_win, text=f"共同区块数: {r['common_regions']} | 重合率: {r['overlap_rate']}",
              foreground="#666").pack(pady=2)

        frame = Frame(detail_win)
        frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        text = Text(frame, wrap="word", font=("Consolas", 10))
        text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll = Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=RIGHT, fill=Y)

        sorted_regions = sorted(common, key=lambda x: int(x))
        chunk_size = 10
        lines = []
        for i in range(0, len(sorted_regions), chunk_size):
            chunk = sorted_regions[i:i + chunk_size]
            lines.append(", ".join(chunk))
        text.insert("1.0", "\n".join(lines))
        text.config(state="disabled")

    # ------------------------------------------------------------------
    # 导出 CSV
    # ------------------------------------------------------------------
    def _export_csv(self):
        if not self.last_date_results and not self.last_region_results:
            messagebox.showwarning("提示", "没有可导出的数据，请先进行分析")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            initialfile="wplace_overlap_analysis.csv"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                writer.writerow(["=== 日期重合度分析 ==="])
                writer.writerow(["账号对", "共同活跃天数", "两人总活跃天数", "日期重合率", "共同日期列表"])
                for r in self.last_date_results:
                    writer.writerow([
                        r["accounts"], r["common_dates_count"],
                        r["total_dates_pair"], r["overlap_rate"], r["common_dates"]
                    ])

                writer.writerow([])
                writer.writerow(["=== 作画区块重合度分析 ==="])
                writer.writerow(["账号对", "共同区块数", "两人总区块数", "区块重合率"])
                for r in self.last_region_results:
                    writer.writerow([
                        r["accounts"], r["common_regions"],
                        r["total_regions_pair"], r["overlap_rate"]
                    ])

            messagebox.showinfo("成功", f"已导出到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ------------------------------------------------------------------
    # 复制结果
    # ------------------------------------------------------------------
    def _copy_results(self):
        """复制当前摘要到剪贴板"""
        text = self.text_summary.get("1.0", END).strip()
        if not text:
            messagebox.showwarning("提示", "没有可复制的内容")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("成功", "摘要内容已复制到剪贴板")


def main():
    root = Tk()
    AccountAnalyzer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
