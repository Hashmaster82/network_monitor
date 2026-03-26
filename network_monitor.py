# -*- coding: utf-8 -*-
"""
Network Monitor - IT Infrastructure Health Check Tool
Автор: Matrix Agent
Версия: 1.1
Описание: Программа для мониторинга критичных сетевых узлов
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import json
import os
import socket
import subprocess
import threading
import time
import re
import winsound
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

# Константы
APP_NAME = "Network Monitor"
APP_VERSION = "1.1"  # ИЗМЕНЕНО: обновлена версия
DEFAULT_PING_TIMEOUT = 1000  # ms
DEFAULT_PORT_TIMEOUT = 2  # seconds
HIGH_LATENCY_THRESHOLD = 100  # ms
AUTO_REFRESH_INTERVALS = [30, 60, 120, 300, 600]  # секунды

# Категории по умолчанию
DEFAULT_CATEGORIES = [
    "Серверы",
    "Сетевое оборудование",
    "Принтеры",
    "Рабочие станции",
    "Другое"
]

# Приоритеты
PRIORITIES = {
    "critical": {"name": "Критичный", "color": "#FF4444"},
    "important": {"name": "Важный", "color": "#FFA500"},
    "normal": {"name": "Обычный", "color": "#4CAF50"}
}

# Статусы
STATUS_OK = "online"
STATUS_FAIL = "offline"
STATUS_HIGH_LATENCY = "high_latency"
STATUS_CHECKING = "checking"


class ConfigManager:
    """Управление конфигурацией и путями к данным"""

    def __init__(self):
        self.config_file = self._get_config_path()
        self.config = self._load_config()

    def _get_config_path(self):
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        config_dir = os.path.join(appdata, 'NetworkMonitor')
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, 'config.json')

    def _load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def get_data_path(self):
        return self.config.get('data_path', '')

    def set_data_path(self, path):
        self.config['data_path'] = path
        self.save_config()


class DataManager:
    """Управление данными узлов"""

    def __init__(self, data_path):
        self.data_path = data_path
        self.nodes_file = os.path.join(data_path, 'nodes.json')
        self.history_file = os.path.join(data_path, 'history.json')
        self.categories_file = os.path.join(data_path, 'categories.json')

        os.makedirs(data_path, exist_ok=True)

        self.nodes = self._load_nodes()
        self.categories = self._load_categories()
        self.history = self._load_history()

    def _load_nodes(self):
        if os.path.exists(self.nodes_file):
            try:
                with open(self.nodes_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []

    def _load_categories(self):
        if os.path.exists(self.categories_file):
            try:
                with open(self.categories_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return DEFAULT_CATEGORIES.copy()

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data[-1000:] if len(data) > 1000 else data
            except:
                pass
        return []

    def save_nodes(self):
        with open(self.nodes_file, 'w', encoding='utf-8') as f:
            json.dump(self.nodes, f, ensure_ascii=False, indent=2)

    def save_categories(self):
        with open(self.categories_file, 'w', encoding='utf-8') as f:
            json.dump(self.categories, f, ensure_ascii=False, indent=2)

    def save_history(self):
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history[-1000:], f, ensure_ascii=False, indent=2)

    def add_node(self, node):
        node['id'] = str(int(time.time() * 1000))
        self.nodes.append(node)
        self.save_nodes()
        return node

    def update_node(self, node_id, updated_data):
        for i, node in enumerate(self.nodes):
            if node['id'] == node_id:
                self.nodes[i].update(updated_data)
                self.save_nodes()
                return True
        return False

    def delete_node(self, node_id):
        self.nodes = [n for n in self.nodes if n['id'] != node_id]
        self.save_nodes()

    def add_history_entry(self, entry):
        entry['timestamp'] = datetime.now().isoformat()
        self.history.append(entry)
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
        self.save_history()

    def add_category(self, category):
        if category not in self.categories:
            self.categories.append(category)
            self.save_categories()

    def export_nodes(self, filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.nodes, f, ensure_ascii=False, indent=2)

    def import_nodes(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            imported = json.load(f)
            for node in imported:
                node['id'] = str(int(time.time() * 1000) + len(self.nodes))
                self.nodes.append(node)
            self.save_nodes()
            return len(imported)


class NetworkChecker:
    """Проверка сетевых узлов"""

    @staticmethod
    def ping(host, timeout=DEFAULT_PING_TIMEOUT):
        try:
            cmd = f'ping -n 1 -w {timeout} {host}'
            result = subprocess.run(
                cmd, capture_output=True, text=True, shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                output = result.stdout
                patterns = [
                    r'время[=<](\d+)\s*мс',
                    r'time[=<](\d+)\s*ms',
                    r'Average = (\d+)ms',
                    r'Среднее = (\d+)'
                ]
                for pattern in patterns:
                    match = re.search(pattern, output, re.IGNORECASE)
                    if match:
                        return True, int(match.group(1))
                return True, 0
            return False, None
        except Exception:
            return False, None

    @staticmethod
    def check_port(host, port, timeout=DEFAULT_PORT_TIMEOUT):
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            latency = int((time.time() - start_time) * 1000)
            sock.close()
            return result == 0, latency if result == 0 else None
        except:
            return False, None

    @staticmethod
    def check_node(node):
        results = {
            'id': node['id'],
            'name': node['name'],
            'ip': node['ip'],
            'ping': {'success': False, 'latency': None},
            'ports': {},
            'status': STATUS_FAIL,
            'timestamp': datetime.now().isoformat()
        }

        success, latency = NetworkChecker.ping(node['ip'])
        results['ping']['success'] = success
        results['ping']['latency'] = latency

        ports = node.get('ports', [])
        for port in ports:
            port_success, port_latency = NetworkChecker.check_port(node['ip'], port)
            results['ports'][port] = {'success': port_success, 'latency': port_latency}

        if success:
            if latency and latency > HIGH_LATENCY_THRESHOLD:
                results['status'] = STATUS_HIGH_LATENCY
            else:
                results['status'] = STATUS_OK
        else:
            results['status'] = STATUS_FAIL

        return results


class NodeDialog(tk.Toplevel):
    """Диалог добавления/редактирования узла"""

    def __init__(self, parent, categories, node=None):
        super().__init__(parent)
        self.result = None
        self.node = node
        self.categories = categories

        self.title("Редактирование узла" if node else "Добавление узла")
        self.geometry("450x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._create_widgets()

        if node:
            self._fill_data(node)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Название:").pack(anchor=tk.W)
        self.name_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.name_var, width=50).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(main_frame, text="IP адрес / Hostname:").pack(anchor=tk.W)
        self.ip_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.ip_var, width=50).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(main_frame, text="Категория:").pack(anchor=tk.W)
        self.category_var = tk.StringVar()
        category_combo = ttk.Combobox(main_frame, textvariable=self.category_var,
                                      values=self.categories, width=47)
        category_combo.pack(fill=tk.X, pady=(0, 10))
        if self.categories:
            category_combo.set(self.categories[0])

        ttk.Label(main_frame, text="Приоритет:").pack(anchor=tk.W)
        self.priority_var = tk.StringVar(value="normal")
        priority_frame = ttk.Frame(main_frame)
        priority_frame.pack(fill=tk.X, pady=(0, 10))
        for key, value in PRIORITIES.items():
            ttk.Radiobutton(priority_frame, text=value['name'],
                            variable=self.priority_var, value=key).pack(side=tk.LEFT, padx=5)

        ttk.Label(main_frame, text="Порты для проверки (через запятую):").pack(anchor=tk.W)
        self.ports_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.ports_var, width=50).pack(fill=tk.X, pady=(0, 10))
        ttk.Label(main_frame, text="Например: 80, 443, 3389",
                  font=('Segoe UI', 8)).pack(anchor=tk.W)

        ttk.Label(main_frame, text="Комментарий:").pack(anchor=tk.W, pady=(10, 0))
        self.comment_text = tk.Text(main_frame, height=4, width=50)
        self.comment_text.pack(fill=tk.X, pady=(0, 10))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(btn_frame, text="Сохранить", command=self._on_save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self._on_cancel).pack(side=tk.RIGHT)

    def _fill_data(self, node):
        self.name_var.set(node.get('name', ''))
        self.ip_var.set(node.get('ip', ''))
        self.category_var.set(node.get('category', self.categories[0] if self.categories else ''))
        self.priority_var.set(node.get('priority', 'normal'))
        self.ports_var.set(', '.join(map(str, node.get('ports', []))))
        self.comment_text.insert('1.0', node.get('comment', ''))

    def _parse_ports(self):
        ports_str = self.ports_var.get().strip()
        if not ports_str:
            return []
        try:
            ports = [int(p.strip()) for p in ports_str.split(',') if p.strip()]
            return [p for p in ports if 1 <= p <= 65535]
        except ValueError:
            return []

    def _on_save(self):
        name = self.name_var.get().strip()
        ip = self.ip_var.get().strip()

        if not name:
            messagebox.showerror("Ошибка", "Введите название узла")
            return
        if not ip:
            messagebox.showerror("Ошибка", "Введите IP адрес или hostname")
            return

        self.result = {
            'name': name,
            'ip': ip,
            'category': self.category_var.get() or "Другое",
            'priority': self.priority_var.get(),
            'ports': self._parse_ports(),
            'comment': self.comment_text.get('1.0', tk.END).strip()
        }
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


class HistoryDialog(tk.Toplevel):
    """Диалог просмотра истории"""

    def __init__(self, parent, history):
        super().__init__(parent)
        self.title("История проверок")
        self.geometry("800x500")
        self.transient(parent)

        self._create_widgets(history)

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self, history):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('timestamp', 'name', 'ip', 'status', 'latency')
        tree = ttk.Treeview(main_frame, columns=columns, show='headings', height=20)

        tree.heading('timestamp', text='Время')
        tree.heading('name', text='Название')
        tree.heading('ip', text='IP')
        tree.heading('status', text='Статус')
        tree.heading('latency', text='Задержка')

        tree.column('timestamp', width=150)
        tree.column('name', width=200)
        tree.column('ip', width=150)
        tree.column('status', width=100)
        tree.column('latency', width=100)

        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for entry in reversed(history[-500:]):
            timestamp = entry.get('timestamp', '')[:19].replace('T', ' ')
            status_text = {
                STATUS_OK: '✓ Online',
                STATUS_FAIL: '✗ Offline',
                STATUS_HIGH_LATENCY: '⚠ Высокий пинг'
            }.get(entry.get('status', ''), entry.get('status', ''))

            latency = entry.get('ping', {}).get('latency')
            latency_text = f"{latency} ms" if latency else "-"

            tree.insert('', tk.END, values=(
                timestamp, entry.get('name', ''), entry.get('ip', ''),
                status_text, latency_text
            ))


class NetworkMonitorApp:
    """Главное приложение"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)

        try:
            self.root.iconbitmap('icon.ico')
        except:
            pass

        self.config_manager = ConfigManager()
        self.data_manager = None
        self.check_results = {}
        self.auto_refresh_job = None
        self.is_checking = False
        self.show_offline_only = False  # ДОБАВЛЕНО: флаг фильтра offline

        self._setup_styles()
        self._create_menu()
        self._create_widgets()

        data_path = self.config_manager.get_data_path()
        if not data_path or not os.path.exists(data_path):
            self._select_data_folder()
        else:
            self._load_data(data_path)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        style.configure("Online.TLabel", foreground="#2E7D32", font=('Segoe UI', 10, 'bold'))
        style.configure("Offline.TLabel", foreground="#C62828", font=('Segoe UI', 10, 'bold'))
        style.configure("HighLatency.TLabel", foreground="#F57C00", font=('Segoe UI', 10, 'bold'))
        style.configure("Checking.TLabel", foreground="#1565C0", font=('Segoe UI', 10))
        style.configure("Header.TLabel", font=('Segoe UI', 12, 'bold'))
        style.configure("Action.TButton", font=('Segoe UI', 10))

        # ДОБАВЛЕНО: стили для кнопки OFFline (неактивная и активная)
        style.configure("OfflineFilter.TButton", font=('Segoe UI', 10))
        style.configure("OfflineFilterActive.TButton", font=('Segoe UI', 10, 'bold'))

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Выбрать папку данных...", command=self._select_data_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Импорт узлов...", command=self._import_nodes)
        file_menu.add_command(label="Экспорт узлов...", command=self._export_nodes)
        file_menu.add_separator()
        file_menu.add_command(label="Экспорт отчёта (HTML)...", command=lambda: self._export_report('html'))
        file_menu.add_command(label="Экспорт отчёта (TXT)...", command=lambda: self._export_report('txt'))
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_close)

        nodes_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Узлы", menu=nodes_menu)
        nodes_menu.add_command(label="Добавить узел...", command=self._add_node)
        nodes_menu.add_command(label="Управление категориями...", command=self._manage_categories)

        check_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Проверка", menu=check_menu)
        check_menu.add_command(label="Проверить все", command=self._check_all)
        check_menu.add_command(label="Проверить выбранный", command=self._check_selected)
        check_menu.add_separator()
        check_menu.add_command(label="История проверок", command=self._show_history)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", command=self._show_about)

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Панель инструментов
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text="➕ Добавить узел", command=self._add_node,
                   style="Action.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔄 Проверить все", command=self._check_all,
                   style="Action.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="✏️ Редактировать", command=self._edit_selected,
                   style="Action.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🗑️ Удалить", command=self._delete_selected,
                   style="Action.TButton").pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # ============================================================
        # ДОБАВЛЕНО: Кнопка фильтра OFFline
        # ============================================================
        self.offline_filter_btn = tk.Button(
            toolbar,
            text="🔴 OFFline",
            command=self._toggle_offline_filter,
            font=('Segoe UI', 10),
            bg='#f0f0f0',  # обычный фон
            fg='#333333',  # обычный текст
            activebackground='#e0e0e0',
            relief=tk.RAISED,
            bd=2,
            padx=10,
            pady=2
        )
        self.offline_filter_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        # ============================================================

        # Автообновление
        ttk.Label(toolbar, text="Автообновление:").pack(side=tk.LEFT, padx=5)
        self.auto_refresh_var = tk.StringVar(value="Выкл")
        auto_refresh_combo = ttk.Combobox(toolbar, textvariable=self.auto_refresh_var,
                                          values=["Выкл", "30 сек", "1 мин", "2 мин", "5 мин", "10 мин"],
                                          width=10, state='readonly')
        auto_refresh_combo.pack(side=tk.LEFT)
        auto_refresh_combo.bind('<<ComboboxSelected>>', self._on_auto_refresh_change)

        # Фильтр по категории
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Label(toolbar, text="Категория:").pack(side=tk.LEFT, padx=5)
        self.filter_category_var = tk.StringVar(value="Все")
        self.filter_combo = ttk.Combobox(toolbar, textvariable=self.filter_category_var,
                                         values=["Все"], width=20, state='readonly')
        self.filter_combo.pack(side=tk.LEFT)
        self.filter_combo.bind('<<ComboboxSelected>>', lambda e: self._refresh_tree())

        # Статус справа
        self.status_label = ttk.Label(toolbar, text="")
        self.status_label.pack(side=tk.RIGHT, padx=5)

        # Область с таблицей
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('priority', 'name', 'ip', 'category', 'status', 'latency', 'ports', 'comment')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')

        self.tree.heading('priority', text='⚡')
        self.tree.heading('name', text='Название')
        self.tree.heading('ip', text='IP / Hostname')
        self.tree.heading('category', text='Категория')
        self.tree.heading('status', text='Статус')
        self.tree.heading('latency', text='Задержка')
        self.tree.heading('ports', text='Порты')
        self.tree.heading('comment', text='Комментарий')

        self.tree.column('priority', width=30, anchor=tk.CENTER)
        self.tree.column('name', width=180)
        self.tree.column('ip', width=140)
        self.tree.column('category', width=130)
        self.tree.column('status', width=100, anchor=tk.CENTER)
        self.tree.column('latency', width=80, anchor=tk.CENTER)
        self.tree.column('ports', width=150)
        self.tree.column('comment', width=200)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<Double-1>', lambda e: self._edit_selected())

        self.tree.tag_configure('online', background='#E8F5E9')
        self.tree.tag_configure('offline', background='#FFEBEE')
        self.tree.tag_configure('high_latency', background='#FFF3E0')
        self.tree.tag_configure('checking', background='#E3F2FD')
        self.tree.tag_configure('critical', foreground='#C62828')
        self.tree.tag_configure('important', foreground='#E65100')

        # Строка статуса внизу
        status_bar = ttk.Frame(main_frame)
        status_bar.pack(fill=tk.X, pady=(10, 0))

        self.stats_label = ttk.Label(status_bar, text="Узлов: 0 | Online: 0 | Offline: 0")
        self.stats_label.pack(side=tk.LEFT)

        self.last_check_label = ttk.Label(status_bar, text="")
        self.last_check_label.pack(side=tk.RIGHT)

    # ================================================================
    # ДОБАВЛЕНО: Метод переключения фильтра OFFline
    # ================================================================
    def _toggle_offline_filter(self):
        """Переключение фильтра показа только offline узлов"""
        self.show_offline_only = not self.show_offline_only

        if self.show_offline_only:
            # Кнопка активна — выделяем красным цветом
            self.offline_filter_btn.config(
                bg='#C62828',  # красный фон
                fg='white',  # белый текст
                activebackground='#D32F2F',
                relief=tk.SUNKEN,  # вдавленная кнопка
                text="🔴 OFFline ✓"
            )
        else:
            # Кнопка неактивна — обычный вид
            self.offline_filter_btn.config(
                bg='#f0f0f0',
                fg='#333333',
                activebackground='#e0e0e0',
                relief=tk.RAISED,
                text="🔴 OFFline"
            )

        # Обновляем таблицу с учётом нового фильтра
        self._refresh_tree()

    # ================================================================

    def _select_data_folder(self):
        folder = filedialog.askdirectory(
            title="Выберите папку для хранения данных",
            initialdir=os.path.expanduser('~')
        )
        if folder:
            self.config_manager.set_data_path(folder)
            self._load_data(folder)
            messagebox.showinfo("Успех", f"Данные будут храниться в:\n{folder}")

    def _load_data(self, data_path):
        self.data_manager = DataManager(data_path)
        self._update_filter_categories()
        self._refresh_tree()

    def _update_filter_categories(self):
        if self.data_manager:
            categories = ["Все"] + self.data_manager.categories
            self.filter_combo['values'] = categories

    def _refresh_tree(self):
        """Обновление таблицы"""
        if not self.data_manager:
            return

        # Очистка
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Фильтр по категории
        filter_cat = self.filter_category_var.get()
        nodes = self.data_manager.nodes
        if filter_cat != "Все":
            nodes = [n for n in nodes if n.get('category') == filter_cat]

        # ============================================================
        # ДОБАВЛЕНО: Фильтр по статусу offline
        # ============================================================
        if self.show_offline_only:
            nodes = [
                n for n in nodes
                if self.check_results.get(n['id'], {}).get('status') == STATUS_FAIL
            ]
        # ============================================================

        # Сортировка по приоритету
        priority_order = {'critical': 0, 'important': 1, 'normal': 2}
        nodes = sorted(nodes, key=lambda x: priority_order.get(x.get('priority', 'normal'), 2))

        # Статистика (считаем по ВСЕМ узлам, не по отфильтрованным)
        online_count = 0
        offline_count = 0
        for node in self.data_manager.nodes:
            result = self.check_results.get(node['id'], {})
            status = result.get('status', '')
            if status == STATUS_OK or status == STATUS_HIGH_LATENCY:
                online_count += 1
            elif status == STATUS_FAIL:
                offline_count += 1

        for node in nodes:
            node_id = node['id']
            result = self.check_results.get(node_id, {})

            # Приоритет
            priority = node.get('priority', 'normal')
            priority_icon = {'critical': '🔴', 'important': '🟡', 'normal': '🟢'}.get(priority, '⚪')

            # Статус
            status = result.get('status', '')
            if status == STATUS_OK:
                status_text = '✓ Online'
            elif status == STATUS_FAIL:
                status_text = '✗ Offline'
            elif status == STATUS_HIGH_LATENCY:
                status_text = '⚠ Высокий пинг'
            elif status == STATUS_CHECKING:
                status_text = '⏳ Проверка...'
            else:
                status_text = '—'

            # Задержка
            latency = result.get('ping', {}).get('latency')
            latency_text = f"{latency} ms" if latency else "—"

            # Порты
            ports = node.get('ports', [])
            port_results = result.get('ports', {})
            ports_text = ""
            if ports:
                port_statuses = []
                for p in ports:
                    pr = port_results.get(p, {})
                    if pr.get('success'):
                        port_statuses.append(f"✓{p}")
                    elif pr.get('success') is False:
                        port_statuses.append(f"✗{p}")
                    else:
                        port_statuses.append(str(p))
                ports_text = ", ".join(port_statuses)

            # Теги
            tags = []
            if status:
                tags.append(status)
            if priority in ('critical', 'important'):
                tags.append(priority)

            self.tree.insert('', tk.END, iid=node_id, values=(
                priority_icon,
                node.get('name', ''),
                node.get('ip', ''),
                node.get('category', ''),
                status_text,
                latency_text,
                ports_text,
                node.get('comment', '')[:50]
            ), tags=tags)

        # ИЗМЕНЕНО: показываем общую статистику + сколько отображается при фильтре
        total = len(self.data_manager.nodes)
        shown = len(nodes)

        if self.show_offline_only:
            self.stats_label.config(
                text=f"Узлов: {total} | Online: {online_count} | "
                     f"Offline: {offline_count} | 🔴 Показано offline: {shown}"
            )
        else:
            self.stats_label.config(
                text=f"Узлов: {total} | Online: {online_count} | Offline: {offline_count}"
            )

    def _add_node(self):
        if not self.data_manager:
            messagebox.showwarning("Внимание", "Сначала выберите папку для хранения данных")
            return

        dialog = NodeDialog(self.root, self.data_manager.categories)
        self.root.wait_window(dialog)

        if dialog.result:
            if dialog.result['category'] not in self.data_manager.categories:
                self.data_manager.add_category(dialog.result['category'])
                self._update_filter_categories()

            self.data_manager.add_node(dialog.result)
            self._refresh_tree()

    def _edit_selected(self):
        if not self.data_manager:
            return

        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите узел для редактирования")
            return

        node_id = selection[0]
        node = next((n for n in self.data_manager.nodes if n['id'] == node_id), None)
        if not node:
            return

        dialog = NodeDialog(self.root, self.data_manager.categories, node)
        self.root.wait_window(dialog)

        if dialog.result:
            if dialog.result['category'] not in self.data_manager.categories:
                self.data_manager.add_category(dialog.result['category'])
                self._update_filter_categories()

            self.data_manager.update_node(node_id, dialog.result)
            self._refresh_tree()

    def _delete_selected(self):
        if not self.data_manager:
            return

        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите узел для удаления")
            return

        node_id = selection[0]
        node = next((n for n in self.data_manager.nodes if n['id'] == node_id), None)
        if not node:
            return

        if messagebox.askyesno("Подтверждение",
                               f"Удалить узел '{node.get('name', '')}'?"):
            self.data_manager.delete_node(node_id)
            if node_id in self.check_results:
                del self.check_results[node_id]
            self._refresh_tree()

    def _check_all(self):
        if not self.data_manager or not self.data_manager.nodes:
            return

        if self.is_checking:
            return

        self.is_checking = True
        self.status_label.config(text="Проверка...")

        for node in self.data_manager.nodes:
            self.check_results[node['id']] = {'status': STATUS_CHECKING}
        self._refresh_tree()

        threading.Thread(target=self._perform_check_all, daemon=True).start()

    def _perform_check_all(self):
        nodes = self.data_manager.nodes.copy()
        failed_critical = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(NetworkChecker.check_node, node): node for node in nodes}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    node_id = result['id']
                    self.check_results[node_id] = result

                    self.data_manager.add_history_entry(result)

                    node = futures[future]
                    if node.get('priority') == 'critical' and result['status'] == STATUS_FAIL:
                        failed_critical.append(node['name'])

                    self.root.after(0, self._refresh_tree)
                except Exception as e:
                    print(f"Ошибка проверки: {e}")

        self.is_checking = False
        self.root.after(0, lambda: self.status_label.config(text=""))
        self.root.after(0, lambda: self.last_check_label.config(
            text=f"Последняя проверка: {datetime.now().strftime('%H:%M:%S')}"
        ))

        if failed_critical:
            self.root.after(0, lambda: self._alert_critical_failure(failed_critical))

    def _alert_critical_failure(self, failed_nodes):
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except:
            pass

        message = "ВНИМАНИЕ! Недоступны критичные узлы:\n\n" + "\n".join(f"• {name}" for name in failed_nodes)
        messagebox.showwarning("Критичные узлы недоступны", message)

    def _check_selected(self):
        if not self.data_manager:
            return

        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите узел для проверки")
            return

        node_id = selection[0]
        node = next((n for n in self.data_manager.nodes if n['id'] == node_id), None)
        if not node:
            return

        self.check_results[node_id] = {'status': STATUS_CHECKING}
        self._refresh_tree()

        def check():
            result = NetworkChecker.check_node(node)
            self.check_results[node_id] = result
            self.data_manager.add_history_entry(result)
            self.root.after(0, self._refresh_tree)

        threading.Thread(target=check, daemon=True).start()

    def _on_auto_refresh_change(self, event):
        if self.auto_refresh_job:
            self.root.after_cancel(self.auto_refresh_job)
            self.auto_refresh_job = None

        value = self.auto_refresh_var.get()
        if value == "Выкл":
            return

        intervals = {"30 сек": 30, "1 мин": 60, "2 мин": 120, "5 мин": 300, "10 мин": 600}
        seconds = intervals.get(value, 60)

        self._schedule_auto_refresh(seconds * 1000)

    def _schedule_auto_refresh(self, ms):
        def refresh():
            if self.auto_refresh_var.get() != "Выкл":
                self._check_all()
                self.auto_refresh_job = self.root.after(ms, refresh)

        self.auto_refresh_job = self.root.after(ms, refresh)

    def _show_history(self):
        if not self.data_manager:
            return
        HistoryDialog(self.root, self.data_manager.history)

    def _manage_categories(self):
        if not self.data_manager:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Управление категориями")
        dialog.geometry("350x400")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Категории:", style="Header.TLabel").pack(anchor=tk.W)

        listbox = tk.Listbox(frame, height=15)
        listbox.pack(fill=tk.BOTH, expand=True, pady=10)

        for cat in self.data_manager.categories:
            listbox.insert(tk.END, cat)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        def add_category():
            name = simpledialog.askstring("Новая категория", "Название:", parent=dialog)
            if name and name.strip():
                self.data_manager.add_category(name.strip())
                listbox.insert(tk.END, name.strip())
                self._update_filter_categories()

        def delete_category():
            selection = listbox.curselection()
            if selection:
                cat = listbox.get(selection[0])
                if messagebox.askyesno("Подтверждение", f"Удалить категорию '{cat}'?", parent=dialog):
                    self.data_manager.categories.remove(cat)
                    self.data_manager.save_categories()
                    listbox.delete(selection[0])
                    self._update_filter_categories()

        ttk.Button(btn_frame, text="Добавить", command=add_category).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=delete_category).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Закрыть", command=dialog.destroy).pack(side=tk.RIGHT)

    def _import_nodes(self):
        if not self.data_manager:
            messagebox.showwarning("Внимание", "Сначала выберите папку для хранения данных")
            return

        filepath = filedialog.askopenfilename(
            title="Импорт узлов",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        if filepath:
            try:
                count = self.data_manager.import_nodes(filepath)
                self._update_filter_categories()
                self._refresh_tree()
                messagebox.showinfo("Успех", f"Импортировано узлов: {count}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка импорта: {e}")

    def _export_nodes(self):
        if not self.data_manager:
            return

        filepath = filedialog.asksaveasfilename(
            title="Экспорт узлов",
            defaultextension=".json",
            filetypes=[("JSON файлы", "*.json")]
        )
        if filepath:
            try:
                self.data_manager.export_nodes(filepath)
                messagebox.showinfo("Успех", f"Узлы экспортированы в:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка экспорта: {e}")

    def _export_report(self, format_type):
        if not self.data_manager:
            return

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        default_name = f"network_report_{timestamp}"

        if format_type == 'html':
            filepath = filedialog.asksaveasfilename(
                title="Экспорт отчёта HTML",
                defaultextension=".html",
                initialfile=default_name,
                filetypes=[("HTML файлы", "*.html")]
            )
            if filepath:
                self._save_html_report(filepath)
        else:
            filepath = filedialog.asksaveasfilename(
                title="Экспорт отчёта TXT",
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("Текстовые файлы", "*.txt")]
            )
            if filepath:
                self._save_txt_report(filepath)

    def _save_html_report(self, filepath):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Network Monitor Report - {timestamp}</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .info {{ color: #666; margin-bottom: 20px; }}
        table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background: #4a90d9; color: white; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        .online {{ color: #2E7D32; font-weight: bold; }}
        .offline {{ color: #C62828; font-weight: bold; }}
        .high-latency {{ color: #F57C00; font-weight: bold; }}
        .critical {{ background: #FFEBEE !important; }}
        .stats {{ margin: 20px 0; padding: 15px; background: white; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>🖥️ Network Monitor Report</h1>
    <div class="info">Дата и время: {timestamp}</div>
"""

        total = len(self.data_manager.nodes)
        online = sum(1 for r in self.check_results.values() if r.get('status') == STATUS_OK)
        offline = sum(1 for r in self.check_results.values() if r.get('status') == STATUS_FAIL)

        html += f"""
    <div class="stats">
        <strong>Всего узлов:</strong> {total} | 
        <strong style="color:#2E7D32">Online:</strong> {online} | 
        <strong style="color:#C62828">Offline:</strong> {offline}
    </div>

    <table>
        <tr>
            <th>Приоритет</th>
            <th>Название</th>
            <th>IP</th>
            <th>Категория</th>
            <th>Статус</th>
            <th>Задержка</th>
            <th>Порты</th>
        </tr>
"""

        for node in self.data_manager.nodes:
            result = self.check_results.get(node['id'], {})
            priority = PRIORITIES.get(node.get('priority', 'normal'), {}).get('name', 'Обычный')

            status = result.get('status', '')
            if status == STATUS_OK:
                status_html = '<span class="online">✓ Online</span>'
            elif status == STATUS_FAIL:
                status_html = '<span class="offline">✗ Offline</span>'
            elif status == STATUS_HIGH_LATENCY:
                status_html = '<span class="high-latency">⚠ Высокий пинг</span>'
            else:
                status_html = '—'

            latency = result.get('ping', {}).get('latency')
            latency_text = f"{latency} ms" if latency else "—"

            ports_text = ", ".join(map(str, node.get('ports', []))) or "—"

            row_class = 'critical' if node.get('priority') == 'critical' and status == STATUS_FAIL else ''

            html += f"""
        <tr class="{row_class}">
            <td>{priority}</td>
            <td>{node.get('name', '')}</td>
            <td>{node.get('ip', '')}</td>
            <td>{node.get('category', '')}</td>
            <td>{status_html}</td>
            <td>{latency_text}</td>
            <td>{ports_text}</td>
        </tr>
"""

        html += """
    </table>
    <div class="info" style="margin-top:20px">Сгенерировано: Network Monitor</div>
</body>
</html>
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)

        messagebox.showinfo("Успех", f"Отчёт сохранён:\n{filepath}")

    def _save_txt_report(self, filepath):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        lines = [
            "=" * 70,
            "NETWORK MONITOR REPORT",
            f"Дата и время: {timestamp}",
            "=" * 70,
            ""
        ]

        total = len(self.data_manager.nodes)
        online = sum(1 for r in self.check_results.values() if r.get('status') == STATUS_OK)
        offline = sum(1 for r in self.check_results.values() if r.get('status') == STATUS_FAIL)

        lines.append(f"Всего узлов: {total} | Online: {online} | Offline: {offline}")
        lines.append("")
        lines.append("-" * 70)

        for node in self.data_manager.nodes:
            result = self.check_results.get(node['id'], {})
            priority = PRIORITIES.get(node.get('priority', 'normal'), {}).get('name', 'Обычный')

            status = result.get('status', '')
            if status == STATUS_OK:
                status_text = '[OK] Online'
            elif status == STATUS_FAIL:
                status_text = '[!!] OFFLINE'
            elif status == STATUS_HIGH_LATENCY:
                status_text = '[!] Высокий пинг'
            else:
                status_text = '[-] Не проверен'

            latency = result.get('ping', {}).get('latency')
            latency_text = f"{latency} ms" if latency else "-"

            lines.append(f"[{priority}] {node.get('name', '')}")
            lines.append(f"  IP: {node.get('ip', '')} | Категория: {node.get('category', '')}")
            lines.append(f"  Статус: {status_text} | Задержка: {latency_text}")
            if node.get('ports'):
                lines.append(f"  Порты: {', '.join(map(str, node.get('ports', [])))}")
            if node.get('comment'):
                lines.append(f"  Комментарий: {node.get('comment', '')}")
            lines.append("-" * 70)

        lines.append("")
        lines.append("Сгенерировано: Network Monitor")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        messagebox.showinfo("Успех", f"Отчёт сохранён:\n{filepath}")

    def _show_about(self):
        messagebox.showinfo(
            "О программе",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "Программа для мониторинга сетевой\n"
            "инфраструктуры и критичных узлов.\n\n"
            "Автор: Matrix Agent"
        )

    def _on_close(self):
        if self.auto_refresh_job:
            self.root.after_cancel(self.auto_refresh_job)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = NetworkMonitorApp()
    app.run()