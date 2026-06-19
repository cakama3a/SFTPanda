from __future__ import annotations
import sys
import os
import json
import paramiko
try:
    import paramiko.sftp_file
    import paramiko.common
    # Встановлюємо розмір запиту в 256КБ (безпечний ліміт для OpenSSH) для високої швидкості
    paramiko.sftp_file.SFTPFile._MAX_REQUEST_SIZE = 262144
    # Зберігаємо стабільний розмір вікна (2МБ) та обмежуємо розмір пакета до 256КБ
    paramiko.common.DEFAULT_WINDOW_SIZE = 2097152
    paramiko.common.DEFAULT_MAX_PACKET_SIZE = 262144
except Exception:
    pass
import subprocess
from datetime import datetime
import threading
import time
import keyring
import shlex
import tempfile
import stat
import zipfile
import secrets

APP_SERVICE_NAME = "SFTPanda"
APP_VERSION = "1.0.0"

from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFileIconProvider, QFormLayout, QGraphicsOpacityEffect, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar, QRadioButton, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QStyle, QStyledItemDelegate, QTabWidget, QTableView, QTextBrowser, QVBoxLayout, QWidget)
from PySide6.QtCore import (QAbstractTableModel, QEasingCurve, QFileInfo, QFileSystemWatcher, QModelIndex, QObject, QPoint, QPropertyAnimation, QSize, QThread, QTimer, QUrl, QVariantAnimation, Qt, Signal)
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QIcon, QKeySequence, QTextCursor)

# icons
try:
    import qtawesome as qta
except Exception:
    qta = None  # fallback to text icons if library is missing

# Клас для обгортки файлу з підтримкою обмеження швидкості передачі
class ThrottledFile:
    def __init__(self, file_obj, rate_limit_kbps=0):
        self.file_obj = file_obj
        # Переводимо КБ/с в байти/с. 0 або менше означає без ліміту.
        self.rate_limit = rate_limit_kbps * 1024 if rate_limit_kbps > 0 else 0
        self.start_time = time.time()
        self.transferred = 0

    def _throttle(self, length):
        if self.rate_limit <= 0:
            return
            
        self.transferred += length
        elapsed = time.time() - self.start_time
        
        # Очікувана швидкість на даний момент
        expected_speed = self.transferred / elapsed if elapsed > 0 else 0
        
        # Якщо ми передаємо дані занадто швидко, розраховуємо час очікування
        if expected_speed > self.rate_limit:
            wait_time = (self.transferred / self.rate_limit) - elapsed
            time.sleep(wait_time)

    def read(self, size):
        chunk = self.file_obj.read(size)
        if chunk:
            self._throttle(len(chunk))
        return chunk
        
    def write(self, chunk):
        result = self.file_obj.write(chunk)
        if result:
            self._throttle(result)
        return result

    # Це потрібно, щоб paramiko міг викликати інші методи файлу (напр. seek, tell)
    def __getattr__(self, attr):
        return getattr(self.file_obj, attr)

# Функція для отримання шляху до ресурсів (іконок, файлів тощо)
def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # fallback to current file directory
        base_path = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# ДОДАЙТЕ ЦЕЙ НОВИЙ КЛАС ПІСЛЯ ІМПОРТІВ

class StyledSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Створюємо наші власні кнопки
        self.up_button = QPushButton()
        self.down_button = QPushButton()
        
        # Встановлюємо для них іконки з qtawesome
        if qta:
            up_icon = qta.icon('fa5s.chevron-up', color='#dcddde')
            down_icon = qta.icon('fa5s.chevron-down', color='#dcddde')
            self.up_button.setIcon(up_icon)
            self.down_button.setIcon(down_icon)
        else:
            # Текстовий варіант, якщо qtawesome не встановлено
            self.up_button.setText("▲")
            self.down_button.setText("▼")

        # Прибираємо стандартні стрілки самого QSpinBox
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        # З'єднуємо натискання наших кнопок з вбудованими функціями QSpinBox
        self.up_button.clicked.connect(self.stepUp)
        self.down_button.clicked.connect(self.stepDown)

        # Додаємо кнопкам імена об'єктів для стилізації через QSS
        self.up_button.setObjectName("upButton")
        self.down_button.setObjectName("downButton")
        
        # Створюємо лейаут для розміщення кнопок всередині віджета
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 2, 0) # Відступ справа, щоб кнопки не прилипали
        layout.setSpacing(0)
        layout.addStretch() # Розтягуємо простір, щоб кнопки були справа

        # Лейаут для вертикального розміщення кнопок
        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(0, 2, 0, 2) # Вертикальні відступи
        button_layout.setSpacing(1) # Проміжок між кнопками
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)
        
        layout.addLayout(button_layout)

class StyledCheckBox(QCheckBox):
    """Кастомний чекбокс з покращеним стилем та гарантованою галочкою"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("StyledCheckBox")
    
    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF
        from PySide6.QtCore import QPointF
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Визначаємо розміри та положення квадратика чекбокса
        indicator_size = 18
        y_offset = (self.height() - indicator_size) // 2
        
        # Малюємо фон та рамку індикатора
        rect_color = QColor("#202225")
        border_color = QColor("#7289da") if self.isChecked() else QColor("#4f545c")
        
        if self.isChecked():
            rect_color = QColor("#7289da")
            
        painter.setPen(QPen(border_color, 2))
        painter.setBrush(QBrush(rect_color))
        painter.drawRoundedRect(2, y_offset, indicator_size, indicator_size, 4, 4)
        
        # Малюємо галочку, якщо вибрано
        if self.isChecked():
            painter.setPen(QPen(QColor(Qt.white), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            
            # Малюємо галочку за координатами відносно індикатора
            chk_x = 2
            chk_y = y_offset
            
            poly = QPolygonF([
                QPointF(chk_x + 5, chk_y + 9),
                QPointF(chk_x + 8, chk_y + 12),
                QPointF(chk_x + 13, chk_y + 5)
            ])
            painter.drawPolyline(poly)
            
        # Малюємо текст чекбокса праворуч від індикатора
        painter.setPen(QColor("#dcddde"))
        text_rect = self.rect()
        text_rect.setLeft(indicator_size + 12)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())
        
        painter.end()

class SFTPConnectionPool:
    def __init__(self):
        self.pool = {}  # Ключ: (hostname, port, username) -> список кортежів (ssh_client, sftp_client, last_used_time)
        self.lock = threading.Lock()

    def get_connection(self, connection_details):
        key = (connection_details.get('hostname'), connection_details.get('port', 22), connection_details.get('username'))
        to_close = []
        ssh_ret, sftp_ret = None, None
        
        with self.lock:
            if key in self.pool and self.pool[key]:
                while self.pool[key]:
                    ssh, sftp, last_used = self.pool[key].pop(0)
                    try:
                        # Перевіряємо працездатність з'єднання (це неблокуюча перевірка прапорця)
                        if ssh.get_transport() and ssh.get_transport().is_active():
                            ssh_ret, sftp_ret = ssh, sftp
                            break
                        else:
                            to_close.append((ssh, sftp))
                    except Exception:
                        to_close.append((ssh, sftp))
                        
        # Закриваємо неробочі з'єднання ПОЗА блокуванням
        for s, f in to_close:
            try: f.close()
            except Exception: pass
            try: s.close()
            except Exception: pass
            
        return ssh_ret, sftp_ret

    def release_connection(self, connection_details, ssh, sftp):
        if not ssh or not sftp:
            return
        
        # Швидка неблокуюча перевірка працездатності
        is_active = False
        try:
            if ssh.get_transport() and ssh.get_transport().is_active():
                is_active = True
        except Exception:
            pass
            
        if not is_active:
            # Закриваємо неробоче з'єднання поза локом
            try: sftp.close()
            except Exception: pass
            try: ssh.close()
            except Exception: pass
            return
            
        key = (connection_details.get('hostname'), connection_details.get('port', 22), connection_details.get('username'))
        close_needed = None
        
        with self.lock:
            if key not in self.pool:
                self.pool[key] = []
            
            # Утримуємо в пулі не більше 8 вільних з'єднань одночасно
            if len(self.pool[key]) < 8:
                self.pool[key].append((ssh, sftp, time.time()))
            else:
                close_needed = (ssh, sftp)
                
        # Закриваємо зайве з'єднання ПОЗА блокуванням
        if close_needed:
            s, f = close_needed
            try: f.close()
            except Exception: pass
            try: s.close()
            except Exception: pass

    def clear(self):
        to_close = []
        with self.lock:
            for key, conns in self.pool.items():
                for ssh, sftp, _ in conns:
                    to_close.append((ssh, sftp))
            self.pool.clear()
            
        for ssh, sftp in to_close:
            try: sftp.close()
            except Exception: pass
            try: ssh.close()
            except Exception: pass

sftp_connection_pool = SFTPConnectionPool()


class FileTransferThread(QThread):
    transfer_started = Signal(str, str, str, int, int) # Сигнал для оновлення назви файлу в UI
    progress_updated = Signal(str, str, int, int)
    transfer_complete = Signal(str, str, bool, str)

    def __init__(self, is_upload, source_path, target_path, connection_details, task_id, transfer_id, settings_manager, size=0, file_num=0, total_files=0, parent=None):
        super().__init__(parent)
        self.is_upload = is_upload
        self.source_path = source_path
        self.target_path = target_path
        self.connection_details = connection_details
        self.task_id = task_id
        self.transfer_id = transfer_id
        self.settings_manager = settings_manager
        self.file_size = size
        self.file_num = file_num
        self.total_files = total_files
        self.canceled = False
        self.ssh = None
        self.sftp = None

    def run(self):
        try:
            try:
                # Пробуємо отримати вже підключене з'єднання з пулу
                self.ssh, self.sftp = sftp_connection_pool.get_connection(self.connection_details)
                
                if not (self.ssh and self.sftp):
                    self.ssh = paramiko.SSHClient()
                    self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    connect_params = self.connection_details.copy()
                    connect_params.pop('start_directory', None)
                    connect_params.pop('name', None)
                    connect_params['timeout'] = 20  # 20 секунд на підключення

                    if connect_params.get('key_filename') == '':
                        connect_params.pop('key_filename', None)

                    self.ssh.connect(**connect_params)
                    self.sftp = self.ssh.open_sftp()
                
                # Встановлюємо таймаут сокета на рівні SFTP-каналу для запобігання зависання
                if self.sftp and self.sftp.get_channel():
                    self.sftp.get_channel().settimeout(30.0)
            except Exception as e:
                if self.canceled:
                    self.transfer_complete.emit(self.task_id, self.transfer_id, False, lang["CANCELED"])
                else:
                    error_msg = f"Connection error: {str(e)}"
                    self.transfer_complete.emit(self.task_id, self.transfer_id, False, error_msg)
                return

            if self.file_size == 0:
                try:
                    if self.is_upload:
                        self.file_size = os.path.getsize(self.source_path)
                    else:
                        self.file_size = self.sftp.stat(self.source_path).st_size
                except Exception:
                    self.file_size = 0

            def progress_callback(transferred, total):
                if self.canceled:
                    raise InterruptedError(lang["TRANSFER_CANCELED_BY_USER"])
                self.progress_updated.emit(self.task_id, self.transfer_id, transferred, total)

            if self.canceled:
                raise InterruptedError(lang["TRANSFER_CANCELED_BEFORE_START"])
            
            filename = os.path.basename(self.source_path)
            self.transfer_started.emit(self.task_id, self.transfer_id, filename, self.file_num, self.total_files)
                
            rate_limit_kbps = 0
            if self.settings_manager:
                speed_settings = self.settings_manager.get_speed_limit_settings()
                if speed_settings.get("enabled", False):
                    if self.is_upload:
                        rate_limit_kbps = speed_settings.get("upload_kbps", 0)
                    else:
                        rate_limit_kbps = speed_settings.get("download_kbps", 0)

            if self.is_upload:
                if rate_limit_kbps > 0:
                    with open(self.source_path, 'rb') as local_file:
                        throttled_file = ThrottledFile(local_file, rate_limit_kbps)
                        self.sftp.putfo(throttled_file, self.target_path, callback=progress_callback)
                else:
                    self.sftp.put(self.source_path, self.target_path, callback=progress_callback)
                
                try:
                    local_stat = os.stat(self.source_path)
                    mtime = local_stat.st_mtime
                    self.sftp.utime(self.target_path, (local_stat.st_atime, mtime))
                except Exception:
                    try:
                        command = f"touch -m -d @{int(mtime)} {shlex.quote(self.target_path)}"
                        stdin, stdout, stderr = self.ssh.exec_command(command)
                        stdout.channel.recv_exit_status()
                    except Exception:
                        pass
            else:
                local_dir = os.path.dirname(self.target_path)
                os.makedirs(local_dir, exist_ok=True)
                attr = self.sftp.stat(self.source_path)
                if rate_limit_kbps > 0:
                    with open(self.target_path, 'wb') as local_file:
                        throttled_file = ThrottledFile(local_file, rate_limit_kbps)
                        self.sftp.getfo(self.source_path, throttled_file, callback=progress_callback)
                else:
                    self.sftp.get(self.source_path, self.target_path, callback=progress_callback)
                
                os.utime(self.target_path, (attr.st_atime, attr.st_mtime))
            
            self.transfer_complete.emit(self.task_id, self.transfer_id, True, lang["COMPLETE"])

        except InterruptedError:
            self.transfer_complete.emit(self.task_id, self.transfer_id, False, lang["CANCELED"])
        except Exception as e:
            msg = lang["CANCELED"] if self.canceled else str(e)
            self.transfer_complete.emit(self.task_id, self.transfer_id, False, msg)
        finally:
            ssh_to_release = self.ssh
            sftp_to_release = self.sftp
            self.ssh = None
            self.sftp = None
            
            if ssh_to_release and sftp_to_release:
                sftp_connection_pool.release_connection(self.connection_details, ssh_to_release, sftp_to_release)
            else:
                if sftp_to_release:
                    try: sftp_to_release.close()
                    except Exception: pass
                if ssh_to_release:
                    try: ssh_to_release.close()
                    except Exception: pass

    def cancel(self):
        self.canceled = True
        if self.ssh and self.ssh.get_transport():
            try:
                self.ssh.get_transport().close()
            except Exception:
                pass

class OptimizedDirectoryScannerThread(QThread):
    """
    Оптимізований сканер, що використовує одну SSH команду 'find' для
    швидкого рекурсивного отримання списку файлів, їх розмірів та часу модифікації.
    """
    scan_complete = Signal(list)
    error = Signal(str)

    def __init__(self, ssh_client, remote_base_dir, local_base_dir, files_to_scan):
        super().__init__()
        self.ssh_client = ssh_client
        self.remote_base_dir = remote_base_dir
        self.local_base_dir = local_base_dir
        self.files_to_scan = files_to_scan
        self.found_files = []
        self.canceled = False

    def run(self):
        if not self.ssh_client or not self.ssh_client.get_transport() or not self.ssh_client.get_transport().is_active():
            self.error.emit(lang["SSH_CLIENT_NOT_CONNECTED_FOR_SCANNING"])
            return

        try:
            quoted_items = " ".join([shlex.quote(item) for item in self.files_to_scan])
            
            # --- ПОЧАТОК ЗМІН ---
            # Оновлюємо команду: додаємо %T@ для отримання часу модифікації (mtime) як timestamp
            command = (
                f'cd {shlex.quote(self.remote_base_dir)} && '
                f'find {quoted_items} -type f -printf "%p\\t%s\\t%T@\\n"'
            )
            # --- КІНЕЦЬ ЗМІН ---

            stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=300)

            for line in stdout:
                if self.canceled: break
                
                line = line.strip()
                if not line: continue

                # --- ПОЧАТОК ЗМІН ---
                # Тепер розбираємо рядок на 3 частини
                parts = line.split('\t', 2)
                if len(parts) == 3:
                    relative_path, size_str, mtime_str = parts
                    # --- КІНЕЦЬ ЗМІН ---
                    
                    remote_item_path = f"{self.remote_base_dir}/{relative_path}".replace("//", "/")
                    local_item_path = os.path.join(self.local_base_dir, relative_path.replace('/', os.path.sep))
                    
                    try:
                        file_size = int(size_str)
                        # --- ПОЧАТОК ЗМІН ---
                        mtime = float(mtime_str)
                        # --- КІНЕЦЬ ЗМІН ---
                        
                        local_item_dir = os.path.dirname(local_item_path)
                        os.makedirs(local_item_dir, exist_ok=True)
                        
                        # --- ПОЧАТОК ЗМІН ---
                        # Додаємо кортеж з 4 елементів
                        self.found_files.append((remote_item_path, local_item_path, mtime, file_size))
                        # --- КІНЕЦЬ ЗМІН ---
                    except (ValueError, OSError) as e:
                        print(f"Помилка обробки рядка '{line}': {e}")

            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error_output = stderr.read().decode('utf-8', errors='ignore').strip()
                if error_output:
                    self.error.emit(f"Помилка сканування на сервері: {error_output}")
            
            if not self.canceled:
                self.scan_complete.emit(self.found_files)

        except Exception as e:
            if not self.canceled:
                self.error.emit(f"Критична помилка під час оптимізованого сканування: {e}")

    def cancel(self):
        self.canceled = True

class OptimizedDirectoryUploadScannerThread(QThread):
    """
    Оптимізований сканер, що лише збирає інформацію про локальні файли 
    та директорії без виконання мережевих запитів.
    """
    scan_complete = Signal(list, list) # file_list, dirs_to_create
    error = Signal(str, str)
    progress_updated = Signal(int, int)

    def __init__(self, local_paths_to_scan, remote_base_path, parent=None):
        super().__init__(parent)
        self.local_paths = local_paths_to_scan
        self.remote_base_path = remote_base_path
        self.found_files = []
        self.dirs_to_create = set()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            total_files = 0
            for local_path in self.local_paths:
                if os.path.isfile(local_path):
                    total_files += 1
                elif os.path.isdir(local_path):
                    for _, _, files in os.walk(local_path):
                        if self._cancelled: break
                        total_files += len(files)
            
            self.progress_updated.emit(0, total_files)

            processed_files = 0
            for local_path in self.local_paths:
                if self._cancelled: break
                
                if os.path.isfile(local_path):
                    filename = os.path.basename(local_path)
                    remote_path = (self.remote_base_path + "/" + filename).replace("//", "/")
                    try:
                        stat_res = os.stat(local_path)
                        self.found_files.append((local_path, remote_path, stat_res.st_mtime, stat_res.st_size))
                    except OSError:
                        pass # Пропускаємо файли, до яких немає доступу
                    processed_files += 1
                    self.progress_updated.emit(processed_files, total_files)

                elif os.path.isdir(local_path):
                    for root, _, files in os.walk(local_path):
                        if self._cancelled: break
                        
                        rel_path = os.path.relpath(root, os.path.dirname(local_path))
                        
                        # Додаємо відносний шлях директорії до списку на створення
                        self.dirs_to_create.add(rel_path.replace(os.path.sep, '/'))

                        for name in files:
                            if self._cancelled: break
                            
                            local_file_path = os.path.join(root, name)
                            remote_file_path = (self.remote_base_path + "/" + rel_path.replace(os.path.sep, '/') + "/" + name).replace("//", "/")
                            try:
                                stat_res = os.stat(local_file_path)
                                self.found_files.append((local_file_path, remote_file_path, stat_res.st_mtime, stat_res.st_size))
                            except OSError:
                                continue
                            processed_files += 1
                            if processed_files % 20 == 0:
                                self.progress_updated.emit(processed_files, total_files)
            
            if not self._cancelled:
                self.progress_updated.emit(total_files, total_files)
                self.scan_complete.emit(self.found_files, sorted(list(self.dirs_to_create)))

        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(self.local_paths), lang["ERROR_SCANNING_DIRECTORY_SIMPLE"].format(e=e))

# ДОДАЙТЕ ЦЕЙ НОВИЙ КЛАС
class DirectoryCreationThread(QThread):
    """
    Створює дерево каталогів на віддаленому сервері однією командою 'mkdir -p'.
    """
    creation_complete = Signal(list) # Повертає список файлів для подальшої обробки
    error = Signal(str)

    def __init__(self, ssh_client, remote_base_path, dirs_to_create, file_list, parent=None):
        super().__init__(parent)
        self.ssh_client = ssh_client
        self.remote_base_path = remote_base_path
        self.dirs_to_create = dirs_to_create
        self.file_list = file_list

    def run(self):
        if not self.ssh_client or not self.ssh_client.get_transport() or not self.ssh_client.get_transport().is_active():
            self.error.emit(lang["SSH_CLIENT_NOT_CONNECTED"])
            return
        
        try:
            # Фільтруємо '.' (поточна директорія), оскільки її не треба створювати
            dirs_to_create = [d for d in self.dirs_to_create if d != '.']
            if not dirs_to_create:
                self.creation_complete.emit(self.file_list)
                return

            # Екрануємо кожен шлях та об'єднуємо в один рядок
            quoted_dirs = " ".join([shlex.quote(d) for d in dirs_to_create])
            
            # Формуємо одну команду для створення всіх директорій
            command = f"cd {shlex.quote(self.remote_base_path)} && mkdir -p {quoted_dirs}"
            
            stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=300)
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                error_output = stderr.read().decode('utf-8', errors='ignore').strip()
                self.error.emit(lang["ERROR_CREATING_SERVER_DIRECTORIES"].format(error_output=error_output))
            else:
                self.creation_complete.emit(self.file_list)

        except Exception as e:
            self.error.emit(lang["CRITICAL_ERROR_CREATING_DIRECTORIES"].format(e=e))

class ConflictResolutionThread(QThread):
    resolution_complete = Signal(list, list, bool)
    error = Signal(str)

    def __init__(self, sftp_client_details, files_to_check, is_upload, remote_base_path=None, local_base_path=None):
        super().__init__()
        self.sftp_details = sftp_client_details
        self.files_to_check = files_to_check
        self.is_upload = is_upload
        self.remote_base_path = remote_base_path
        self.local_base_path = local_base_path
        self._is_cancelled = False

    def cancel(self):
        """Signals the thread to stop its operation."""
        self._is_cancelled = True

    def run(self):
        non_conflicts = []
        conflicts = []

        try:
            if self._is_cancelled:
                return

            if self.is_upload:
                if not self.files_to_check:
                    self.resolution_complete.emit([], [], self.is_upload)
                    return

                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                connect_params = self.sftp_details.copy()
                connect_params.pop('start_directory', None)
                connect_params.pop('name', None)

                # ВИПРАВЛЕННЯ: Видаляємо порожній key_filename
                if connect_params.get('key_filename') == '':
                    connect_params.pop('key_filename', None)

                ssh.connect(**connect_params)

                target_dirs = {os.path.dirname(f[1]).replace(os.path.sep, '/') for f in self.files_to_check}
                remote_files_meta = {}
                if target_dirs:
                    quoted_dirs = " ".join([shlex.quote(d) for d in target_dirs])
                    command = f'find {quoted_dirs} -maxdepth 1 -type f -printf "%p\\t%s\\t%T@\\n"'
                    stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
                    for line in stdout:
                        parts = line.strip().split('\t', 2)
                        if len(parts) == 3:
                            full_path, size_str, mtime_str = parts
                            try:
                                remote_files_meta[full_path] = {'size': int(size_str), 'mtime': float(mtime_str)}
                            except ValueError:
                                continue
                
                for source_path, target_path, source_mtime, source_size in self.files_to_check:
                    if self._is_cancelled:
                        break
                    if target_path in remote_files_meta:
                        dest_meta = remote_files_meta[target_path]
                        conflicts.append({'source_path': source_path, 'target_path': target_path,
                                          'source_meta': {'mtime': source_mtime, 'size': source_size},
                                          'dest_meta': {'mtime': dest_meta['mtime'], 'size': dest_meta['size']}})
                    else:
                        non_conflicts.append((source_path, target_path, source_mtime, source_size))
                if ssh:
                    ssh.close()
            
            else:
                # --- [НОВА МАКСИМАЛЬНО ОПТИМІЗОВАНА ЛОГІКА ДЛЯ СКАЧУВАННЯ] ---
                existing_local_files = {}
                if self.local_base_path and os.path.isdir(self.local_base_path):
                    for root, _, filenames in os.walk(self.local_base_path):
                        for filename in filenames:
                            full_path = os.path.join(root, filename)
                            try:
                                existing_local_files[full_path] = os.stat(full_path)
                            except OSError:
                                continue
                
                for source_path, target_path, source_mtime, source_size in self.files_to_check:
                    if self._is_cancelled:
                        break
                    if target_path in existing_local_files:
                        dest_stat = existing_local_files[target_path]
                        conflicts.append({'source_path': source_path, 'target_path': target_path,
                                          'source_meta': {'mtime': source_mtime, 'size': source_size},
                                          'dest_meta': {'mtime': dest_stat.st_mtime, 'size': dest_stat.st_size}})
                    else:
                        non_conflicts.append((source_path, target_path, source_mtime, source_size))

            if not self._is_cancelled:
                self.resolution_complete.emit(non_conflicts, conflicts, self.is_upload)

        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(lang["ERROR_CHECKING_CONFLICTS"].format(e=str(e)))


# Потік для синхронізації файлів (сканування локальної та віддаленої папки)
class SyncScannerThread(QThread):
    scan_complete = Signal(list)
    error = Signal(str)

    def __init__(self, sftp_details, remote_dir, local_dir, ignored_patterns):
        super().__init__()
        self.sftp_details = sftp_details
        self.remote_dir = remote_dir
        self.local_dir = local_dir
        self.ignored_patterns = ignored_patterns
        self.canceled = False

    def run(self):
        import fnmatch
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            connect_params = self.sftp_details.copy()
            connect_params.pop('start_directory', None)
            connect_params.pop('name', None)
            if connect_params.get('key_filename') == '':
                connect_params.pop('key_filename', None)
            
            ssh.connect(**connect_params)
            sftp = ssh.open_sftp()
        except Exception as e:
            self.error.emit(f"Connection error: {e}")
            return
            
        def should_ignore(path, ignored_patterns):
            normalized = path.replace("\\", "/")
            parts = normalized.split("/")
            for part in parts:
                if not part:
                    continue
                for pattern in ignored_patterns:
                    if fnmatch.fnmatch(part.lower(), pattern.lower()) or pattern.lower() in part.lower():
                        return True
            return False

        # Scan remote recursively
        remote_files = {}
        def scan_remote(remote_path, rel_prefix=""):
            if self.canceled:
                return
            if rel_prefix and should_ignore(rel_prefix, self.ignored_patterns):
                return
            
            try:
                for attr in sftp.listdir_attr(remote_path):
                    if self.canceled:
                        break
                    name = attr.filename
                    if name in ('.', '..'):
                        continue
                    rel_item = f"{rel_prefix}/{name}" if rel_prefix else name
                    if should_ignore(name, self.ignored_patterns) or should_ignore(rel_item, self.ignored_patterns):
                        continue
                    
                    full_item_path = f"{remote_path}/{name}".replace("//", "/")
                    if stat.S_ISDIR(attr.st_mode):
                        scan_remote(full_item_path, rel_item)
                    else:
                        remote_files[rel_item] = {
                            'path': full_item_path,
                            'mtime': attr.st_mtime,
                            'size': attr.st_size
                        }
            except Exception as e:
                print(f"Error scanning remote dir {remote_path}: {e}")

        scan_remote(self.remote_dir)
        
        if self.canceled:
            try: sftp.close()
            except: pass
            try: ssh.close()
            except: pass
            return

        # Scan local recursively
        local_files = {}
        for root, dirs, files in os.walk(self.local_dir):
            if self.canceled:
                break
            
            dirs[:] = [d for d in dirs if not should_ignore(d, self.ignored_patterns) and not should_ignore(os.path.join(root, d), self.ignored_patterns)]
            
            for f in files:
                if self.canceled:
                    break
                if should_ignore(f, self.ignored_patterns):
                    continue
                
                full_local_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_local_path, self.local_dir).replace('\\', '/')
                if should_ignore(rel_path, self.ignored_patterns):
                    continue
                
                try:
                    st = os.stat(full_local_path)
                    local_files[rel_path] = {
                        'path': full_local_path,
                        'mtime': st.st_mtime,
                        'size': st.st_size
                    }
                except OSError:
                    pass
        try: sftp.close()
        except: pass
        try: ssh.close()
        except: pass

        if self.canceled:
            return

        diff_items = []
        all_rel_paths = sorted(list(set(local_files.keys()) | set(remote_files.keys())))
        for rel_path in all_rel_paths:
            loc = local_files.get(rel_path)
            rem = remote_files.get(rel_path)
            
            if loc and not rem:
                diff_items.append({
                    'rel_path': rel_path,
                    'status': lang.get("SYNC_STATUS_LOCAL_ONLY", "Local Only"),
                    'action': 'upload',
                    'local_path': loc['path'],
                    'remote_path': f"{self.remote_dir}/{rel_path}".replace("//", "/"),
                    'mtime': loc['mtime'],
                    'size': loc['size']
                })
            elif rem and not loc:
                diff_items.append({
                    'rel_path': rel_path,
                    'status': lang.get("SYNC_STATUS_REMOTE_ONLY", "Remote Only"),
                    'action': 'download',
                    'local_path': os.path.join(self.local_dir, rel_path.replace('/', os.path.sep)),
                    'remote_path': rem['path'],
                    'mtime': rem['mtime'],
                    'size': rem['size']
                })
            elif loc and rem:
                mtime_diff = abs(loc['mtime'] - rem['mtime'])
                size_diff = loc['size'] != rem['size']
                
                if mtime_diff > 1.5 or size_diff:
                    if loc['mtime'] > rem['mtime']:
                        status = lang.get("SYNC_STATUS_LOCAL_NEWER", "Local Newer")
                        action = 'upload'
                        mtime = loc['mtime']
                        size = loc['size']
                    else:
                        status = lang.get("SYNC_STATUS_REMOTE_NEWER", "Remote Newer")
                        action = 'download'
                        mtime = rem['mtime']
                        size = rem['size']
                    
                    diff_items.append({
                        'rel_path': rel_path,
                        'status': status,
                        'action': action,
                        'local_path': loc['path'],
                        'remote_path': rem['path'],
                        'mtime': mtime,
                        'size': size
                    })

        self.scan_complete.emit(diff_items)

class BaseDialog(QDialog):
    def __init__(self, parent=None, window_title="Діалог"):
        super().__init__(parent); self.setWindowTitle(window_title); self.setMinimumWidth(420)
        self.move(-10000, -10000); self.setWindowOpacity(0.0)
        self.main_layout = QVBoxLayout(self); self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)
        self.content_container = QWidget(); self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(15, 15, 15, 20); self.content_layout.setSpacing(10)
        self.footer = QWidget(); self.footer.setObjectName("DialogFooter"); self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(10, 10, 10, 10); self.footer_layout.setSpacing(10)
        self.main_layout.addWidget(self.content_container); self.main_layout.addWidget(self.footer); self.setModal(True)

    def exec(self):
        self.adjustSize()
        if self.parent(): center_point = self.parent().geometry().center()
        else: center_point = QApplication.primaryScreen().geometry().center() if QApplication.instance() else QPoint(0,0)
        self.move(center_point - self.rect().center())
        self.anim = QPropertyAnimation(self, b"windowOpacity"); self.anim.setDuration(150)
        self.anim.setStartValue(0.0); self.anim.setEndValue(1.0); self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        QTimer.singleShot(0, self.anim.start)
        return super().exec()

    def add_title(self, text, icon_name=None, icon_color="#ffffff"):
        title_layout = QHBoxLayout(); title_layout.setSpacing(10)
        if qta and icon_name:
            icon_label = QLabel(); icon = qta.icon(icon_name, color=icon_color); icon_label.setPixmap(icon.pixmap(QSize(22, 22))); title_layout.addWidget(icon_label)
        title = QLabel(text); title.setObjectName("DialogTitle"); title_layout.addWidget(title); title_layout.addStretch()
        self.content_layout.insertLayout(0, title_layout)

    def add_message(self, text, is_warning=False):
        message_label = QLabel(text); message_label.setWordWrap(True); message_label.setObjectName("DialogMessage")
        if is_warning: message_label.setStyleSheet("color: #faa61a; font-size: 12px;")
        self.content_layout.addWidget(message_label)
        
    def add_button(self, text, is_primary=False, is_danger=False, on_click=None, is_default=False):
        button = QPushButton(text)
        if is_primary: button.setObjectName("PrimaryButton")
        if is_danger: button.setStyleSheet("background-color: #f04747;")
        if on_click: button.clicked.connect(on_click)
        
        # --- ДОДАНО: Встановлюємо кнопку як стандартну для натискання Enter ---
        if is_default:
            button.setDefault(True)
        
        self.footer_layout.addWidget(button)
        return button

import urllib.request

class VersionCheckerThread(QThread):
    check_finished = Signal(bool, str, str) # success, online_version, update_url
    
    def run(self):
        try:
            url = "https://raw.githubusercontent.com/cakama3a/SFTPanda/main/version.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'SFTPanda-Updater'})
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    online_version = data.get("version", "1.0.0")
                    update_url = data.get("url", "https://github.com/cakama3a/SFTPanda")
                    self.check_finished.emit(True, online_version, update_url)
                else:
                    self.check_finished.emit(False, "", "")
        except Exception:
            self.check_finished.emit(False, "", "")

class AboutDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent, lang.get("ABOUT_DIALOG_TITLE", "About SFTPanda"))
        self.add_title("SFTPanda", icon_name="fa6s.circle-info", icon_color="#7289da")
        
        # Details container
        details_layout = QVBoxLayout()
        details_layout.setSpacing(8)
        
        author_label = QLabel(f"<b>{lang.get('ABOUT_AUTHOR', 'Author:')}</b> Джон Панч (John Punch)")
        author_label.setStyleSheet("color: #dcddde; font-size: 13px;")
        details_layout.addWidget(author_label)
        
        version_label = QLabel(f"<b>{lang.get('ABOUT_VERSION', 'Version:')}</b> {APP_VERSION}")
        version_label.setStyleSheet("color: #dcddde; font-size: 13px;")
        details_layout.addWidget(version_label)
        
        description = QLabel(lang.get("ABOUT_DESCRIPTION", "SFTP/FTP Client with modern dark theme and adaptive multi-connection transfer capabilities."))
        description.setStyleSheet("color: #b9bbbe; font-size: 12px;")
        description.setWordWrap(True)
        details_layout.addWidget(description)
        
        # Update status
        self.status_label = QLabel(lang.get("ABOUT_CHECKING_UPDATES", "Checking for updates..."))
        self.status_label.setStyleSheet("color: #72767d; font-size: 12px; margin-top: 10px;")
        details_layout.addWidget(self.status_label)
        
        self.content_layout.addLayout(details_layout)
        
        # Add Close button
        self.close_btn = self.add_button(lang.get("CLOSE", "Close"), on_click=self.accept, is_default=True)
        
        # Start update check
        self.checker = VersionCheckerThread(self)
        self.checker.check_finished.connect(self.on_check_finished)
        self.checker.start()
        
    def on_check_finished(self, success, online_version, update_url):
        if not success:
            self.status_label.setText(lang.get("ABOUT_UPDATE_CHECK_FAILED", "Failed to check for updates."))
            self.status_label.setStyleSheet("color: #f04747; font-size: 12px; margin-top: 10px;")
            return
            
        try:
            local_parts = [int(x) for x in APP_VERSION.split(".")]
            online_parts = [int(x) for x in online_version.split(".")]
            has_update = online_parts > local_parts
        except Exception:
            has_update = online_version != APP_VERSION
            
        if has_update:
            self.status_label.setText(lang.get("ABOUT_UPDATE_AVAILABLE", "New version {version} is available!").format(version=online_version))
            self.status_label.setStyleSheet("color: #43b581; font-weight: bold; font-size: 12px; margin-top: 10px;")
            
            from PySide6.QtGui import QDesktopServices
            # Add a download/update button in the footer next to the close button
            self.download_btn = QPushButton(lang.get("ABOUT_DOWNLOAD_UPDATE", "Download"))
            self.download_btn.setObjectName("PrimaryButton")
            self.download_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(update_url)))
            self.footer_layout.insertWidget(0, self.download_btn)
        else:
            self.status_label.setText(lang.get("ABOUT_UP_TO_DATE", "SFTPanda is up to date."))
            self.status_label.setStyleSheet("color: #43b581; font-size: 12px; margin-top: 10px;")

class SyncDialog(BaseDialog):
    def __init__(self, parent, sftp_client, remote_dir, local_dir, settings_manager):
        super().__init__(parent, lang.get("SYNC_DIALOG_TITLE", "Folder Synchronization"))
        from PySide6.QtWidgets import QTableWidget, QFrame
        self.sftp_client = sftp_client
        self.remote_dir = remote_dir
        self.local_dir = local_dir
        self.settings_manager = settings_manager
        
        self.diff_items = []
        
        # 1. Info Box containing local and remote paths (styled Discord-like card)
        paths_widget = QWidget()
        paths_widget.setStyleSheet("""
            QWidget {
                background-color: #2f3136;
                border-radius: 6px;
                padding: 10px;
            }
            QLabel {
                background: transparent;
            }
        """)
        paths_layout = QVBoxLayout(paths_widget)
        paths_layout.setSpacing(6)
        
        # Local Folder Row
        local_header_layout = QHBoxLayout()
        local_header_layout.setSpacing(6)
        if qta:
            local_icon = QLabel()
            local_icon.setPixmap(qta.icon("fa5s.folder", color="#7289da").pixmap(16, 16))
            local_header_layout.addWidget(local_icon)
        local_label = QLabel(f"<b>{lang.get('SYNC_LOCAL_PATH', 'Local Folder:')}</b>")
        local_label.setStyleSheet("color: #7289da; font-size: 12px;")
        local_header_layout.addWidget(local_label)
        local_header_layout.addStretch()
        paths_layout.addLayout(local_header_layout)
        
        local_path_val = QLabel(local_dir)
        local_path_val.setStyleSheet("color: #dcddde; padding-left: 22px; font-family: Consolas, monospace;")
        local_path_val.setWordWrap(True)
        paths_layout.addWidget(local_path_val)
        
        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #4f545c; max-height: 1px; margin-top: 4px; margin-bottom: 4px;")
        paths_layout.addWidget(line)
        
        # Remote Folder Row
        remote_header_layout = QHBoxLayout()
        remote_header_layout.setSpacing(6)
        if qta:
            remote_icon = QLabel()
            remote_icon.setPixmap(qta.icon("fa5s.server", color="#43b581").pixmap(16, 16))
            remote_header_layout.addWidget(remote_icon)
        remote_label = QLabel(f"<b>{lang.get('SYNC_REMOTE_PATH', 'Remote Folder:')}</b>")
        remote_label.setStyleSheet("color: #43b581; font-size: 12px;")
        remote_header_layout.addWidget(remote_label)
        remote_header_layout.addStretch()
        paths_layout.addLayout(remote_header_layout)
        
        remote_path_val = QLabel(remote_dir)
        remote_path_val.setStyleSheet("color: #dcddde; padding-left: 22px; font-family: Consolas, monospace;")
        remote_path_val.setWordWrap(True)
        paths_layout.addWidget(remote_path_val)
        
        self.content_layout.addWidget(paths_widget)
        
        # 2. Status Label & Progress Bar
        self.status_label = QLabel(lang.get("SYNC_STATUS_SCANNING", "Scanning directories, please wait..."))
        self.status_label.setStyleSheet("color: #b9bbbe; font-size: 13px; margin-top: 10px;")
        self.content_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #202225;
                border-radius: 5px;
                text-align: center;
                background-color: #202225;
                height: 10px;
            }
            QProgressBar::chunk {
                background-color: #7289da;
                border-radius: 3px;
            }
        """)
        self.content_layout.addWidget(self.progress_bar)
        
        # 3. Table and controls
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            lang.get("SYNC_COL_PATH", "Path"),
            lang.get("SYNC_COL_STATUS", "Status"),
            lang.get("SYNC_COL_ACTION", "Action"),
            lang.get("SYNC_COL_SIZE", "Size")
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.table.hide()
        self.content_layout.addWidget(self.table)
        
        self.controls_widget = QWidget()
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        self.select_all_btn = QPushButton(lang.get("SYNC_SELECT_ALL", "Select All"))
        self.deselect_all_btn = QPushButton(lang.get("SYNC_DESELECT_ALL", "Deselect All"))
        self.select_all_btn.setStyleSheet("padding: 5px 10px; font-size: 11px;")
        self.deselect_all_btn.setStyleSheet("padding: 5px 10px; font-size: 11px;")
        self.select_all_btn.clicked.connect(self.select_all_items)
        self.deselect_all_btn.clicked.connect(self.deselect_all_items)
        
        controls_layout.addWidget(self.select_all_btn)
        controls_layout.addWidget(self.deselect_all_btn)
        controls_layout.addStretch()
        
        self.content_layout.addWidget(self.controls_widget)
        self.controls_widget.hide()
        
        # 4. Buttons in the BaseDialog footer
        self.ok_button = self.add_button(lang.get("SYNC_START_BUTTON", "Sync"), is_primary=True, on_click=self.accept, is_default=True)
        self.ok_button.setEnabled(False)
        
        self.cancel_button = self.add_button(lang.get("CANCEL", "Cancel"), on_click=self.reject)
        
        ignored_patterns = settings_manager.get_sync_ignored_patterns()
        
        self.scanner = SyncScannerThread(sftp_client.connection_details, remote_dir, local_dir, ignored_patterns)
        self.scanner.scan_complete.connect(self.on_scan_complete)
        self.scanner.error.connect(self.on_scan_error)
        self.scanner.finished.connect(self.scanner.deleteLater)
        self.scanner.start()

    def on_scan_complete(self, diff_items):
        from PySide6.QtWidgets import QTableWidgetItem
        self.diff_items = diff_items
        self.progress_bar.hide()
        
        if not diff_items:
            self.status_label.setText(lang.get("SYNC_NO_CHANGES", "No changes detected. Folders are synchronized."))
            self.ok_button.setEnabled(False)
            
            # Recenter and shrink the dialog beautifully
            self.adjustSize()
            if self.parent():
                center_point = self.parent().geometry().center()
            else:
                center_point = QApplication.primaryScreen().geometry().center() if QApplication.instance() else QPoint(0,0)
            self.move(center_point - self.rect().center())
            return
        
        self.status_label.setText(lang.get("SYNC_CHANGES_DETECTED", "The following files differ. Select the items to synchronize:"))
        self.table.show()
        self.controls_widget.show()
        self.ok_button.setEnabled(True)
        
        self.table.setRowCount(len(diff_items))
        for row, item in enumerate(diff_items):
            path_item = QTableWidgetItem(item['rel_path'])
            path_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            path_item.setCheckState(Qt.Checked)
            self.table.setItem(row, 0, path_item)
            
            self.table.setItem(row, 1, QTableWidgetItem(item['status']))
            
            if item['action'] == 'upload':
                action_str = lang.get("SYNC_ACTION_UPLOAD", "Upload ➜")
            else:
                action_str = lang.get("SYNC_ACTION_DOWNLOAD", "➜ Download")
            
            self.table.setItem(row, 2, QTableWidgetItem(action_str))
            
            size_str = self.format_size(item['size'])
            self.table.setItem(row, 3, QTableWidgetItem(size_str))
            
            # Resize and center on the parent window for selection view
            self.resize(750, 500)
            if self.parent():
                center_point = self.parent().geometry().center()
            else:
                center_point = QApplication.primaryScreen().geometry().center() if QApplication.instance() else QPoint(0,0)
            self.move(center_point - self.rect().center())
            
    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
        
    def select_all_items(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
                
    def deselect_all_items(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
                
    def on_scan_error(self, err_msg):
        self.progress_bar.hide()
        self.status_label.setText(f"<span style='color: #f04747;'>{err_msg}</span>")
        QMessageBox.warning(self, lang.get("ERROR", "Error"), err_msg)
        
    def get_selected_transfers(self):
        uploads = []
        downloads = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                diff_item = self.diff_items[row]
                if diff_item['action'] == 'upload':
                    uploads.append((diff_item['local_path'], diff_item['remote_path'], diff_item['mtime'], diff_item['size']))
                else:
                    downloads.append((diff_item['remote_path'], diff_item['local_path'], diff_item['mtime'], diff_item['size']))
        return uploads, downloads

    def show_table_context_menu(self, position):
        row = self.table.rowAt(position.y())
        if row == -1:
            return
        
        menu = QMenu(self)
        ignore_action = QAction(lang.get("SYNC_ADD_TO_IGNORE", "Add to ignore list"), self)
        
        # Визначаємо ім'я файлу або маску для ігнорування
        diff_item = self.diff_items[row]
        filename = os.path.basename(diff_item['rel_path'])
        
        ignore_action.triggered.connect(lambda: self.add_to_ignore_list(filename, row))
        menu.addAction(ignore_action)
        menu.exec(self.table.viewport().mapToGlobal(position))
        
    def add_to_ignore_list(self, pattern, row_index):
        # Отримуємо старі маски, додаємо нову
        patterns = self.settings_manager.get_sync_ignored_patterns()
        if pattern not in patterns:
            patterns.append(pattern)
            self.settings_manager.set_sync_ignored_patterns(patterns)
            
            # Також оновлюємо текстове поле в налаштуваннях, якщо вони відкриті
            if hasattr(self.parent(), "settings_dialog") and self.parent().settings_dialog:
                self.parent().settings_dialog.sync_ignored_patterns_edit.setText(", ".join(patterns))
                
            self.parent().log_event_message(lang.get("SYNC_IGNORE_ADDED_SUCCESS", "Pattern '{pattern}' added to sync ignore list.").format(pattern=pattern))
            
            # Видаляємо рядок з інтерфейсу
            self.table.removeRow(row_index)
            self.diff_items.pop(row_index)
            
            # Якщо таблиця порожня, відключаємо кнопку синхронізації
            if self.table.rowCount() == 0:
                self.status_label.setText(lang.get("SYNC_NO_CHANGES", "No changes detected. Folders are synchronized."))
                self.ok_button.setEnabled(False)

    def reject(self):
        # Змінюємо прапорець canceled і примусово відключаємо SSH сесію в потоці, щоб не чекати таймаутів
        try:
            if self.scanner and self.scanner.isRunning():
                self.scanner.canceled = True
                # М'яко просимо потік завершитись
                self.scanner.wait(100)
                if self.scanner.isRunning():
                    # Примусове завершення
                    self.scanner.terminate()
                    self.scanner.wait(100)
        except RuntimeError:
            # Об'єкт C++ вже видалено
            pass
        super().reject()

# Потік для операцій зі зміни директорії (листинг, зміна директорії)
class DirectoryOperationThread(QThread):
    list_complete = Signal(list)
    change_dir_complete = Signal(str, str)
    error = Signal(str, str)

    def __init__(self, sftp_client, connection_lock, operation, path=None):
        super().__init__()
        self.sftp_client = sftp_client
        self.connection_lock = connection_lock
        self.operation = operation
        self.path = path
        self.settings_manager = JsonSettingsManager()

    def run(self):
        try:
            with self.connection_lock:
                if self.operation == 'list':
                    show_hidden = self.settings_manager.get_show_hidden()
                    files = self.sftp_client.list_directory(show_hidden=show_hidden)
                    self.list_complete.emit(files)

                elif self.operation == 'chdir':
                    old_path = self.sftp_client.current_directory
                    success, new_path_or_error = self.sftp_client.change_directory(self.path)
                    if success:
                        self.change_dir_complete.emit(old_path, new_path_or_error)
                    else:
                        self.error.emit(self.operation, new_path_or_error)

        except Exception as e:
            self.error.emit(self.operation, lang["CRITICAL_THREAD_ERROR"].format(e=str(e)))

# КРОК 1: ПОВНІСТЮ ЗАМІНІТЬ ЦЕЙ КЛАС
class ArchiveExtractorThread(QThread):
    finished_signal = Signal(str)
    error_signal = Signal(str, str)

    def __init__(self, archive_path, dest_dir, members_to_extract=None):
        super().__init__()
        self.archive_path = archive_path
        self.dest_dir = dest_dir
        self.members_to_extract = members_to_extract

    def run(self):
        try:
            if not os.path.exists(self.archive_path):
                raise FileNotFoundError(lang["ARCHIVE_FILE_NOT_FOUND"])

            with zipfile.ZipFile(self.archive_path, 'r') as zf:
                # Визначаємо, які файли розпаковувати:
                # або переданий список, або всі файли з архіву.
                members = self.members_to_extract if self.members_to_extract is not None else zf.infolist()
                
                for member in members:
                    zf.extract(member, path=self.dest_dir)
                    
                    # Пропускаємо каталоги, оскільки для них не потрібно встановлювати дату
                    if member.is_dir():
                        continue
                        
                    extracted_path = os.path.join(self.dest_dir, member.filename)
                    
                    # Конвертуємо та встановлюємо оригінальну дату
                    date_time = datetime(*member.date_time).timestamp()
                    os.utime(extracted_path, (date_time, date_time))
            
            self.finished_signal.emit(lang["ARCHIVE_EXTRACTED_SUCCESSFULLY"].format(archive_name=os.path.basename(self.archive_path)))

        except Exception as e:
            self.error_signal.emit(self.archive_path, str(e))
        finally:
            # Видаляємо тимчасовий архів після розпакування або у разі помилки
            if os.path.exists(self.archive_path):
                try:
                    os.remove(self.archive_path)
                except OSError:
                    pass

# Потік для пошуку файлів на віддаленому сервері
class SearchThread(QThread):
    result_found = Signal(str)
    search_complete = Signal(int)
    error = Signal(str)

    def __init__(self, ssh_client, base_path, query, search_type='name', case_insensitive=False):
        super().__init__()
        self.client = ssh_client
        self.base_path = base_path
        self.query = query
        self.search_type = search_type
        self.case_insensitive = case_insensitive
        self._is_cancelled = False

    def run(self):
        if not self.client or not self.client.get_transport() or not self.client.get_transport().is_active():
            self.error.emit(lang["SSH_CLIENT_NOT_CONNECTED"])
            return

        try:
            command = ""
            quoted_path = shlex.quote(self.base_path)

            if self.search_type == 'name':
                name_flag = "-iname" if self.case_insensitive else "-name"
                command = f"cd {quoted_path} && find . -type f {name_flag} '*{self.query}*'"

            elif self.search_type == 'content':
                case_flag = "-i" if self.case_insensitive else ""
                quoted_query = shlex.quote(self.query)
                command = f"cd {quoted_path} && grep -r -l {case_flag} {quoted_query} ."
            
            if not command:
                self.error.emit(lang["UNKNOWN_SEARCH_TYPE"])
                return

            stdin, stdout, stderr = self.client.exec_command(command, timeout=120)
            
            found_count = 0
            for line in stdout:
                if self._is_cancelled:
                    break
                result_path = line.strip()
                
                if result_path.startswith('./'):
                    result_path = result_path[2:]
                    
                if result_path:
                    self.result_found.emit(result_path)
                    found_count += 1
            
            error_output = stderr.read().decode('utf-8', errors='ignore').strip()
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0 and not (self.search_type == 'content' and exit_status == 1 and found_count == 0):
                 if error_output:
                     self.error.emit(lang["SERVER_ERROR"].format(error_output=error_output))
                 else:
                     self.error.emit(lang["COMMAND_EXITED_WITH_CODE"].format(exit_status=exit_status))
            
            if not self._is_cancelled:
                self.search_complete.emit(found_count)

        except Exception as e:
            self.error.emit(lang["CRITICAL_SEARCH_ERROR"].format(e=str(e)))

    def cancel(self):
        self._is_cancelled = True





class ArchiveConflictCheckThread(QThread):
    """
    Перший етап: сканує локальні файли та виконує одну швидку перевірку
    конфліктів на віддаленому сервері.
    """
    status_update = Signal(str)
    check_complete = Signal(dict, list, list) # local_file_map, non_conflicts, conflicts
    error = Signal(str)

    def __init__(self, local_paths, connection_details, remote_base_path, parent=None):
        super().__init__(parent)
        self.local_paths = local_paths
        self.conn_details = connection_details
        self.remote_base_path = remote_base_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _create_ssh_connection(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_args = {
            'hostname': self.conn_details.get('hostname'),
            'port': self.conn_details.get('port'),
            'username': self.conn_details.get('username'),
            'timeout': 15
        }
        password = self.conn_details.get('password')
        key_filename = self.conn_details.get('key_filename')

        # ВИПРАВЛЕННЯ: Ігноруємо порожній key_filename
        if key_filename and key_filename != '' and os.path.exists(key_filename):
            connect_args['key_filename'] = key_filename
            if password:
                connect_args['passphrase'] = password
        elif password and password != '':
            connect_args['password'] = password

        # Видаляємо непотрібні ключі
        connect_args.pop('passphrase', None) if 'passphrase' not in connect_args else None
        connect_args.pop('password', None) if 'password' not in connect_args else None

        ssh.connect(**connect_args)
        return ssh

    def run(self):
        ssh = None
        local_file_map = {}
        try:
            self.status_update.emit("Сканування локальних файлів...")
            for path in self.local_paths:
                if self._is_cancelled: return
                if os.path.isdir(path):
                    base_dir = os.path.dirname(path)
                    for root, _, files in os.walk(path):
                        for file in files:
                            local_path = os.path.join(root, file)
                            arcname = os.path.relpath(local_path, base_dir)
                            local_file_map[arcname] = local_path
                elif os.path.isfile(path):
                    arcname = os.path.basename(path)
                    local_file_map[arcname] = path

            if self._is_cancelled: return
            if not local_file_map:
                self.check_complete.emit({}, [], [])
                return

            self.status_update.emit("Швидка перевірка конфліктів на сервері...")
            ssh = self._create_ssh_connection()
            
            remote_files_to_check = list(local_file_map.keys())
            path_conditions = " -o ".join([f"-path {shlex.quote('./' + p.replace(os.path.sep, '/'))}" for p in remote_files_to_check])
            command = f"cd {shlex.quote(self.remote_base_path)} && find . -type f \\( {path_conditions} \\) -printf '%P\\t%s\\t%T@\\n'"
            
            stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
            existing_remote_files = {}
            for line in stdout:
                parts = line.strip().split('\t', 2)
                if len(parts) == 3:
                    path, size, mtime = parts
                    existing_remote_files[path] = {'size': int(size), 'mtime': float(mtime)}
            
            exit_status = stdout.channel.recv_exit_status()
            if exit_status not in [0, 1]:
                error_output = stderr.read().decode('utf-8', errors='ignore').strip()
                if error_output: raise Exception(f"Server error: {error_output}")
            
            conflicts, non_conflicts = [], []
            for arcname, local_path in local_file_map.items():
                remote_arcname = arcname.replace(os.path.sep, '/')
                if remote_arcname in existing_remote_files:
                    local_stat = os.stat(local_path)
                    source_meta = {'mtime': local_stat.st_mtime, 'size': local_stat.st_size}
                    conflicts.append({'arcname': arcname, 'source_meta': source_meta, 'dest_meta': existing_remote_files[remote_arcname]})
                else:
                    non_conflicts.append((local_path, arcname))
            
            self.check_complete.emit(local_file_map, non_conflicts, conflicts)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            if ssh: ssh.close()

class ArchiveCreationUploadThread(QThread):
    """
    Другий етап: отримує фінальний список файлів, створює архів,
    завантажує та розпаковує його на сервері.
    """
    status_update = Signal(str)
    # ADDED: Signal to report upload progress
    progress_updated = Signal(str, int, int) # task_id, transferred_bytes, total_bytes
    finished_with_success = Signal(str)
    error = Signal(str)

    # MODIFIED: __init__ now accepts task_id
    def __init__(self, task_id, approved_files, connection_details, remote_base_path, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.approved_files = approved_files
        self.conn_details = connection_details
        self.remote_base_path = remote_base_path
        self._is_cancelled = False

    def _create_ssh_connection(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_args = {'hostname': self.conn_details.get('hostname'), 'port': self.conn_details.get('port'), 'username': self.conn_details.get('username'), 'timeout': 15}
        password = self.conn_details.get('password')
        key_filename = self.conn_details.get('key_filename')
        if key_filename and os.path.exists(key_filename):
            connect_args['key_filename'] = key_filename
            if password: connect_args['passphrase'] = password
        elif password:
            connect_args['password'] = password
        if not password:
            connect_args.pop('passphrase', None)
            connect_args.pop('password', None)
        ssh.connect(**connect_args)
        return ssh

    def run(self):
        ssh = None
        local_zip_path = ""
        try:
            self.status_update.emit(f"Створення архіву з {len(self.approved_files)} файлів...")
            temp_dir = tempfile.gettempdir()
            local_zip_path = os.path.join(temp_dir, f"sftp_upload_{secrets.token_hex(8)}.zip")

            with zipfile.ZipFile(local_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for local_path, arcname in self.approved_files:
                    if self._is_cancelled: raise InterruptedError()
                    zf.write(local_path, arcname)

            self.status_update.emit("Завантаження архіву на сервер...")
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            remote_temp_path = f"/tmp/{os.path.basename(local_zip_path)}"

            # --- START: Progress Reporting Logic ---
            total_size = os.path.getsize(local_zip_path)

            def progress_callback(transferred, total):
                if self._is_cancelled:
                    # This will stop the sftp.put call
                    raise InterruptedError("Upload cancelled by user")
                self.progress_updated.emit(self.task_id, transferred, total_size)
            
            # Use the callback in the sftp.put call
            sftp.put(local_zip_path, remote_temp_path, callback=progress_callback)
            # --- END: Progress Reporting Logic ---

            sftp.close()

            if self._is_cancelled: raise InterruptedError()

            self.status_update.emit("Розпакування архіву на сервері...")
            command = f"unzip -o {shlex.quote(remote_temp_path)} -d {shlex.quote(self.remote_base_path)}"
            stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error_output = stderr.read().decode('utf-8', errors='ignore').strip()
                if "command not found" in error_output.lower(): raise Exception("На сервері не знайдено команду 'unzip'.")
                raise Exception(f"Помилка розпакування: {error_output}")
            
            self.status_update.emit("Очищення...")
            sftp = ssh.open_sftp()
            sftp.remove(remote_temp_path)
            sftp.close()
            
            self.finished_with_success.emit("Архів успішно завантажено та розпаковано.")
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if ssh: ssh.close()
            if local_zip_path and os.path.exists(local_zip_path):
                try: os.remove(local_zip_path)
                except OSError: pass

class AdaptiveTransferManager(QObject):
    request_new_transfer = Signal(tuple)
    status_update = Signal(str)

    def __init__(self, ceiling=50, parent=None):
        """
        Ініціалізує менеджер передач.

        Args:
            ceiling (int): Максимальна кількість одночасних з'єднань,
                           вище якої менеджер не буде піднімати ліміт.
            parent (QObject, optional): Батьківський об'єкт Qt.
        """
        super().__init__(parent)
        self.MIN_CONCURRENT = 2
        self.RETRY_COOLDOWN_SEC = 0.8
        self.MAX_RETRY_COOLDOWN_SEC = 4.0
        # Стеля тепер гнучка і береться з налаштувань, але не може бути меншою за мінімум.
        self.MAX_CONCURRENT_CAP = max(self.MIN_CONCURRENT, ceiling)
        self.discovered_ceiling = self.MAX_CONCURRENT_CAP
        self.current_limit = self.MIN_CONCURRENT
        self.success_counter = 0
        self.queue = []
        self.delayed_retries = []
        self.active_transfers = set()
        self.pending_data = {}
        self.retry_counts = {}
        # Змінні для керування логуванням
        self.next_log_milestone = 10
        self.last_failure_log_time = 0
        self.last_connection_error_log_time = 0
        self.next_retry_allowed_at = 0

    def add_transfers(self, transfer_items: list):
        """Додає список файлів для передачі в чергу."""
        self.queue.extend(transfer_items)
        self._process_queue()

    def report_success(self, transfer_id: str):
        """Обробляє успішне завершення передачі файлу."""
        self.active_transfers.discard(transfer_id)
        self.pending_data.pop(transfer_id, None)
        self.retry_counts.pop(transfer_id, None)
        self.success_counter += 1
        self.next_retry_allowed_at = 0

        # Якщо кількість успішних передач дорівнює поточному ліміту,
        # спробуємо обережно збільшити ліміт.
        if self.success_counter >= self.current_limit:
            new_limit = min(self.current_limit + 1, self.discovered_ceiling)
            if new_limit > self.current_limit:
                self.current_limit = new_limit
                # Логуємо збільшення тільки на "круглих" числах, щоб не спамити.
                # if self.current_limit >= self.next_log_milestone:
                #     log_msg = lang["ADAPTIVE_LIMIT_INCREASED"].format(limit=self.current_limit)
                #     self.status_update.emit(log_msg)
                #     self.next_log_milestone += 10
            self.success_counter = 0

        self._process_queue()

    def report_failure(self, transfer_id: str):
        """Обробляє звичайну невдачу передачі (напр., 'permission denied')."""
        self.active_transfers.discard(transfer_id)
        self.pending_data.pop(transfer_id, None)
        self.retry_counts.pop(transfer_id, None)
        # Різко зменшуємо ліміт вдвічі, але не нижче мінімального.
        self.current_limit = max(self.MIN_CONCURRENT, int(self.current_limit / 2))
        self.success_counter = 0
        self.next_retry_allowed_at = 0
        
        # Логуємо з "періодом тиші" у 3 секунди, щоб уникнути спаму.
        current_time = time.time()
        if current_time - self.last_failure_log_time > 3:
            log_msg = lang["ADAPTIVE_LIMIT_DECREASED"].format(limit=self.current_limit)
            self.status_update.emit(log_msg)
            self.last_failure_log_time = current_time
            
        self._process_queue()

    def report_cancellation(self, transfer_id: str):
        """Обробляє скасування передачі, звільняючи слот без штрафів."""
        self.active_transfers.discard(transfer_id)
        self.pending_data.pop(transfer_id, None)
        self.retry_counts.pop(transfer_id, None)
        self.next_retry_allowed_at = 0
        # Просто запускаємо обробку черги, щоб почати наступну передачу
        self._process_queue()

    def report_connection_error(self, transfer_id: str):
        """
        Обробляє критичну помилку з'єднання (напр., таймаут або відмова сервера).
        Файл повертається на початок черги для повторної спроби.
        """
        self.active_transfers.discard(transfer_id)
        
        failed_data = self.pending_data.pop(transfer_id, None)
        if failed_data:
            retry_count = self.retry_counts.get(transfer_id, 0) + 1
            self.retry_counts[transfer_id] = retry_count
            retry_delay = min(self.RETRY_COOLDOWN_SEC * retry_count, self.MAX_RETRY_COOLDOWN_SEC)
            ready_at = time.time() + retry_delay
            self.delayed_retries.append((ready_at, failed_data))
            QTimer.singleShot(int(retry_delay * 1000), self._process_queue)
        
        # Знижуємо не тільки поточний ліміт, а й "стелю", оскільки
        # ми досягли реального ліміту можливостей сервера.
        new_ceiling = max(self.MIN_CONCURRENT, self.current_limit - 1)
        self.discovered_ceiling = new_ceiling
        self.current_limit = min(self.current_limit, self.discovered_ceiling)
        self.success_counter = 0
        self.next_retry_allowed_at = time.time() + self.RETRY_COOLDOWN_SEC
        
        # Логуємо з "періодом тиші" у 3 секунди.
        current_time = time.time()
        if current_time - self.last_connection_error_log_time > 3:
            log_msg = lang["ADAPTIVE_LIMIT_CEILING_REACHED"].format(ceiling=new_ceiling)
            self.status_update.emit(log_msg)
            self.last_connection_error_log_time = current_time
        
        self._process_queue()

    def _process_queue(self):
        """
        Внутрішній метод, який запускає нові передачі, поки є вільні "слоти".
        """
        now = time.time()
        if self.delayed_retries:
            ready_retries = [item for item in self.delayed_retries if item[0] <= now]
            self.delayed_retries = [item for item in self.delayed_retries if item[0] > now]
            for _, transfer_data in ready_retries:
                self.queue.append(transfer_data)

        if self.next_retry_allowed_at and time.time() < self.next_retry_allowed_at:
            return

        while len(self.active_transfers) < self.current_limit and self.queue:
            transfer_data = self.queue.pop(0)
            transfer_id = transfer_data[1]
            self.pending_data[transfer_id] = transfer_data
            self.active_transfers.add(transfer_id)
            self.request_new_transfer.emit(transfer_data)

    def is_active(self) -> bool:
        """Перевіряє, чи є активні або очікуючі завдання."""
        return bool(self.active_transfers or self.queue)

    def reset(self):
        """Повністю скидає стан менеджера при скасуванні всіх завдань."""
        self.queue.clear()
        self.delayed_retries.clear()
        self.active_transfers.clear()
        self.pending_data.clear()
        self.retry_counts.clear()
        self.success_counter = 0
        # Скидаємо змінні логування
        self.next_log_milestone = 10 
        self.last_failure_log_time = 0
        self.last_connection_error_log_time = 0
        self.next_retry_allowed_at = 0
        print("[Adaptive Manager] State has been reset (queues cleared).")

class ElidedLabel(QLabel):
    def __init__(self, text="", elide_mode=Qt.ElideRight, parent=None):
        super().__init__(parent)
        self._full_text = ""
        self._elide_mode = elide_mode
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def fullText(self):
        return self._full_text

    def setText(self, text):
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._update_elided_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self):
        if not self._full_text:
            QLabel.setText(self, "")
            return
        available_width = self.width()
        if available_width <= 0:
            QLabel.setText(self, self.fontMetrics().elidedText(self._full_text, self._elide_mode, 240))
            return
        elided = self.fontMetrics().elidedText(self._full_text, self._elide_mode, available_width)
        QLabel.setText(self, elided)

class TransfersPanel(QWidget):
    cancel_all_transfers = Signal()
    transfer_cancellation_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)
        
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        
        self.title_label = QLabel(lang["ACTIVE_TRANSFERS"])
        self.title_label.setObjectName("PanelTitle")
        
        self.transfer_count_label = QLabel("(0)")
        self.transfer_count_label.setStyleSheet("color: #b9bbbe; font-size: 12px; margin-left: 0px;")

        self.header_layout.addWidget(self.title_label)
        self.header_layout.addWidget(self.transfer_count_label)
        self.header_layout.addStretch()
        
        self.cancel_all_button = QPushButton(lang["CANCEL_ALL"])
        self.cancel_all_button.setToolTip(lang["CANCEL_ALL_ACTIVE_TRANSFERS_TOOLTIP"])
        self.cancel_all_button.clicked.connect(self.request_cancel_all)
        self.cancel_all_button.setObjectName("CancelAllButton")
        self.cancel_all_button.setCursor(Qt.PointingHandCursor)
        self.cancel_all_button.setVisible(False)
        
        self.header_layout.addWidget(self.cancel_all_button)
        self.main_layout.addLayout(self.header_layout)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("TransfersScrollArea")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.transfers_container = QWidget()
        self.transfers_container.setObjectName("TransfersContainer")
        self.layout = QVBoxLayout(self.transfers_container)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(8)
        self.layout.addStretch()

        self.scroll_area.setWidget(self.transfers_container)
        self.main_layout.addWidget(self.scroll_area)
        
        self.tasks = {}

    def add_task(self, task_id, task_name, is_upload):
        if task_id in self.tasks:
            return

        self.cancel_all_button.setVisible(True)

        task_container = QWidget()
        container_layout = QVBoxLayout(task_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(3)
        
        opacity_effect = QGraphicsOpacityEffect(task_container)
        task_container.setGraphicsEffect(opacity_effect)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(0)
        
        if is_upload:
            operation_icon = "▲"
            icon_color = "#43b581"
            tooltip_text = lang["UPLOADING"]
        else:
            operation_icon = "▼"
            icon_color = "#3498db"
            tooltip_text = lang["DOWNLOADING"]

        icon_label = QLabel(operation_icon)
        icon_label.setToolTip(tooltip_text)
        icon_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {icon_color};")
        
        name_label = ElidedLabel(task_name)
        name_label.setStyleSheet("font-weight: bold;")

        task_count_label = QLabel("")
        task_count_label.setStyleSheet("color: #b9bbbe; font-size: 12px;")

        top_layout.addWidget(icon_label)
        top_layout.addWidget(name_label, 1)
        top_layout.addWidget(task_count_label)
        
        container_layout.addLayout(top_layout)

        details_container = QWidget()
        details_container.setObjectName("TransferDetailsContainer")
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(8, 8, 8, 8)
        details_layout.setSpacing(5)

        current_file_label = ElidedLabel(lang["IN_QUEUE"])
        current_file_label.setStyleSheet("font-size: 11px; color: #dcddde; background-color: transparent;")
        details_layout.addWidget(current_file_label)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(0)
        
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        progress_bar.setFixedHeight(20)
        progress_bar.setFormat("")
        progress_bar.setObjectName("ProgressBarQueued")

        cancel_button = QPushButton("×")
        cancel_button.setToolTip(lang["CANCEL_TASK_TOOLTIP"])
        cancel_button.setObjectName("CancelButton")
        cancel_button.setCursor(Qt.PointingHandCursor)
        cancel_button.setFixedSize(20, 20)
        cancel_button.clicked.connect(lambda: self.transfer_cancellation_requested.emit(task_id))

        bottom_layout.addWidget(progress_bar, 1)
        bottom_layout.addWidget(cancel_button)
        
        details_layout.addLayout(bottom_layout)
        container_layout.addWidget(details_container)
        
        self.layout.insertWidget(0, task_container)
        
        self.tasks[task_id] = {
            "name_label": name_label,
            "progress_bar": progress_bar,
            "container": task_container,
            "cancel_button": cancel_button,
            "opacity_effect": opacity_effect,
            "task_count_label": task_count_label,
            "current_file_label": current_file_label
        }
        self.update_transfer_count()

    def set_task_indeterminate(self, task_id, subtitle):
        if task_id in self.tasks:
            self.tasks[task_id]["current_file_label"].setText(subtitle)
            
            progress_bar = self.tasks[task_id]["progress_bar"]
            progress_bar.setRange(0, 0)
            progress_bar.setFormat("")
            progress_bar.setObjectName("")
            style = self.style()
            if style:
                style.unpolish(progress_bar)
                style.polish(progress_bar)

    def set_task_determinate(self, task_id):
        if task_id in self.tasks:
            progress_bar = self.tasks[task_id]["progress_bar"]
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setObjectName("ProgressBarQueued")
            style = self.style()
            if style:
                style.unpolish(progress_bar)
                style.polish(progress_bar)
            
    def update_task_subtitle(self, task_id, text, current_file, total_files):
        if task_id in self.tasks:
            task_info = self.tasks[task_id]
            task_info["task_count_label"].setText(f"({current_file}/{total_files})")
            task_info["current_file_label"].setText(text)
            
    def update_task_progress(self, task_id, current_bytes, total_bytes):
        if task_id in self.tasks:
            progress_bar = self.tasks[task_id]["progress_bar"]
            if total_bytes > 0:
                progress_bar.setMaximum(total_bytes)
                progress_bar.setValue(current_bytes)
                progress_bar.setFormat(f"{current_bytes / (1024*1024):.2f} MB / {total_bytes / (1024*1024):.2f} MB")
                progress_bar.setTextVisible(True)

    def complete_transfer(self, task_id, success, message):
        if task_id in self.tasks:
            task_info = self.tasks[task_id]
            progress_bar = task_info["progress_bar"]
            
            task_info["task_count_label"].setText("")
            progress_bar.setRange(0, 100)
            
            final_status = ""
            if success:
                progress_bar.setValue(100)
                final_status = lang["COMPLETED"]
                progress_bar.setObjectName("ProgressBarSuccess")
            else:
                # ВИПРАВЛЕНО: Чітко перевіряємо, чи повідомлення є саме про скасування
                if message == lang.get("CANCELED", "Canceled"):
                    final_status = lang["CANCELED"]
                    progress_bar.setObjectName("ProgressBarCanceled")
                else:
                    final_status = lang["ERROR"]
                    progress_bar.setObjectName("ProgressBarError")

            task_info["current_file_label"].setText(final_status)
            progress_bar.setFormat("")
            
            style = self.style()
            if style:
                style.unpolish(progress_bar)
                style.polish(progress_bar)

            task_info["cancel_button"].setEnabled(False)
            
            container = task_info["container"]
            animation = QPropertyAnimation(task_info["opacity_effect"], b"opacity", parent=container)
            
            animation.setDuration(400) 
            animation.setStartValue(1.0)
            animation.setEndValue(0.0)
            animation.finished.connect(lambda: self.remove_task(task_id))
            
            QTimer.singleShot(1500, animation.start)

    def remove_task(self, task_id):
        if task_id in self.tasks:
            task_info = self.tasks.pop(task_id)
            self.layout.removeWidget(task_info["container"])
            task_info["container"].deleteLater()
            self.update_transfer_count()
            if not self.tasks:
                self.cancel_all_button.setVisible(False)
    
    def update_transfer_count(self):
        count = len(self.tasks)
        self.transfer_count_label.setText(f"({count})")

    def request_cancel_all(self):
        if self.tasks:
            confirm = QMessageBox.question(
                self, lang["CONFIRM_CANCELLATION"],
                lang["CONFIRM_CANCEL_ALL_PROMPT"],
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                self.cancel_all_transfers.emit()

class LogWidget(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(0)
        
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PanelTitle")
        layout.addWidget(self.title_label)
        
        self.log_browser = QTextBrowser()
        self.log_browser.setReadOnly(True)
        self.log_browser.setOpenExternalLinks(False)
        self.log_browser.setObjectName("LogBrowser")
        self.log_browser.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log_browser.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.log_browser)
        
    def show_context_menu(self, position):
        # Створюємо стандартне контекстне меню, яке вже містить "Копіювати"
        menu = self.log_browser.createStandardContextMenu()
        
        # Додаємо розділювач, щоб візуально відокремити стандартні дії від наших
        if menu.actions():
            menu.addSeparator()

        # Додаємо наш власний пункт "Очистити лог"
        clear_action = menu.addAction(lang["CLEAR_LOG"])
        clear_action.triggered.connect(self.clear_log)
        
        # Показуємо оновлене меню
        menu.exec(self.log_browser.viewport().mapToGlobal(position))

    def add_log_message(self, message):
        self.log_browser.append(message)
        self.log_browser.moveCursor(QTextCursor.End)
        self.log_browser.ensureCursorVisible()
    
    def clear_log(self):
        self.log_browser.clear()

class JsonSettingsManager:
    def __init__(self, config_path=None):
        if config_path is None:
            # Назва програми, яка буде використовуватись для створення теки
            APP_NAME = "SFTPanda"

            # Визначаємо шлях до теки з налаштуваннями залежно від ОС
            if sys.platform == "win32":
                # Для Windows використовуємо %APPDATA%
                base_dir = os.getenv('APPDATA') or os.path.expanduser('~')
                config_dir = os.path.join(base_dir, APP_NAME)
            else:
                # Для Linux, macOS та інших Unix-подібних систем
                # Використовуємо стандартний шлях ~/.config/
                config_dir = os.path.join(os.path.expanduser('~'), '.config', APP_NAME)

            # Створюємо теку, якщо вона не існує.
            # exist_ok=True запобігає помилці, якщо тека вже є.
            os.makedirs(config_dir, exist_ok=True)
            
            # Встановлюємо фінальний шлях до файлу налаштувань
            self.config_path = os.path.join(config_dir, "sftp_settings.json")
        else:
            self.config_path = config_path
            
        self.settings = {
            "editor": {"path": self._get_default_editor()},
            "files": {"show_hidden": False},
            "columns": {
                "name_visible": True, "date_visible": True, "size_visible": True,
                "group_visible": True, "permissions_visible": True
            },
            "sort": {"remote_column": 0, "remote_order": 0},
            "reconnect": {"enabled": True, "interval": 5, "max_attempts": 3},
            "transfers": {"max_concurrent": 5},
            "speed_limits": {
                "enabled": False, 
                "upload_kbps": 0, 
                "download_kbps": 0
            },
            "last_session": {"server_name": "", "remote_directory": "", "auto_connect": True},
            "servers": [],
            "pending_cleanup": {},
            "language": "en",
            "sync_ignored_patterns": [".git", "node_modules", ".env"]
        }
        self.load_settings()
        
    def _get_default_editor(self):
        if sys.platform == "win32": return "notepad.exe"
        elif sys.platform == "darwin": return "open -t"
        else:
            for editor in ["gedit", "kate", "nano", "vim", "vi"]:
                if self._which(editor): return editor
            return "xdg-open"
            
    def _which(self, program):
        def is_exe(fpath): return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
        fpath, fname = os.path.split(program)
        if fpath:
            if is_exe(program): return program
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                exe_file = os.path.join(path, program)
                if is_exe(exe_file): return exe_file
        return None
        
    def load_settings(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as file:
                    loaded_settings = json.load(file)
                    self._update_dict(self.settings, loaded_settings)
            except Exception as e:
                print(lang["ERROR_LOADING_SETTINGS"].format(e=e))
        
    def save_settings(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as file:
                json.dump(self.settings, file, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(lang["ERROR_SAVING_SETTINGS"].format(e=e))
            return False
            
    def _update_dict(self, target, source):
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._update_dict(target[key], value)
            else:
                target[key] = value
        
    def get_editor_path(self): return self.settings["editor"]["path"]
    def set_editor_path(self, path): self.settings["editor"]["path"] = path; self.save_settings()
    def get_show_hidden(self): return self.settings["files"]["show_hidden"]
    def set_show_hidden(self, show_hidden): self.settings["files"]["show_hidden"] = show_hidden; self.save_settings()
    
    def get_sync_ignored_patterns(self):
        return self.settings.get("sync_ignored_patterns", [".git", "node_modules", ".env"])
    def set_sync_ignored_patterns(self, patterns):
        self.settings["sync_ignored_patterns"] = patterns
        self.save_settings()
    
    def get_last_sync_path(self):
        return self.settings.get("last_sync_path", "")
    def set_last_sync_path(self, path):
        self.settings["last_sync_path"] = path
        self.save_settings()
    
    def get_visible_columns(self):
        columns = self.settings["columns"]
        return {"name": columns["name_visible"], "date": columns["date_visible"], "size": columns["size_visible"],
                "group": columns["group_visible"], "permissions": columns["permissions_visible"]}

    def set_column_visibility(self, column_name, visible):
        key = f"{column_name}_visible"
        if key in self.settings["columns"]: self.settings["columns"][key] = visible; self.save_settings()
            
    def get_sort_settings(self):
        return (self.settings["sort"].get("remote_column", 0), 0 if self.settings["sort"].get("remote_order", 0) == 0 else 1)
            
    def set_sort_settings(self, column, order):
        self.settings["sort"]["remote_column"] = column; self.settings["sort"]["remote_order"] = 0 if order == 0 else 1; self.save_settings()
    
    def get_reconnect_settings(self):
        return {"enabled": self.settings["reconnect"].get("enabled", True), "interval": self.settings["reconnect"].get("interval", 5),
                "max_attempts": self.settings["reconnect"].get("max_attempts", 3)}
    
    def set_reconnect_settings(self, enabled, interval=None, max_attempts=None):
        self.settings["reconnect"]["enabled"] = enabled
        if interval is not None: self.settings["reconnect"]["interval"] = interval
        if max_attempts is not None: self.settings["reconnect"]["max_attempts"] = max_attempts
        self.save_settings()
        
    def get_last_session(self):
        if "last_session" in self.settings: return self.settings["last_session"]
        else: self.settings["last_session"] = {"server_name": "", "remote_directory": "", "auto_connect": True}; return self.settings["last_session"]
    
    def set_last_session(self, server_name, remote_directory):
        if "last_session" not in self.settings: self.settings["last_session"] = {}
        self.settings["last_session"]["server_name"] = server_name; self.settings["last_session"]["remote_directory"] = remote_directory
        self.save_settings()
    
    def set_auto_connect(self, enabled):
        if "last_session" not in self.settings: self.settings["last_session"] = {}
        self.settings["last_session"]["auto_connect"] = enabled; self.save_settings()
    
    def get_auto_connect(self):
        if "last_session" in self.settings and "auto_connect" in self.settings["last_session"]: return self.settings["last_session"]["auto_connect"]
        return True

    def get_max_concurrent_transfers(self): return self.settings.get("transfers", {}).get("max_concurrent", 5)
    def set_max_concurrent_transfers(self, value):
        if "transfers" not in self.settings: self.settings["transfers"] = {}
        self.settings["transfers"]["max_concurrent"] = value; self.save_settings()

    def add_pending_cleanup_file(self, server_name, remote_path):
        if server_name not in self.settings["pending_cleanup"]: self.settings["pending_cleanup"][server_name] = []
        if remote_path not in self.settings["pending_cleanup"][server_name]: self.settings["pending_cleanup"][server_name].append(remote_path); self.save_settings()

    def remove_pending_cleanup_file(self, server_name, remote_path):
        if server_name in self.settings["pending_cleanup"]:
            if remote_path in self.settings["pending_cleanup"][server_name]:
                self.settings["pending_cleanup"][server_name].remove(remote_path)
                if not self.settings["pending_cleanup"][server_name]: del self.settings["pending_cleanup"][server_name]
                self.save_settings()

    def get_pending_cleanup_files(self, server_name): return self.settings["pending_cleanup"].get(server_name, [])

    def get_language(self):
        return self.settings.get("language", "en") # 'en' as a fallback

    def set_language(self, lang_code):
        self.settings["language"] = lang_code
        self.save_settings()

    def get_speed_limit_settings(self):
        return self.settings.get("speed_limits", {"enabled": False, "upload_kbps": 0, "download_kbps": 0})

    def set_speed_limit_settings(self, enabled, upload_kbps, download_kbps):
        if "speed_limits" not in self.settings:
            self.settings["speed_limits"] = {}
        self.settings["speed_limits"]["enabled"] = enabled
        self.settings["speed_limits"]["upload_kbps"] = upload_kbps
        self.settings["speed_limits"]["download_kbps"] = download_kbps
        self.save_settings()



class SFTPClient:
    def __init__(self):
        self.client = None; self.sftp = None; self.hostname = ""; self.port = 22; self.username = ""
        self.password = ""; self.start_directory = "/"; self.current_directory = "/"; self.connected = False; self.connection_details = None
        
    def check_directory_is_empty(self, path):
        if not self.sftp: return False
        try:
            dir_items = self.sftp.listdir(path)
            if dir_items: return False
            return True
        except FileNotFoundError: return True
        except Exception: return False

    # У класі SFTPClient
    def connect(self, hostname, port, username, password, start_directory="/", key_filename=None):
        try:
            self.hostname = hostname
            self.port = port
            self.username = username
            # Зберігаємо пароль/парольну фразу для перепідключення
            self.password = password 
            self.start_directory = start_directory
            
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # --- ПОЧАТОК ЗМІН: Динамічно збираємо аргументи для підключення ---
            connect_args = {
                'hostname': hostname,
                'port': port,
                'username': username,
                'timeout': 15  # Рекомендую додати таймаут
            }

            if key_filename and os.path.exists(key_filename):
                connect_args['key_filename'] = key_filename
                # Якщо введено пароль, він використовується як парольна фраза для ключа
                if password:
                    connect_args['passphrase'] = password
            else:
                # Інакше використовуємо звичайну автентифікацію за паролем
                connect_args['password'] = password
            
            # Видаляємо пусті значення, щоб уникнути помилок paramiko
            if not password:
                connect_args.pop('passphrase', None)
                connect_args.pop('password', None)

            self.client.connect(**connect_args)
            
            # --- ПОЧАТОК ЗМІН: Keep-Alive для утримання з'єднання активним ---
            transport = self.client.get_transport()
            if transport:
                transport.set_keepalive(30)  # Відправляти пусті пакети кожні 30 секунд
            # --- КІНЕЦЬ ЗМІН ---

            self.sftp = self.client.open_sftp()
            if start_directory:
                self.current_directory = start_directory
                self.sftp.chdir(start_directory)
            
            self.connected = True
            # Зберігаємо всі деталі, включно з ключем, для перепідключень
            self.connection_details = {
                "hostname": hostname, "port": port, "username": username,
                "password": password, "start_directory": start_directory,
                "key_filename": key_filename
            }
            
            return True, lang["CONNECTION_SUCCESSFUL"]
        except Exception as e:
            self.connected = False
            return False, str(e)
    
    def reconnect(self):
        if not self.connection_details:
            return False, lang["NO_CONNECTION_DATA"]
        try:
            current_directory = self.current_directory
            self.disconnect()
            success, message = self.connect(
                self.connection_details["hostname"],
                self.connection_details["port"],
                self.connection_details["username"],
                self.connection_details["password"],
                self.connection_details.get("start_directory") or "/",
                key_filename=self.connection_details.get("key_filename")
            )
            if success:
                try:
                    self.change_directory(current_directory)
                except:
                    pass
            return success, message
        except Exception as e:
            return False, str(e)
    
    def disconnect(self):
        try:
            if self.sftp:
                try:
                    self.sftp.close()
                except:
                    pass
        finally:
            self.sftp = None
        try:
            if self.client:
                try:
                    transport = self.client.get_transport()
                    if transport:
                        try:
                            transport.close()
                        except:
                            pass
                except:
                    pass
                try:
                    self.client.close()
                except:
                    pass
        finally:
            self.client = None
            self.connected = False
    
    def check_connection(self):
        if not self.sftp or not self.client: return False
        try:
            transport = self.client.get_transport()
            if transport and transport.is_active(): transport.send_ignore(); return True
            else: return False
        except: return False
    
    def check_command_exists(self, command):
        if not self.client: return False
        try:
            stdin, stdout, stderr = self.client.exec_command(f"which {command}"); return stdout.channel.recv_exit_status() == 0
        except Exception: return False
    
    def install_package(self, package_name):
        if not self.client: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            package_managers = [{"check": "which apt-get", "install": "apt-get -y install"}, {"check": "which apt", "install": "apt -y install"},
                                {"check": "which yum", "install": "yum -y install"}, {"check": "which dnf", "install": "dnf -y install"},
                                {"check": "which pacman", "install": "pacman -S --noconfirm"}, {"check": "which zypper", "install": "zypper -n install"},
                                {"check": "which brew", "install": "brew install"}]
            package_manager = None
            for pm in package_managers:
                stdin, stdout, stderr = self.client.exec_command(pm["check"])
                if stdout.channel.recv_exit_status() == 0: package_manager = pm["install"]; break
            if not package_manager: return False, lang["PACKAGE_MANAGER_NOT_FOUND"]
            command = f"sudo {package_manager} {package_name}"
            stdin, stdout, stderr = self.client.exec_command(command); exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0: return True, lang["PACKAGE_INSTALLED_SUCCESSFULLY"].format(package_name=package_name)
            else: error = stderr.read().decode('utf-8'); return False, lang["ERROR_INSTALLING_PACKAGE"].format(error=error)
        except Exception as e: return False, lang["ERROR_INSTALLING_PACKAGE"].format(error=str(e))
    
    def list_directory(self, path=None, show_hidden=False):
        if not self.sftp: return []
        if path is None: path = self.current_directory
        try:
            file_list = []
            if path != "/": file_list.append({'name': "..", 'size': 0, 'date_modified': None, 'is_dir': True, 'permissions': "", 'extension': "", 'group': ""})
            for attr in self.sftp.listdir_attr(path):
                if not show_hidden and attr.filename.startswith('.'): continue
                if attr.filename in ['.', '..']: continue
                is_dir = stat.S_ISDIR(attr.st_mode); extension = ""
                if not is_dir and "." in attr.filename: extension = attr.filename.split(".")[-1].lower()
                file_list.append({'name': attr.filename, 'size': attr.st_size, 'date_modified': datetime.fromtimestamp(attr.st_mtime),
                                  'is_dir': is_dir, 'permissions': oct(attr.st_mode)[-3:], 'extension': extension, 'group': ""})
            return file_list
        except Exception as e: print(lang["ERROR_LISTING_FILES"].format(e=e)); return []
    
    def change_directory(self, path):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            current_path_before_change = self.current_directory
            if path == "..":
                new_path = current_path_before_change.rstrip('/'); last_slash = new_path.rfind('/')
                if last_slash < 0: new_path = "/"
                elif last_slash == 0: new_path = "/"
                else: new_path = new_path[:last_slash]
            elif not path.startswith("/"):
                new_path = current_path_before_change + '/' + path if not current_path_before_change.endswith('/') else current_path_before_change + path
            else: new_path = path
            self.sftp.chdir(new_path); self.current_directory = self.sftp.getcwd()
            if not self.current_directory: self.current_directory = "/"
            return True, self.current_directory
        except Exception as e: print(lang["ERROR_CHANGING_DIRECTORY"].format(e=str(e))); return False, str(e)
    
    def change_permissions(self, filename, permissions, recursive=False):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            path = filename if filename.startswith("/") else f"{self.current_directory}/{filename}"
            if recursive: return self.change_permissions_recursive(path, permissions)
            else: self.sftp.chmod(path, int(permissions, 8)); return True, lang["PERMISSIONS_CHANGED_SUCCESSFULLY"]
        except Exception as e: return False, str(e)

    def change_permissions_recursive(self, path, permissions):
        if not self.client: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            command = f"chmod -R {permissions} {shlex.quote(path)}"; stdin, stdout, stderr = self.client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0: return True, lang["PERMISSIONS_CHANGED_RECURSIVELY_SUCCESSFULLY"]
            else:
                error = stderr.read().decode('utf-8').strip() or f"Команда завершилася з кодом виходу {exit_status}"
                return False, lang["ERROR_CHANGING_PERMISSIONS_RECURSIVELY"].format(error=error)
        except Exception as e: return False, str(e)

    def upload_file(self, local_path, remote_path):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try: self.sftp.put(local_path, remote_path); return True, lang["FILE_UPLOADED_SUCCESSFULLY"]
        except Exception as e: return False, str(e)
    
    def download_file(self, remote_path, local_path):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try: self.sftp.get(remote_path, local_path); return True, lang["FILE_DOWNLOADED_SUCCESSFULLY"]
        except Exception as e: return False, str(e)
    
    def create_directory(self, dir_name):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            path = dir_name if dir_name.startswith("/") else f"{self.current_directory}/{dir_name}"
            self.sftp.mkdir(path); return True, lang["DIRECTORY_CREATED_SUCCESSFULLY"]
        except Exception as e: return False, str(e)

    def create_empty_file(self, filename):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_f: local_path = temp_f.name
            remote_path = filename if filename.startswith("/") else f"{self.current_directory}/{filename}"
            self.sftp.put(local_path, remote_path); os.remove(local_path)
            return True, lang["FILE_CREATED_SUCCESSFULLY"].format(filename=filename)
        except Exception as e:
            if 'local_path' in locals() and os.path.exists(local_path): os.remove(local_path)
            return False, str(e)
            
    def download_for_edit(self, remote_file, editor_path):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            # Базова тимчасова директорія
            temp_dir = os.path.expanduser("~/.sftp_client/temp")
            
            # Визначаємо повний шлях до файлу на сервері
            remote_path = remote_file if remote_file.startswith("/") else f"{self.current_directory}/{remote_file}"

            # --- ПОЧАТОК ЗМІН ---
            # Відтворюємо структуру директорій сервера всередині тимчасової папки.

            # 1. Готуємо відносний шлях, видаляючи початковий слеш
            relative_remote_path = remote_path[1:] if remote_path.startswith('/') else remote_path
            # Додатково замінюємо ":" на випадок, якщо шлях містить щось схоже на диск Windows
            relative_remote_path = relative_remote_path.replace(':', '_')

            # 2. Створюємо повний локальний шлях, що дублює структуру сервера
            local_path = os.path.join(temp_dir, relative_remote_path)
            
            # 3. КЛЮЧОВИЙ КРОК: Створюємо всі необхідні піддиректорії для файлу
            local_file_dir = os.path.dirname(local_path)
            os.makedirs(local_file_dir, exist_ok=True)
            # --- КІНЕЦЬ ЗМІН ---

            # Завантажуємо файл у новостворений шлях
            self.sftp.get(remote_path, local_path)
            
            # Розбиваємо шлях до редактора на команду та аргументи
            command_parts = shlex.split(editor_path)
            command_parts.append(local_path)
            
            subprocess.Popen(command_parts)
            return True, local_path, remote_path
        except Exception as e:
            return False, str(e), None

    def delete_file(self, filename):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            path = filename if filename.startswith("/") else f"{self.current_directory}/{filename}"
            self.sftp.remove(path); return True, lang["FILE_DELETED_SUCCESSFULLY"]
        except Exception as e: return False, str(e)
    
    def delete_directory(self, dirname):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            path = dirname if dirname.startswith("/") else f"{self.current_directory}/{dirname}"
            self.sftp.rmdir(path); return True, lang["DIRECTORY_DELETED_SUCCESSFULLY"]
        except Exception as e: return False, str(e)
    
    def delete_directory_recursive(self, dirname):
        if not self.client: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            path = dirname if dirname.startswith("/") else f"{self.current_directory}/{dirname}"
            command = f"rm -rf {shlex.quote(path)}"; stdin, stdout, stderr = self.client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0: return True, lang["DIRECTORY_DELETED_RECURSIVELY_SUCCESSFULLY"]
            else:
                error = stderr.read().decode('utf-8').strip() or f"Команда завершилася з кодом виходу {exit_status}"
                return False, lang["ERROR_DELETING_DIRECTORY"].format(error=error)
        except Exception as e: return False, str(e)
    
    def get_remote_items_size(self, items):
        """Розраховує загальний розмір файлів/каталогів на сервері в байтах."""
        if not self.client or not items:
            return 0, "Клієнт не підключено або не вказано елементи"
        try:
            # -s: summary, -c: grand total, -b: in bytes
            quoted_items = " ".join([shlex.quote(item) for item in items])
            command = f'cd {shlex.quote(self.current_directory)} && du -scb {quoted_items}'
            
            stdin, stdout, stderr = self.client.exec_command(command, timeout=60)
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                error = stderr.read().decode('utf-8', 'ignore').strip()
                return 0, f"Помилка команди 'du': {error}" if error else f"Команда 'du' завершилась з кодом {exit_status}"

            output = stdout.read().decode('utf-8', 'ignore').strip().split('\n')
            if output and 'total' in output[-1]:
                total_size_str = output[-1].split()[0]
                if total_size_str.isdigit():
                    return int(total_size_str), None
            return 0, "Не вдалося розпарсити вивід команди 'du'"
        except Exception as e:
            return 0, str(e)

    def get_available_space(self):
        """Повертає доступний простір на диску в поточній директорії в байтах."""
        if not self.client:
            return 0, "Клієнт не підключено"
        try:
            # -k: розміри в 1K блоках, -P: POSIX формат для стабільного парсингу
            command = f'cd {shlex.quote(self.current_directory)} && df -kP .'
            stdin, stdout, stderr = self.client.exec_command(command, timeout=15)
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                error = stderr.read().decode('utf-8', 'ignore').strip()
                return 0, f"Помилка команди 'df': {error}" if error else f"Команда 'df' завершилась з кодом {exit_status}"

            lines = stdout.read().decode('utf-8', 'ignore').strip().splitlines()
            if len(lines) > 1:
                # Вивід: Filesystem 1024-blocks Used Available Capacity Mounted on
                parts = lines[1].split()
                if len(parts) >= 4 and parts[3].isdigit():
                    # parts[3] - це 'Available' в кілобайтах
                    return int(parts[3]) * 1024, None
            return 0, "Не вдалося розпарсити вивід команди 'df'"
        except Exception as e:
            return 0, str(e)

    def create_zip_archive(self, files, archive_name):
        if not self.client: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            # 1. Перевірка наявності утиліти zip
            if not self.check_command_exists("zip"): return False, "MISSING_ZIP"
            
            # 2. Отримання необхідного розміру
            required_size, error = self.get_remote_items_size(files)
            if error: return False, f"Не вдалося визначити розмір: {error}"

            # 3. Отримання доступного місця
            available_space, error = self.get_available_space()
            if error: return False, f"Не вдалося перевірити місце: {error}"
            
            # 4. Порівняння розмірів (з невеликим запасом 1%)
            if required_size * 1.01 > available_space:
                return False, f"INSUFFICIENT_SPACE:{required_size}"

            # 5. Створення архіву, якщо місця достатньо
            if not archive_name.lower().endswith(".zip"): archive_name += ".zip"
            command = f'cd "{self.current_directory}" && zip -r "{archive_name}" {" ".join([f"{shlex.quote(f)}" for f in files])}'
            stdin, stdout, stderr = self.client.exec_command(command); exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0: return True, lang["ARCHIVE_CREATED_SUCCESSFULLY"].format(archive_name=archive_name)
            else: return False, lang["ERROR_CREATING_ARCHIVE"].format(error=stderr.read().decode('utf-8'))
        except Exception as e: return False, lang["ERROR_CREATING_ARCHIVE"].format(error=str(e))
            
    def extract_zip_archive(self, archive_name):
        if not self.client: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            if not archive_name.lower().endswith(".zip"): return False, lang["FILE_IS_NOT_ZIP_ARCHIVE"]
            if not self.check_command_exists("unzip"): return False, "MISSING_UNZIP"
            command = f'cd "{self.current_directory}" && unzip -o "{archive_name}"'
            stdin, stdout, stderr = self.client.exec_command(command); exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0: return True, lang["ARCHIVE_EXTRACTED_SUCCESSFULLY_GENERIC"].format(archive_name=archive_name)
            else: return False, lang["ERROR_EXTRACTING_ARCHIVE"].format(error=stderr.read().decode('utf-8'))
        except Exception as e: return False, lang["ERROR_EXTRACTING_ARCHIVE"].format(error=str(e))
            
    def rename_file(self, old_name, new_name):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            old_path = old_name if old_name.startswith("/") else f"{self.current_directory}/{old_name}"
            new_path = new_name if new_name.startswith("/") else f"{self.current_directory}/{new_name}"
            self.sftp.rename(old_path, new_path); return True, lang["RENAMED_SUCCESSFULLY"]
        except Exception as e: return False, str(e)
            
    def duplicate_item(self, source_name, new_name):
        if not self.client: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            if not self.check_command_exists("cp"): return False, lang["CP_COMMAND_MISSING"]
            source_path = source_name if source_name.startswith("/") else f"{self.current_directory}/{source_name}"
            new_path = new_name if new_name.startswith("/") else f"{self.current_directory}/{new_name}"
            command = f"cp -r {shlex.quote(source_path)} {shlex.quote(new_path)}"
            stdin, stdout, stderr = self.client.exec_command(command); exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0: return True, lang["ITEM_DUPLICATED_SUCCESSFULLY"].format(source_name=source_name, new_name=new_name)
            else:
                error = stderr.read().decode('utf-8').strip() or f"Команда завершилася з кодом виходу {exit_status}"
                return False, lang["ERROR_DUPLICATING"].format(error=error)
        except Exception as e: return False, lang["ERROR_DUPLICATING"].format(error=str(e))

    def move_item(self, source_path, dest_path):
        if not self.sftp: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try: self.sftp.rename(source_path, dest_path); return True, lang["ITEM_MOVED_SUCCESSFULLY"]
        except Exception:
            self.client.get_transport().send_ignore()
            try:
                if not self.check_command_exists("mv"): return False, lang["MV_COMMAND_MISSING"]
                command = f"mv {shlex.quote(source_path)} {shlex.quote(dest_path)}"; stdin, stdout, stderr = self.client.exec_command(command)
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0: return True, lang["ITEM_MOVED_SUCCESSFULLY_SSH"]
                else: return False, lang["ERROR_SSH_MV"].format(error=stderr.read().decode('utf-8').strip())
            except Exception as ssh_e: return False, lang["ERROR_MOVING"].format(e=ssh_e)

    def copy_item(self, source_path, dest_path):
        if not self.client: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            if not self.check_command_exists("cp"): return False, lang["CP_COMMAND_MISSING"]
            command = f"cp -r {shlex.quote(source_path)} {shlex.quote(dest_path)}"; stdin, stdout, stderr = self.client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0: return True, lang["ITEM_COPIED_SUCCESSFULLY"]
            else: return False, lang["ERROR_COPYING"].format(error=stderr.read().decode('utf-8').strip())
        except Exception as e: return False, lang["ERROR_COPYING"].format(error=str(e))

    def change_group(self, filename, group_name, recursive=False):
        if not self.client: return False, lang["NOT_CONNECTED_TO_SERVER"]
        try:
            path = filename if filename.startswith("/") else f"{self.current_directory}/{filename}"
            command_parts = ['chgrp'];
            if recursive: command_parts.append('-R')
            command_parts.append(shlex.quote(group_name)); command_parts.append(shlex.quote(path)); command = ' '.join(command_parts)
            stdin, stdout, stderr = self.client.exec_command(command); exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0: return True, lang["GROUP_CHANGED_SUCCESSFULLY"]
            else:
                error = stderr.read().decode('utf-8').strip() or f"Команда завершилася з кодом виходу {exit_status}"
                return False, lang["ERROR_CHANGING_GROUP"].format(error=error)
        except Exception as e: return False, lang["ERROR_CHANGING_GROUP"].format(error=str(e))


class ServerManager:
    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager; self.servers = []; self.load_servers()
    
    # У класі ServerManager
    def get_server_credentials(self, server_name):
        """ Отримує дані сервера з JSON і додає пароль із keyring. """
        server_data = self.get_server(server_name) # Ваш існуючий метод get_server
        if not server_data:
            return None

        try:
            # Отримуємо пароль із системного сховища
            password = keyring.get_password(APP_SERVICE_NAME, server_name)
            
            # Створюємо копію, щоб не змінювати оригінальний словник
            credentials = server_data.copy()
            credentials['password'] = password
            return credentials

        except Exception as e:
            print(f"Не вдалося отримати пароль із системного сховища: {e}")
            return server_data # Повертаємо дані без пароля у разі помилки

    def load_servers(self):
        if self.settings_manager:
            if "servers" in self.settings_manager.settings: self.servers = self.settings_manager.settings["servers"]
            else: self.servers = []; self.settings_manager.settings["servers"] = self.servers
        else: self.servers = []
    
    def save_servers(self):
        if self.settings_manager: self.settings_manager.settings["servers"] = self.servers; return self.settings_manager.save_settings()
        return False
    
    # У класі ServerManager
    def add_server(self, server_data):
        # Витягуємо пароль з даних, щоб не зберігати його в JSON
        password = server_data.pop('password', None)
        server_name = server_data['name']

        # Зберігаємо або оновлюємо дані сервера (БЕЗ пароля) в списку
        server_found = False
        for i, server in enumerate(self.servers):
            if server['name'] == server_name:
                server_data['bookmarks'] = server.get('bookmarks', [])
                self.servers[i] = server_data
                server_found = True
                break
        
        if not server_found:
            self.servers.append(server_data)

        self.save_servers() # Цей метод тепер зберігає JSON без пароля

        # Якщо пароль був наданий, зберігаємо його в системному сховищі
        if password is not None:
            try:
                keyring.set_password(APP_SERVICE_NAME, server_name, password)
            except Exception as e:
                # Бажано обробити помилку, якщо keyring не працює
                print(f"Не вдалося зберегти пароль у системному сховищі: {e}")
    
    def remove_server(self, server_name):
        # Видаляємо дані сервера з JSON
        self.servers = [s for s in self.servers if s['name'] != server_name]
        self.save_servers()
        
        # Видаляємо пароль із системного сховища
        try:
            keyring.delete_password(APP_SERVICE_NAME, server_name)
        except keyring.errors.PasswordDeleteError:
            # Пароль міг бути вже видалений, це нормально
            pass
        except Exception as e:
            print(f"Помилка при видаленні пароля із системного сховища: {e}")
    
    def get_server(self, server_name):
        for server in self.servers:
            if server['name'] == server_name: return server
        return None
    
    def get_server_names(self): return [server['name'] for server in self.servers]

class GroupInfoFetcherThread(QThread):
    groups_fetched = Signal(dict)
    error = Signal(str)

    def __init__(self, ssh_client, path):
        super().__init__(); self.client = ssh_client; self.path = path

    def run(self):
        if not self.client or not self.client.get_transport() or not self.client.get_transport().is_active(): return
        try:
            cmd = f"ls -la {shlex.quote(self.path)}"; stdin, stdout, stderr = self.client.exec_command(cmd)
            ls_output = stdout.read().decode('utf-8', errors='ignore'); ls_lines = ls_output.splitlines()
            if ls_lines and ls_lines[0].startswith('total '): ls_lines = ls_lines[1:]
            groups_info = {}
            for line in ls_lines:
                parts = line.split()
                if len(parts) >= 8:
                    group = parts[3]; name = ' '.join(parts[8:])
                    if name not in ['.', '..']: groups_info[name] = group
            if groups_info: self.groups_fetched.emit(groups_info)
        except Exception as e: self.error.emit(lang["ERROR_FETCHING_GROUPS"].format(e=str(e)))


class FileTableModel(QAbstractTableModel):
    rename_failed = Signal(str, str)

    def __init__(self, parent=None, settings_manager=None, sftp_client=None, main_window=None):
        super().__init__(parent)
        self.headers = [lang["HEADER_NAME"], lang["HEADER_DATE_MODIFIED"], lang["HEADER_SIZE"], lang["HEADER_GROUP"], lang["HEADER_PERMISSIONS"]]
        self.files = []; self.icon_provider = QFileIconProvider(); self.group_animations = {}
        self.settings_manager = settings_manager; self.sftp_client = sftp_client; self.main_window = main_window
        if settings_manager:
            self.sort_column, sort_order = settings_manager.get_sort_settings()
            self.sort_order = Qt.AscendingOrder if sort_order == 0 else Qt.DescendingOrder
        else: self.sort_column = 0; self.sort_order = Qt.AscendingOrder

    def rowCount(self, parent=QModelIndex()): return len(self.files)
    def columnCount(self, parent=QModelIndex()): return len(self.headers)
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole: return self.headers[section]
            elif role == Qt.TextAlignmentRole: return Qt.AlignLeft | Qt.AlignVCenter
        return None
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.files): return None
        file = self.files[index.row()]; col = index.column(); row = index.row()
        
        if role == Qt.DisplayRole:
            if col == 0: return file['name']
            elif col == 1:
                if file['name'] == ".." and file['date_modified'] is None: return ""
                return file['date_modified'].strftime("%d.%m.%Y %H:%M")
            elif col == 2:
                if file['name'] == ".." and file['permissions'] == "": return ""
                if file['is_dir']: return "--"
                elif file['size'] >= 1024 * 1024: return f"{file['size'] / (1024 * 1024):.2f} {lang['UNIT_MB']}"
                elif file['size'] >= 1024: return f"{file['size'] / 1024:.2f} {lang['UNIT_KB']}"
                else: return f"{file['size']} {lang['UNIT_BYTES']}"
            elif col == 3:
                if file['name'] == ".." and file['permissions'] == "": return ""
                return file['group']
            elif col == 4:
                if file['name'] == ".." and file['permissions'] == "": return ""
                return file['permissions']
        elif role == Qt.EditRole and col == 0: return file['name']
        elif role == Qt.DecorationRole and col == 0:
            if file['is_dir']: return self.icon_provider.icon(QFileIconProvider.IconType.Folder)
            else:
                file_path = f"temp.{file['extension']}" if file['extension'] else "temp"
                return self.icon_provider.icon(QFileInfo(file_path))
        elif role == Qt.ForegroundRole:
            if col == 3 and row in self.group_animations: return QBrush(self.group_animations[row]['color'])
            if self.main_window and self.main_window.internal_clipboard:
                clipboard = self.main_window.internal_clipboard
                if clipboard.get("operation") == "cut":
                    if self.sftp_client and self.sftp_client.current_directory:
                        full_path = f"{self.sftp_client.current_directory}/{file['name']}".replace("//", "/")
                        if full_path in clipboard.get("items", []): return QColor("#8e9297")
        return None
    
    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit(); self.sort_column = column; self.sort_order = order
        parent_dir = None; other_files = []
        for file in self.files:
            if file['name'] == "..": parent_dir = file
            else: other_files.append(file)
        if column == 0: other_files.sort(key=lambda f: (not f['is_dir'], f['name'].lower()), reverse=(order == Qt.DescendingOrder))
        elif column == 1: other_files.sort(key=lambda f: f['date_modified'] if f['date_modified'] else datetime.min, reverse=(order == Qt.DescendingOrder))
        elif column == 2: other_files.sort(key=lambda f: f['size'], reverse=(order == Qt.DescendingOrder))
        elif column == 3: other_files.sort(key=lambda f: f['group'], reverse=(order == Qt.DescendingOrder))
        elif column == 4: other_files.sort(key=lambda f: f['permissions'], reverse=(order == Qt.DescendingOrder))
        sorted_files = [parent_dir] if parent_dir else []; sorted_files.extend(other_files); self.files = sorted_files
        self.layoutChanged.emit()
    
    def setFiles(self, files):
        self.beginResetModel()

        for anim_data in self.group_animations.values():
            anim_data['animation'].stop()
        self.group_animations.clear()

        self.files = files
        self.endResetModel()
    
    def flags(self, index):
        default_flags = super().flags(index)
        if not index.isValid():
            return default_flags
        if self.files[index.row()]['name'] == "..":
            return default_flags & ~Qt.ItemIsSelectable
        
        # Add the draggable flag for valid items
        default_flags |= Qt.ItemIsDragEnabled

        if index.column() == 0: 
            return default_flags | Qt.ItemIsEditable
        return default_flags

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not self.sftp_client or not self.sftp_client.sftp: return False
        file_info = self.files[index.row()]; old_name = file_info['name']; new_name = value.strip()
        if not new_name or new_name == old_name: return False
        self.main_window.log_event_message(lang["RENAMING_IN_PROGRESS"].format(old_name=old_name, new_name=new_name))
        success, message = self.sftp_client.rename_file(old_name, new_name)
        if success:
            self.main_window.log_event_message(lang["RENAMED_SUCCESSFULLY_LOG"].format(old_name=old_name, new_name=new_name))
            self.main_window.refresh_remote(); return True
        else: self.rename_failed.emit(old_name, message); return False

    def update_group_info(self, group_data: dict):
        try: group_column_index = self.headers.index(lang["HEADER_GROUP"])
        except ValueError: return
        for row, file_info in enumerate(self.files):
            file_name = file_info.get('name')
            if file_name in group_data and file_info.get('group') != group_data[file_name]:
                self.files[row]['group'] = group_data[file_name]; model_index = self.index(row, group_column_index)
                self.dataChanged.emit(model_index, model_index, [Qt.DisplayRole])
                if row in self.group_animations: self.group_animations[row]['animation'].stop()
                animation = QVariantAnimation(self); animation.setDuration(600); animation.setStartValue(QColor("#2f3136")); animation.setEndValue(QColor("#dcddde"))
                animation.valueChanged.connect(lambda color, r=row: self._on_group_animation_update(r, color))
                animation.finished.connect(lambda r=row: self._on_group_animation_finished(r))
                self.group_animations[row] = {'animation': animation, 'color': QColor("#2f3136")}; animation.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _on_group_animation_update(self, row, color):
        if row in self.group_animations:
            self.group_animations[row]['color'] = color; model_index = self.index(row, self.headers.index(lang["HEADER_GROUP"]))
            self.dataChanged.emit(model_index, model_index, [Qt.ItemDataRole.ForegroundRole])

    def _on_group_animation_finished(self, row):
        if row in self.group_animations:
            del self.group_animations[row]; model_index = self.index(row, self.headers.index(lang["HEADER_GROUP"]))
            self.dataChanged.emit(model_index, model_index, [Qt.ItemDataRole.ForegroundRole])

class RemoteTableView(QTableView):
    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def startDrag(self, supportedActions):
        self.start_custom_drag()

    def start_custom_drag(self):
        selected_indexes = self.selectionModel().selectedRows()
        if not selected_indexes or not self.main_window:
            return
        selected_files = [self.model().files[idx.row()] for idx in selected_indexes if self.model().files[idx.row()]['name'] != ".."]
        if not selected_files:
            return

        import tempfile
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDrag

        temp_paths = []
        urls = []
        for file_info in selected_files:
            temp_path = os.path.join(tempfile.gettempdir(), file_info['name'])
            try:
                if file_info['is_dir']:
                    os.makedirs(temp_path, exist_ok=True)
                else:
                    open(temp_path, 'w').close()
                temp_paths.append((temp_path, file_info['is_dir']))
                urls.append(QUrl.fromLocalFile(temp_path))
            except Exception:
                continue

        if not urls:
            return

        # Перевіряємо затиснуті модифікатори безпосередньо перед початком перетягування,
        # оскільки після завершення drag.exec() стан клавіш може змінитися.
        is_fast_mode = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)

        mime_data = QMimeData()
        mime_data.setUrls(urls)

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # Запускаємо перетягування (підтримуємо як копіювання, так і переміщення)
        drag.exec(Qt.CopyAction | Qt.MoveAction)

        # Оскільки Windows Explorer може повертати IgnoreAction при успішному перетягуванні локальних тимчасових файлів,
        # ми орієнтуємося на наявність відкритого Провідника/Робочого столу під курсором.
        explorer_path = self.get_explorer_path_under_cursor()
        if explorer_path and os.path.isdir(explorer_path):
            if is_fast_mode:
                # Швидке завантаження через створення та скачування архіву
                self.main_window._initiate_server_side_archiving(selected_files, explorer_path)
            else:
                # Звичайне завантаження через чергу передач
                self.main_window.download_selected_items(selected_files, preselected_dir=explorer_path)

        # Очищуємо тимчасові файли-заглушки
        for path, is_dir in temp_paths:
            try:
                if is_dir:
                    os.rmdir(path)
                else:
                    os.remove(path)
            except Exception:
                pass

    def get_explorer_path_under_cursor(self):
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        ole32 = ctypes.windll.ole32
        
        # Налаштовуємо типи аргументів та результатів для коректної роботи на 64-бітних системах
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        
        hwnd = user32.WindowFromPoint(point)
        if not hwnd:
            return None
            
        while hwnd:
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            if class_name.value in ["CabinetWClass", "ExploreWClass", "Progman", "WorkerW"]:
                break
            hwnd = user32.GetParent(hwnd)
            
        if not hwnd:
            return None
            
        ole32.CoInitialize(None)
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            windows = shell.Windows()
            
            # Якщо це робочий стіл
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            if class_name.value in ["Progman", "WorkerW"]:
                return os.path.join(os.path.expanduser("~"), "Desktop")
                
            for i in range(windows.Count):
                try:
                    window = windows.Item(i)
                    if int(window.HWND) == hwnd:
                        return window.Document.Folder.Self.Path
                except Exception:
                    continue
        except Exception:
            return None
        finally:
            ole32.CoUninitialize()
            
        return None

    def dragEnterEvent(self, event):
        # Ігноруємо перетягування всередині самої таблиці сервера
        if event.source() == self:
            event.ignore()
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # Ігноруємо перетягування всередині самої таблиці сервера
        if event.source() == self:
            event.ignore()
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self.main_window or not self.main_window.sftp_client.sftp:
            QMessageBox.warning(self, lang["ERROR"], lang["CONNECT_TO_SERVER_FIRST"])
            event.ignore()
            return
        
        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return

        is_fast_mode = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
            
        local_paths = [url.toLocalFile() for url in urls]
        if local_paths:
            self.main_window.log_event_message(lang["DRAGGED_ITEMS_FOR_UPLOAD"].format(count=len(local_paths)))
            self.main_window.upload_items_from_drop(local_paths, is_fast_mode=is_fast_mode)
            
        event.acceptProposedAction()


    
class PermissionsDialog(BaseDialog):
    def __init__(self, parent=None, current_permissions="644", is_dir=False):
        super().__init__(parent, window_title=lang["CHANGE_PERMISSIONS_TITLE"])
        self.add_title(lang["PERMISSIONS_HEADER"], icon_name="fa6s.lock", icon_color="#b9bbbe")
        form_layout = QFormLayout(); form_layout.setContentsMargins(0, 10, 0, 10); form_layout.setVerticalSpacing(15)
        self.perm_edit = QLineEdit(current_permissions); form_layout.addRow(lang["PERMISSIONS_OCTAL_LABEL"], self.perm_edit)
        self.recursive_checkbox = StyledCheckBox(lang["APPLY_RECURSIVELY_CHECKBOX"]); self.recursive_checkbox.setVisible(is_dir)
        if is_dir: form_layout.addRow("", self.recursive_checkbox)
        self.content_layout.addLayout(form_layout)
        self.footer_layout.addStretch()
        self.add_button(lang["CANCEL"], on_click=self.reject)
        self.add_button(lang["SAVE"], is_primary=True, on_click=self.accept)
    
    def get_permissions(self): return self.perm_edit.text(), self.recursive_checkbox.isChecked()

class ChangeGroupDialog(BaseDialog):
    def __init__(self, parent=None, current_group="", available_groups=[], is_dir=False):
        super().__init__(parent, window_title=lang["CHANGE_GROUP_TITLE"])
        self.add_title(lang["CHANGE_GROUP_HEADER"], icon_name="fa6s.users", icon_color="#b9bbbe")
        form_layout = QFormLayout(); form_layout.setContentsMargins(0, 10, 0, 10); form_layout.setVerticalSpacing(15)
        self.current_group_edit = QLineEdit(current_group); self.current_group_edit.setReadOnly(True)
        form_layout.addRow(lang["CURRENT_GROUP_LABEL"], self.current_group_edit)
        self.new_group_combo = QComboBox(); self.new_group_combo.setEditable(True); self.new_group_combo.addItems(available_groups)
        index = self.new_group_combo.findText(current_group)
        if index >= 0: self.new_group_combo.setCurrentIndex(index)
        else: self.new_group_combo.setEditText(current_group)
        form_layout.addRow(lang["NEW_GROUP_LABEL"], self.new_group_combo)
        self.recursive_checkbox = StyledCheckBox(lang["APPLY_RECURSIVELY_CHECKBOX"]); self.recursive_checkbox.setVisible(is_dir)
        if is_dir: form_layout.addRow("", self.recursive_checkbox)
        self.content_layout.addLayout(form_layout)
        self.footer_layout.addStretch()
        self.add_button(lang["CANCEL"], on_click=self.reject)
        self.add_button(lang["SAVE"], is_primary=True, on_click=self.accept)
    
    def get_new_group(self): return self.new_group_combo.currentText(), self.recursive_checkbox.isChecked()

class DuplicateDialog(QDialog):
    def __init__(self, parent=None, original_name=""):
        super().__init__(parent); self.setWindowTitle(lang["DUPLICATE_ITEM_TITLE"]); self.setMinimumWidth(400)
        layout = QFormLayout(self)
        self.original_name_label = QLabel(original_name); layout.addRow(lang["ORIGINAL_NAME_LABEL"], self.original_name_label)
        base, ext = os.path.splitext(original_name); timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        suggested_name = f"{base}_copy_{timestamp}{ext}"
        self.new_name_edit = QLineEdit(); self.new_name_edit.setText(suggested_name); self.new_name_edit.selectAll()
        layout.addRow(lang["NEW_NAME_LABEL"], self.new_name_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)
    
    def get_new_name(self): return self.new_name_edit.text()


class ServerDialog(QDialog):
    def __init__(self, parent=None, server_data=None):
        super().__init__(parent)
        self.setWindowTitle(lang["SERVER_SETTINGS_TITLE"])
        self.setMinimumWidth(450)

        # Додаємо атрибути для обробки пароля
        self.existing_password_placeholder = "••••••••"
        self.is_editing = server_data is not None

        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        layout.addRow(lang["SERVER_NAME_LABEL"], self.name_edit)
        self.host_edit = QLineEdit()
        layout.addRow(lang["HOST_LABEL"], self.host_edit)
        self.port_spin = StyledSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        layout.addRow(lang["PORT_LABEL"], self.port_spin)
        self.username_edit = QLineEdit()
        layout.addRow(lang["USERNAME_LABEL"], self.username_edit)

        key_layout = QHBoxLayout()
        key_layout.setContentsMargins(0, 0, 0, 0)
        self.key_path_edit = QLineEdit()
        self.key_path_edit.setPlaceholderText("Натисніть 'Огляд', щоб вибрати ключ")
        browse_button = QPushButton(lang["SETTINGS_BROWSE_BUTTON"])
        browse_button.clicked.connect(self.browse_for_key)
        key_layout.addWidget(self.key_path_edit)
        key_layout.addWidget(browse_button)
        layout.addRow(lang["SSH_KEY_LABEL"], key_layout)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        layout.addRow(lang["PASSPHRASE_LABEL"], self.password_edit)

        self.directory_edit = QLineEdit()
        self.directory_edit.setText("/")
        layout.addRow(lang["START_DIRECTORY_LABEL"], self.directory_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if server_data:
            self.name_edit.setText(server_data.get("name", ""))
            self.host_edit.setText(server_data.get("host", ""))
            self.port_spin.setValue(server_data.get("port", 22))
            self.username_edit.setText(server_data.get("username", ""))
            
            # ВИПРАВЛЕННЯ: Встановлюємо заглушку, якщо пароль існує
            if server_data.get("password"):
                self.password_edit.setText(self.existing_password_placeholder)
            else:
                self.password_edit.setText("") # Інакше поле порожнє
                
            self.directory_edit.setText(server_data.get("directory", "/"))
            self.key_path_edit.setText(server_data.get("key_filename", ""))

    # --- ДОДАНО НОВИЙ МЕТОД ---
    def browse_for_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            lang["SELECT_SSH_KEY_TITLE"],
            os.path.expanduser("~/.ssh"), # Починаємо пошук у стандартній теці SSH
            lang["SSH_KEY_FILES_FILTER"]
        )
        if file_path:
            self.key_path_edit.setText(file_path)

    def get_server_data(self):
        password = self.password_edit.text()
        
        # ВИПРАВЛЕННЯ: Додаємо логіку обробки заглушки
        # Якщо ми редагуємо і текст у полі - це наша заглушка,
        # значить користувач не змінював пароль. Повертаємо None, щоб це позначити.
        if self.is_editing and password == self.existing_password_placeholder:
            password_to_save = None  # Сигнал "не змінювати пароль"
        else:
            password_to_save = password # Інакше беремо нове значення (може бути порожнім)

        return {
            "name": self.name_edit.text(),
            "host": self.host_edit.text(),
            "port": self.port_spin.value(),
            "username": self.username_edit.text(),
            "password": password_to_save, # Передаємо оброблене значення
            "directory": self.directory_edit.text(),
            "key_filename": self.key_path_edit.text()
        }

class NoFocusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if option.state & QStyle.State_HasFocus: option.state = option.state ^ QStyle.State_HasFocus
        super().paint(painter, option, index)

class ServerListWidget(QWidget):
    server_selected = Signal(dict)

    def __init__(self, server_manager, parent=None, show_title=True):
        super().__init__(parent); self.server_manager = server_manager; layout = QVBoxLayout(self)
        if show_title: layout.setContentsMargins(1, 5, 5, 5)
        else: layout.setContentsMargins(0, 0, 0, 0)
        if show_title: title_label = QLabel(lang["SAVED_SERVERS"]); title_label.setObjectName("PanelTitle"); layout.addWidget(title_label)
        self.server_list = QListWidget(); self.server_list.setItemDelegate(NoFocusDelegate(self.server_list)); self.server_list.itemDoubleClicked.connect(self.select_server); layout.addWidget(self.server_list)
        button_layout = QHBoxLayout()
        self.add_button = QPushButton(lang["ADD"]); self.add_button.clicked.connect(self.add_server)
        self.edit_button = QPushButton(lang["EDIT"]); self.edit_button.clicked.connect(self.edit_server)
        self.remove_button = QPushButton(lang["DELETE"]); self.remove_button.clicked.connect(self.remove_server)
        self.connect_button = QPushButton(lang["CONNECT"]); self.connect_button.clicked.connect(self.select_server)
        button_layout.addWidget(self.add_button); button_layout.addWidget(self.edit_button); button_layout.addWidget(self.remove_button)
        button_layout.addStretch(); button_layout.addWidget(self.connect_button); layout.addLayout(button_layout)
        self.load_servers()

    def load_servers(self):
        self.server_list.clear(); server_icon = qta.icon("fa6s.server", color="#b9bbbe") if qta else None
        for server_name in self.server_manager.get_server_names():
            item = QListWidgetItem(server_name)
            if server_icon: item.setIcon(server_icon)
            self.server_list.addItem(item)
    
    def add_server(self, server_data):
        # Пароль тепер може бути рядком (новий/порожній) або None (без змін)
        password = server_data.pop('password', None)
        server_name = server_data['name']

        server_found = False
        for i, server in enumerate(self.servers):
            if server['name'] == server_name:
                server_data['bookmarks'] = server.get('bookmarks', [])
                self.servers[i] = server_data
                server_found = True
                break
        
        if not server_found:
            self.servers.append(server_data)

        self.save_servers()

        # ВИПРАВЛЕННЯ: Змінюємо пароль у сховищі, тільки якщо він НЕ None.
        # Якщо password - це рядок (навіть порожній), keyring буде оновлено.
        # Якщо password - це None, цей блок коду пропускається, і старий пароль залишається.
        if password is not None:
            try:
                keyring.set_password(APP_SERVICE_NAME, server_name, password)
            except Exception as e:
                print(f"Не вдалося зберегти пароль у системному сховищі: {e}")
    
    def edit_server(self):
        selected_items = self.server_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, lang["WARNING"], lang["SELECT_SERVER_TO_EDIT"])
            return
        server_name = selected_items[0].text()
        # ВИПРАВЛЕННЯ: Використовуємо get_server_credentials для отримання пароля з keyring
        server_data = self.server_manager.get_server_credentials(server_name)
        if server_data:
            dialog = ServerDialog(self, server_data=server_data)
            if dialog.exec():
                self.server_manager.add_server(dialog.get_server_data())
                self.load_servers()
    
    def remove_server(self):
        selected_items = self.server_list.selectedItems()
        if not selected_items: QMessageBox.warning(self, lang["WARNING"], lang["SELECT_SERVER_TO_DELETE"]); return
        server_name = selected_items[0].text()
        confirm = QMessageBox.question(self, lang["CONFIRM_DELETION"], lang["CONFIRM_DELETE_SERVER_PROMPT"].format(server_name=server_name),
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm == QMessageBox.Yes: self.server_manager.remove_server(server_name); self.load_servers()
    
    def select_server(self):
        selected_items = self.server_list.selectedItems()
        if not selected_items:
            if self.server_list.count() > 0: self.server_list.setCurrentRow(0); selected_items = self.server_list.selectedItems()
            else: QMessageBox.warning(self, lang["WARNING"], lang["NO_SAVED_SERVERS_TO_CONNECT"]); return
        if not selected_items: return
        server_name = selected_items[0].text(); server_data = self.server_manager.get_server(server_name)
        if server_data: self.server_selected.emit(server_data)

class ServerListDialog(QDialog):
    def __init__(self, parent=None, server_manager=None):
        super().__init__(parent); self.setWindowTitle(lang["SAVED_SERVERS"]); self.setMinimumSize(500, 400)
        self.selected_server = None; layout = QVBoxLayout(self)
        self.server_list_widget = ServerListWidget(server_manager, self, show_title=False)
        self.server_list_widget.server_selected.connect(self._on_server_selected); layout.addWidget(self.server_list_widget)
        self.close_button = QPushButton(lang["CLOSE"]); self.close_button.clicked.connect(self.reject); layout.addWidget(self.close_button)

    def _on_server_selected(self, server_data): self.selected_server = server_data; self.accept()

class BookmarkDialog(QDialog):
    def __init__(self, parent=None, path="", name=""):
        super().__init__(parent); self.setMinimumWidth(400); layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        if name: self.setWindowTitle(lang["EDIT_BOOKMARK_TITLE"]); self.name_edit.setText(name)
        else: self.setWindowTitle(lang["ADD_BOOKMARK_TITLE"]); self.name_edit.setPlaceholderText(lang["OPTIONAL_BOOKMARK_NAME_PLACEHOLDER"])
        layout.addRow(lang["NAME_LABEL"], self.name_edit)
        self.path_edit = QLineEdit(path); self.path_edit.setReadOnly(True); layout.addRow(lang["PATH_LABEL"], self.path_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)

    def get_bookmark_data(self):
        name = self.name_edit.text().strip(); path = self.path_edit.text()
        if not name:
            parts = [p for p in path.rstrip('/').split('/') if p]
            if len(parts) >= 2: name = ".../" + "/".join(parts[-2:])
            elif len(parts) == 1: name = ".../" + parts[0]
            else: name = "/"
        return {"name": name, "path": path}

# ЗАМІНІТЬ ВАШ СТАРИЙ КЛАС OverwriteDialog НА ЦЕЙ НОВИЙ КЛАС
class AdvancedOverwriteDialog(BaseDialog):
    def __init__(self, filename, source_meta, dest_meta, direction, parent=None):
        super().__init__(parent, window_title=lang["CONFIRM_OVERWRITE_TITLE"])
        self.choice = 'cancel'
        
        # --- 1. Додаємо заголовок та інформацію про файли ---
        self.add_title(lang["FILE_EXISTS_HEADER"], "fa5s.exclamation-triangle", "#faa61a")
        self.add_message(lang["FILE_EXISTS_PROMPT"].format(filename=f"<b>{filename}</b>"))
        
        # Створюємо сітку для відображення метаданих
        grid = QGridLayout()
        grid.setContentsMargins(0, 10, 0, 10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        # Заголовки таблиці
        grid.addWidget(QLabel(""), 0, 0) # Порожня клітинка
        grid.addWidget(QLabel(f"<b>{lang['HEADER_DATE_MODIFIED']}</b>"), 0, 1)
        grid.addWidget(QLabel(f"<b>{lang['HEADER_SIZE']}</b>"), 0, 2)

        is_upload = direction == 'upload'
        source_label_text = lang["DIALOG_OVERWRITE_SOURCE_LOCAL"] if is_upload else lang["DIALOG_OVERWRITE_SOURCE_SERVER"]
        dest_label_text = lang["DIALOG_OVERWRITE_SOURCE_SERVER"] if is_upload else lang["DIALOG_OVERWRITE_SOURCE_LOCAL"]
        
        # Функція для форматування
        def format_bytes(size):
            if size >= 1024 * 1024: return f"{size / (1024 * 1024):.2f} {lang['UNIT_MB']}"
            if size >= 1024: return f"{size / 1024:.2f} {lang['UNIT_KB']}"
            return f"{size} {lang['UNIT_BYTES']}"

        # Дані Джерела (Source)
        grid.addWidget(QLabel(f"<b>{source_label_text}</b>"), 1, 0)
        grid.addWidget(QLabel(datetime.fromtimestamp(source_meta['mtime']).strftime("%d.%m.%Y %H:%M:%S")), 1, 1)
        grid.addWidget(QLabel(format_bytes(source_meta['size'])), 1, 2)
        
        # Дані Призначення (Destination)
        grid.addWidget(QLabel(f"<b>{dest_label_text}</b>"), 2, 0)
        grid.addWidget(QLabel(datetime.fromtimestamp(dest_meta['mtime']).strftime("%d.%m.%Y %H:%M:%S")), 2, 1)
        grid.addWidget(QLabel(format_bytes(dest_meta['size'])), 2, 2)

        self.content_layout.addLayout(grid)
        
        # --- 2. Створюємо групу з радіокнопками ---
        options_group = QGroupBox(lang["DIALOG_OVERWRITE_SELECT_ACTION"])
        options_layout = QVBoxLayout(options_group)
        
        # Опція "Оновити"
        self.update_rb = QRadioButton(lang["DIALOG_OVERWRITE_ACTION_UPDATE"])
        options_layout.addWidget(self.update_rb)
        
        # Опція "Перезаписати"
        self.overwrite_rb = QRadioButton(lang["DIALOG_OVERWRITE_ACTION_OVERWRITE"])
        options_layout.addWidget(self.overwrite_rb)
        
        # Опція "Пропустити"
        self.skip_rb = QRadioButton(lang["DIALOG_OVERWRITE_ACTION_SKIP"])
        options_layout.addWidget(self.skip_rb)
        
        # --- 3. Логіка вибору опції за замовчуванням ---
        if source_meta['mtime'] > dest_meta['mtime']:
            self.update_rb.setChecked(True)
        else:
            self.skip_rb.setChecked(True)
            
        self.content_layout.addWidget(options_group)
        
        # --- 4. Чекбокс та кнопки ---
        self.apply_to_all_checkbox = StyledCheckBox(lang["APPLY_TO_ALL_CONFLICTS_CHECKBOX"])
        self.content_layout.addWidget(self.apply_to_all_checkbox)
        
        self.footer_layout.addStretch()
        self.add_button(lang["ABORT"], on_click=self.on_cancel)
        self.add_button(lang["OK"], is_primary=True, on_click=self.on_ok)
        
    def on_ok(self):
        if self.update_rb.isChecked(): self.choice = 'update'
        elif self.overwrite_rb.isChecked(): self.choice = 'overwrite'
        else: self.choice = 'skip'
        self.accept()

    def on_cancel(self):
        self.choice = 'cancel'
        self.reject()
        
    def get_choice(self):
        return self.choice, self.apply_to_all_checkbox.isChecked()
    
class DeleteConfirmationDialog(BaseDialog):
    def __init__(self, num_files, num_dirs, parent=None):
        super().__init__(parent, window_title=lang["CONFIRM_DELETION"])
        self.add_title(lang["DELETE_ITEMS_HEADER"], icon_name="fa6s.trash-can", icon_color="#f04747")
        message_parts = []
        if num_files > 0:
            file_str = lang["FILE_SINGULAR"] if num_files == 1 else (lang["FILE_PLURAL_2_4"] if 2 <= num_files <= 4 else lang["FILE_PLURAL_5_"])
            message_parts.append(f"<b>{num_files} {file_str}</b>")
        if num_dirs > 0:
            dir_str = lang["DIR_SINGULAR"] if num_dirs == 1 else (lang["DIR_PLURAL_2_4"] if 2 <= num_dirs <= 4 else lang["DIR_PLURAL_5_"])
            message_parts.append(f"<b>{num_dirs} {dir_str}</b>")
        self.add_message(lang["CONFIRM_PERMANENT_DELETE_PREFIX"] + lang["AND_CONJUNCTION"].join(message_parts) + "?")
        if num_dirs > 0: self.add_message(lang["DELETE_RECURSIVE_WARNING"], is_warning=True)
        self.footer_layout.addStretch()
        self.add_button(lang["CANCEL"], on_click=self.reject)
        # --- ЗМІНЕНО: Додано is_default=True ---
        self.add_button(lang["DELETE"], is_danger=True, on_click=self.accept, is_default=True)

class ReconnectSettingsDialog(QDialog):
    def __init__(self, parent=None, settings_manager=None):
        super().__init__(parent); self.setWindowTitle(lang["AUTOCONNECT_SETTINGS_TITLE"]); self.setMinimumWidth(400)
        self.settings_manager = settings_manager; layout = QFormLayout(self)
        self.enabled_checkbox = StyledCheckBox(lang["ENABLE_AUTOCONNECT_CHECKBOX"]); layout.addRow(self.enabled_checkbox)
        self.interval_spin = QSpinBox(); self.interval_spin.setRange(1, 60); self.interval_spin.setSuffix(lang["SECONDS_SUFFIX"]); layout.addRow(lang["CONNECTION_CHECK_INTERVAL_LABEL"], self.interval_spin)
        self.attempts_spin = QSpinBox(); self.attempts_spin.setRange(1, 10); self.attempts_spin.setSuffix(lang["ATTEMPTS_SUFFIX"]); layout.addRow(lang["MAX_ATTEMPTS_LABEL"], self.attempts_spin)
        self.help_text = QLabel(lang["AUTOCONNECT_HELP_TEXT"]); self.help_text.setWordWrap(True); layout.addRow(self.help_text)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)
        if settings_manager:
            reconnect_settings = settings_manager.get_reconnect_settings()
            self.enabled_checkbox.setChecked(reconnect_settings["enabled"]); self.interval_spin.setValue(reconnect_settings["interval"]); self.attempts_spin.setValue(reconnect_settings["max_attempts"])
    
    def accept(self):
        if self.settings_manager: self.settings_manager.set_reconnect_settings(self.enabled_checkbox.isChecked(), self.interval_spin.value(), self.attempts_spin.value())
        super().accept()

# Додайте цей клас у ваш код
class PasswordPromptDialog(BaseDialog):
    def __init__(self, server_name, parent=None):
        super().__init__(parent, window_title=lang["PASSWORD_LABEL"])
        
        # Використовуємо ваш кастомний метод для заголовка
        self.add_title(lang["PASSWORD_LABEL"], icon_name="fa6s.key", icon_color="#b9bbbe")

        # Створюємо віджети
        prompt_label = QLabel(lang["PASSWORD_LABEL"] + f" для '<b>{server_name}</b>':")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        # Додаємо віджети в основний лейаут
        self.content_layout.addWidget(prompt_label)
        self.content_layout.addWidget(self.password_edit)

        # Налаштовуємо кнопки у футері
        self.footer_layout.addStretch()
        self.add_button(lang["CANCEL"], on_click=self.reject)
        ok_button = self.add_button(lang["OK"], is_primary=True, on_click=self.accept)
        
        # Робимо кнопку "ОК" кнопкою за замовчуванням
        ok_button.setDefault(True)
        # Встановлюємо фокус на поле вводу
        self.password_edit.setFocus()

    def get_password(self):
        """ Повертає введений пароль. """
        return self.password_edit.text()

class SearchDialog(QDialog):
    file_open_requested = Signal(str)
    def __init__(self, parent=None, search_path=""):
        super().__init__(parent); self.setWindowTitle(lang["SEARCH_FILES_TITLE"]); self.setMinimumSize(600, 400)
        self.base_path = search_path; self.search_thread = None; layout = QVBoxLayout(self); layout.setContentsMargins(10, 10, 10, 10); layout.setSpacing(10)
        settings_group = QGroupBox(lang["SEARCH_PARAMETERS_GROUP"]); form_layout = QFormLayout(settings_group)
        self.path_label = QLabel(f"<b>{search_path}</b>"); self.path_label.setWordWrap(True); form_layout.addRow(lang["SEARCH_IN_DIRECTORY_LABEL"], self.path_label)
        self.query_edit = QLineEdit(); self.query_edit.setPlaceholderText(lang["SEARCH_QUERY_PLACEHOLDER"]); form_layout.addRow(lang["FIND_LABEL"], self.query_edit)
        self.case_checkbox = StyledCheckBox(lang["IGNORE_CASE_CHECKBOX"]); self.case_checkbox.setChecked(True); form_layout.addRow(self.case_checkbox); layout.addWidget(settings_group)
        button_layout = QHBoxLayout(); self.find_by_name_button = QPushButton(lang["SEARCH_BY_NAME_BUTTON"]); self.find_by_content_button = QPushButton(lang["SEARCH_BY_CONTENT_BUTTON"])
        button_layout.addWidget(self.find_by_name_button); button_layout.addWidget(self.find_by_content_button); layout.addLayout(button_layout)
        results_group = QGroupBox(lang["RESULTS_GROUP"]); results_layout = QVBoxLayout(results_group)
        self.results_list = QListWidget(); self.results_list.setObjectName("SearchResultsList")
        self.results_list.setStyleSheet("QListWidget#SearchResultsList::item {padding:5px;border-bottom:1px solid #40444b;} QListWidget#SearchResultsList::item:last-child {border-bottom:none;}")
        self.status_label = QLabel(lang["READY_TO_SEARCH_STATUS"]); results_layout.addWidget(self.results_list); results_layout.addWidget(self.status_label); layout.addWidget(results_group)
        close_button_layout = QHBoxLayout(); close_button_layout.addStretch(); self.close_button = QPushButton(lang["CLOSE"]); close_button_layout.addWidget(self.close_button); layout.addLayout(close_button_layout)
        self.find_by_name_button.clicked.connect(lambda: self.start_search('name')); self.find_by_content_button.clicked.connect(lambda: self.start_search('content'))
        self.close_button.clicked.connect(self.reject); self.query_edit.returnPressed.connect(self.find_by_name_button.click); self.results_list.itemDoubleClicked.connect(self.open_selected_file)

    def start_search(self, search_type):
        query = self.query_edit.text()
        if not query: QMessageBox.warning(self, lang["SEARCH"], lang["SEARCH_FIELD_CANNOT_BE_EMPTY"]); return
        self.results_list.clear(); self.set_buttons_enabled(False); self.status_label.setText(lang["SEARCHING_STATUS"])
        self.parent().start_search(self, query, search_type, self.case_checkbox.isChecked())
    
    def set_buttons_enabled(self, enabled):
        self.find_by_name_button.setEnabled(enabled); self.find_by_content_button.setEnabled(enabled); self.query_edit.setEnabled(enabled)
    def add_result(self, path): self.results_list.addItem(f".../{path}")
    def on_search_complete(self, count):
        self.status_label.setText(lang["SEARCH_COMPLETE_STATUS"].format(count=count)); self.set_buttons_enabled(True); self.search_thread = None
    def on_search_error(self, message):
        self.status_label.setText(lang["ERROR_STATUS"].format(message=message)); self.set_buttons_enabled(True); self.search_thread = None
    def reject(self):
        if self.search_thread and self.search_thread.isRunning(): self.search_thread.cancel(); self.search_thread.wait(1000)
        super().reject()
    def open_selected_file(self, item):
        display_path = item.text(); relative_path = display_path[4:] if display_path.startswith('.../') else display_path
        full_path = f"{self.base_path.rstrip('/')}/{relative_path}"; self.file_open_requested.emit(full_path)

class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_manager=None):
        super().__init__(parent)
        self.setWindowTitle(lang["MAINWINDOW_MENU_SETTINGS"])
        self.setMinimumWidth(500)
        self.settings_manager = settings_manager
        self.tab_widget = QTabWidget()
        self.create_general_tab()
        self.create_files_tab()
        self.create_transfers_tab()
        self.create_reconnect_tab()
        layout = QVBoxLayout(self)
        layout.addWidget(self.tab_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.save_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def create_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 15, 0, 15)

        editor_group = QGroupBox(lang["SETTINGS_EDITOR_GROUP"])
        editor_layout = QFormLayout(editor_group)
        self.editor_path = QLineEdit()
        self.editor_path.setText(self.settings_manager.get_editor_path())
        browse_button = QPushButton(lang["SETTINGS_BROWSE_BUTTON"])
        browse_button.clicked.connect(self.browse_editor)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.editor_path)
        path_layout.addWidget(browse_button)
        editor_layout.addRow(lang["SETTINGS_EDITOR_PATH_LABEL"], path_layout)
        editor_help = QLabel(lang["SETTINGS_EDITOR_HELP"])
        editor_help.setWordWrap(True)
        editor_layout.addRow(editor_help)
        layout.addWidget(editor_group)

        # Блок для вибору мови
        language_group = QGroupBox(lang.get("SETTINGS_LANGUAGE_GROUP", "Language")) # Використовуємо .get для сумісності
        lang_layout = QFormLayout(language_group)
        
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(lang.get("SETTINGS_LANG_NAME_EN", "English"), "en")
        self.lang_combo.addItem(lang.get("SETTINGS_LANG_NAME_UA", "Українська"), "ua")
        
        # Встановлюємо поточну мову
        current_lang_code = self.settings_manager.get_language()
        index = self.lang_combo.findData(current_lang_code)
        if index != -1:
            self.lang_combo.setCurrentIndex(index)
            
        lang_layout.addRow(lang.get("SETTINGS_LANGUAGE_LABEL", "Interface language:"), self.lang_combo)
        lang_help = QLabel(lang.get("SETTINGS_LANGUAGE_HELP", "Changing the language requires an application restart to take effect."))
        lang_help.setWordWrap(True)
        lang_layout.addRow(lang_help)
        
        layout.addWidget(language_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, lang["SETTINGS_TAB_GENERAL"])

    def create_files_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        files_group = QGroupBox(lang["SETTINGS_FILES_GROUP"])
        layout.setContentsMargins(0, 15, 0, 15)
        files_layout = QFormLayout(files_group)
        self.show_hidden_checkbox = StyledCheckBox(lang["MAINWINDOW_MENU_SHOW_HIDDEN"])
        self.show_hidden_checkbox.setChecked(self.settings_manager.get_show_hidden())
        files_layout.addRow(self.show_hidden_checkbox)
        hidden_help = QLabel(lang["SETTINGS_HIDDEN_FILES_HELP"])
        hidden_help.setWordWrap(True)
        files_layout.addRow(hidden_help)
        
        self.sync_ignored_patterns_edit = QLineEdit()
        patterns = self.settings_manager.get_sync_ignored_patterns()
        self.sync_ignored_patterns_edit.setText(", ".join(patterns))
        files_layout.addRow(lang.get("SETTINGS_SYNC_IGNORED_PATTERNS_LABEL", "Sync ignored patterns:"), self.sync_ignored_patterns_edit)
        
        ignored_help = QLabel(lang.get("SETTINGS_SYNC_IGNORED_HELP", "Comma-separated patterns to ignore during folder sync (e.g., .git, .env, node_modules)."))
        ignored_help.setWordWrap(True)
        files_layout.addRow(ignored_help)
        
        layout.addWidget(files_group)
        layout.addStretch()
        self.tab_widget.addTab(tab, lang["SETTINGS_TAB_FILES"])

    # У класі SettingsDialog, замініть цей метод
    def create_transfers_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 15, 0, 15)

        # --- ЗМІНЕНО: Група тепер налаштовує стелю для адаптивного режиму ---
        transfers_group = QGroupBox(lang["SETTINGS_ADAPTIVE_MODE_GROUP"])
        transfers_layout = QFormLayout(transfers_group)
        
        self.max_transfers_spin = StyledSpinBox()
        # Новий діапазон: від 2 до 100. Значення 0 (старий авто-режим) більше не потрібне.
        self.max_transfers_spin.setRange(2, 100)
        
        current_val = self.settings_manager.get_max_concurrent_transfers()
        # Якщо стоїть старе значення "0" або "1", встановлюємо розумний дефолт (напр., 20)
        if current_val < 2:
            current_val = 20
        self.max_transfers_spin.setValue(current_val)

        transfers_layout.addRow(lang["SETTINGS_ADAPTIVE_CEILING_LABEL"], self.max_transfers_spin)
        transfers_help = QLabel(lang["SETTINGS_ADAPTIVE_CEILING_HELP"])
        transfers_help.setWordWrap(True)
        transfers_layout.addRow(transfers_help)
        layout.addWidget(transfers_group)
        # --- КІНЕЦЬ ЗМІН ---

        # Існуюча група для обмеження швидкості залишається без змін
        speed_group = QGroupBox(lang["SETTINGS_SPEED_LIMIT_GROUP"])
        speed_layout = QFormLayout(speed_group)
        current_limits = self.settings_manager.get_speed_limit_settings()
        self.speed_limit_enabled_check = StyledCheckBox(lang["SETTINGS_SPEED_LIMIT_ENABLE"])
        self.speed_limit_enabled_check.setChecked(current_limits["enabled"])
        speed_layout.addRow(self.speed_limit_enabled_check)
        self.upload_limit_spin = StyledSpinBox()
        self.upload_limit_spin.setRange(0, 100000)
        self.upload_limit_spin.setValue(current_limits["upload_kbps"])
        self.upload_limit_spin.setSuffix(lang["KBPS_SUFFIX"])
        speed_layout.addRow(lang["SETTINGS_UPLOAD_LIMIT_LABEL"], self.upload_limit_spin)
        self.download_limit_spin = StyledSpinBox()
        self.download_limit_spin.setRange(0, 100000)
        self.download_limit_spin.setValue(current_limits["download_kbps"])
        self.download_limit_spin.setSuffix(lang["KBPS_SUFFIX"])
        speed_layout.addRow(lang["SETTINGS_DOWNLOAD_LIMIT_LABEL"], self.download_limit_spin)
        
        def toggle_controls(enabled):
            self.upload_limit_spin.setEnabled(enabled)
            self.download_limit_spin.setEnabled(enabled)
        
        self.speed_limit_enabled_check.toggled.connect(toggle_controls)
        toggle_controls(current_limits["enabled"])
        
        layout.addWidget(speed_group)
        layout.addStretch()
        # --- ВИПРАВЛЕНО ТИПОДРУК: 'TRANSfers' -> 'TRANSFERS' ---
        self.tab_widget.addTab(tab, lang["SETTINGS_TAB_TRANSFERS"])

    def create_reconnect_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        reconnect_group = QGroupBox(lang["SETTINGS_RECONNECT_GROUP"])
        layout.setContentsMargins(0, 15, 0, 15)
        reconnect_layout = QFormLayout(reconnect_group)
        reconnect_settings = self.settings_manager.get_reconnect_settings()
        self.reconnect_enabled = StyledCheckBox(lang["ENABLE_AUTOCONNECT_CHECKBOX"])
        self.reconnect_enabled.setChecked(reconnect_settings["enabled"])
        reconnect_layout.addRow(self.reconnect_enabled)
        self.reconnect_interval = StyledSpinBox()
        self.reconnect_interval.setRange(1, 60)
        self.reconnect_interval.setValue(reconnect_settings["interval"])
        self.reconnect_interval.setSuffix(lang["SECONDS_SUFFIX"])
        reconnect_layout.addRow(lang["CONNECTION_CHECK_INTERVAL_LABEL"], self.reconnect_interval)
        self.reconnect_attempts = StyledSpinBox()
        self.reconnect_attempts.setRange(1, 10)
        self.reconnect_attempts.setValue(reconnect_settings["max_attempts"])
        self.reconnect_attempts.setSuffix(lang["ATTEMPTS_SUFFIX"])
        reconnect_layout.addRow(lang["MAX_ATTEMPTS_LABEL"], self.reconnect_attempts)
        reconnect_help = QLabel(lang["AUTOCONNECT_HELP_TEXT"])
        reconnect_help.setWordWrap(True)
        reconnect_layout.addRow(reconnect_help)
        layout.addWidget(reconnect_group)
        layout.addStretch()
        self.tab_widget.addTab(tab, lang["SETTINGS_TAB_AUTOCONNECT"])

    def browse_editor(self):
        file_path, _ = QFileDialog.getOpenFileName(self, lang["SETTINGS_SELECT_EDITOR_TITLE"], os.path.expanduser("~"),
            lang["SETTINGS_EXECUTABLE_FILES_FILTER"] if sys.platform == "win32" else lang["SETTINGS_ALL_FILES_FILTER"])
        if file_path:
            self.editor_path.setText(file_path)

    def save_settings(self):
        old_lang = self.settings_manager.get_language()
        
        self.settings_manager.set_editor_path(self.editor_path.text())
        self.settings_manager.set_show_hidden(self.show_hidden_checkbox.isChecked())
        
        patterns_text = self.sync_ignored_patterns_edit.text()
        patterns = [p.strip() for p in patterns_text.split(",") if p.strip()]
        self.settings_manager.set_sync_ignored_patterns(patterns)
        
        self.settings_manager.set_max_concurrent_transfers(self.max_transfers_spin.value())
        self.settings_manager.set_reconnect_settings(self.reconnect_enabled.isChecked(), self.reconnect_interval.value(), self.reconnect_attempts.value())
        self.settings_manager.set_speed_limit_settings(self.speed_limit_enabled_check.isChecked(), self.upload_limit_spin.value(), self.download_limit_spin.value())
        new_lang = self.lang_combo.currentData()
        self.settings_manager.set_language(new_lang)

        if old_lang != new_lang:
            QMessageBox.information(self, 
                                    lang.get("RESTART_REQUIRED_TITLE", "Restart Required"), 
                                    lang.get("RESTART_REQUIRED_PROMPT", "The language has been changed. Please restart the application for the changes to take full effect."))

        self.accept()

class BreadcrumbBar(QWidget):
    path_clicked = Signal(str)
    switch_to_edit = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(2, 0, 0, 0)  # Reduced margins
        self.layout.setSpacing(1)  # Minimal spacing between elements
        self.layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # Left align the content
        self.current_path = "/"
        self.setCursor(Qt.IBeamCursor)
        # Set reasonable maximum width to prevent layout stretching
        self.setMaximumWidth(800)  # Maximum reasonable width for path display
        self._last_width = 0

    def set_path(self, path):
        self.current_path = path
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        parts = [p for p in path.split('/') if p]
        
        root_btn = QPushButton("/")
        root_btn.setFlat(True)
        root_btn.setCursor(Qt.PointingHandCursor)
        root_btn.clicked.connect(lambda: self.path_clicked.emit("/"))
        root_btn.setStyleSheet("""
            QPushButton { 
                text-align: left; 
                padding: 0px 2px; 
                border-radius: 2px; 
                color: #b9bbbe;
                font-weight: bold;
                border: 1px solid transparent;
                background: transparent;
                margin: 0px;
                font-size: 11px;
            } 
            QPushButton:hover { 
                background-color: rgba(255, 255, 255, 0.1); 
            }
        """)
        self.layout.addWidget(root_btn)

        if not parts:
            return

        # Adaptive logic: calculate actual widths and show as many segments as possible
        # Never truncate individual directory names
        metrics = self.fontMetrics()
        
        def calculate_width(text):
            return metrics.horizontalAdvance(text) + 8  # Reduced padding for more compact display
        
        sep_width = calculate_width("›") + 2  # Reduced separator spacing
        root_width = calculate_width("/")
        dots_width = calculate_width("...")
        
        # Calculate available width (be more aggressive with space usage)
        available_width = max(self.width() - 10, 80)
        
        # Start with showing all parts
        display_parts = parts
        truncated_prefix = False
        
        # Calculate total width if we show all parts
        total_width = root_width
        part_widths = []
        for part in parts:
            part_width = sep_width + calculate_width(part)
            part_widths.append(part_width)
            total_width += part_width
        
        # If all parts fit, show them all
        if total_width <= available_width:
            display_parts = parts
            truncated_prefix = False
        else:
            # Need to truncate from the beginning
            # Start from the end and add as many as we can fit
            display_parts = []
            truncated_prefix = True
            current_width = root_width + dots_width  # root + "..." button
            
            # Add parts from the end until we run out of space
            for i in range(len(parts) - 1, -1, -1):
                part_width = part_widths[i]
                if current_width + part_width <= available_width:
                    display_parts.insert(0, parts[i])
                    current_width += part_width
                else:
                    break
            
            # If we couldn't fit any parts, at least show the last one
            if not display_parts and parts:
                display_parts = [parts[-1]]
            
            # Add "..." indicator with full path tooltip
            prefix_parts = parts[:-len(display_parts)] if display_parts else parts
            prefix_path = "/" + "/".join(prefix_parts) if prefix_parts else "/"
            dots_btn = QPushButton("...")
            dots_btn.setFlat(True)
            dots_btn.setCursor(Qt.PointingHandCursor)
            dots_btn.setToolTip(prefix_path)
            dots_btn.setStyleSheet("""
                QPushButton { 
                    text-align: left; 
                    padding: 1px 3px; 
                    border-radius: 3px; 
                    color: #72767d;
                    font-weight: bold;
                    border: 1px solid transparent;
                    background: transparent;
                    margin: 0px;
                } 
                QPushButton:hover { 
                    background-color: rgba(255, 255, 255, 0.1); 
                    color: #b9bbbe;
                }
            """)
            self.layout.addWidget(dots_btn)
        
        cumulative_path = "/"
        for i, part in enumerate(display_parts):
            sep = QLabel("›")
            sep.setStyleSheet("color: #72767d; font-weight: bold; margin: 0; font-size: 11px;")
            self.layout.addWidget(sep)
            
            if truncated_prefix:
                actual_parts = parts[:len(parts)-len(display_parts)] + display_parts[:i+1]
                cumulative_path = "/" + "/".join(actual_parts)
            else:
                if cumulative_path == "/":
                    cumulative_path += part
                else:
                    cumulative_path += "/" + part

            btn = QPushButton(part)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(part)
            btn.clicked.connect(lambda checked=False, p=cumulative_path: self.path_clicked.emit(p))
            btn.setStyleSheet("""
                QPushButton { 
                    text-align: left; 
                    padding: 0px 2px; 
                    border-radius: 2px; 
                    color: #b9bbbe;
                    border: 1px solid transparent;
                    background: transparent;
                    margin: 0px;
                    font-size: 11px;
                } 
                QPushButton:hover { 
                    background-color: rgba(255, 255, 255, 0.1); 
                }
            """)
            self.layout.addWidget(btn)

    def resizeEvent(self, event):
        # Redraw if width changed to adapt to new available space
        # Use smaller threshold (20px) for more responsive behavior
        if abs(event.size().width() - self._last_width) > 20:
            self._last_width = event.size().width()
            if self.current_path is not None:
                self.set_path(self.current_path)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        self.switch_to_edit.emit()
        super().mousePressEvent(event)
        
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(lang["MAINWINDOW_TITLE"])

        try:
            icon_path = resource_path("icon.png")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(lang["MAINWINDOW_ICON_WARNING"].format(e=e))
            
        self.resize(1200, 800)
        
        self.settings_manager = JsonSettingsManager()
        self.sftp_client = SFTPClient()
        self.server_manager = ServerManager(self.settings_manager)
        
        self.sftp_lock = threading.Lock()
        # ДОДАЙТЕ ЦІ РЯДКИ
        self.dir_history = []
        self.dir_history_index = -1
        self.is_navigating_history = False
        # КІНЕЦЬ ДОДАВАННЯ
        self.initial_sort_applied = False
        self.edited_files = {}
        self.file_watcher = QFileSystemWatcher()
        self.last_save_timestamps = {}
        self.reconnect_timer = QTimer(self)
        self.reconnect_attempt_count = 0
        self.is_reconnecting = False
        self.pending_uploads = []
        
        self.transfer_tasks = {}
        self.active_file_transfers = {}
        self.transfer_queue = []
        self.adaptive_manager = None 
        self.fixed_mode_banner_errors = 0
        self.fallback_to_adaptive_triggered = False
        self.worker_threads = []
        
        self.overwrite_action = None
        self.file_to_edit_after_refresh = None
        self.internal_clipboard = {}
        self.group_fetcher_thread = None
        self.search_thread = None
        
        self.dir_operation_thread = None
        self.next_operation_on_finish = None
        self.active_bookmark_navigation = None
        self.active_search_threads = {}
        self.startup_cleanup_thread = None

        # --- Створення UI ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0,0,0,0)
        
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.left_splitter = QSplitter(Qt.Vertical)
        
        self.transfers_panel = TransfersPanel()
        self.event_log_widget = LogWidget(lang["MAINWINDOW_EVENT_LOG_TITLE"])
        self.left_splitter.addWidget(self.transfers_panel)
        self.left_splitter.addWidget(self.event_log_widget)
        self.left_splitter.setSizes([int(self.height() * 0.4), int(self.height() * 0.6)])
        
        # --- Створення віджета для файлового браузера (Сторінка 1) ---
        self.remote_widget = QWidget()
        remote_layout = QVBoxLayout(self.remote_widget)
        remote_layout.setContentsMargins(1, 5, 5, 5)
        remote_layout.setSpacing(5)
        
        self.remote_path_edit = QLineEdit()
        
        # --- BREADCRUMB SETUP ---
        self.path_stack = QStackedWidget()
        self.path_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.path_stack.setFixedHeight(28)
        
        self.breadcrumb_container = QWidget()
        self.breadcrumb_container.setObjectName("breadcrumbContainer")
        self.breadcrumb_container.setFixedHeight(28)
        self.breadcrumb_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)  # Don't force horizontal expansion
        self.breadcrumb_container.setStyleSheet("""
            #breadcrumbContainer {
                background-color: #36393f;
                border: 1px solid #40444b;
                border-radius: 4px;
            }
        """)
        bc_layout = QVBoxLayout(self.breadcrumb_container)
        bc_layout.setContentsMargins(2, 2, 2, 2)
        self.breadcrumb_bar = BreadcrumbBar()
        self.breadcrumb_bar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # Don't affect layout width
        bc_layout.addWidget(self.breadcrumb_bar)
        self.path_stack.addWidget(self.breadcrumb_container)
        self.path_stack.addWidget(self.remote_path_edit)
        
        # Signals
        self.breadcrumb_bar.path_clicked.connect(self.navigate_via_breadcrumbs)
        self.breadcrumb_bar.switch_to_edit.connect(self.enable_path_edit_mode)
        self.remote_path_edit.editingFinished.connect(self.disable_path_edit_mode)
        # --- END BREADCRUMB SETUP ---

        self.bookmark_action_button = QPushButton()
        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0,0,0,0)
        path_layout.setSpacing(5)

        if qta:
            self.back_button = QPushButton(qta.icon("fa6s.arrow-left", color="#b9bbbe"), "")
            self.forward_button = QPushButton(qta.icon("fa6s.arrow-right", color="#b9bbbe"), "")
        else:
            self.back_button = QPushButton("<-")
            self.forward_button = QPushButton("->")

        self.back_button.setToolTip(lang["HISTORY_BACK"]) # ВИКОРИСТОВУЄМО ПЕРЕКЛАД
        self.back_button.setFixedSize(28, 28)
        self.back_button.setEnabled(False)

        self.forward_button.setToolTip(lang["HISTORY_FORWARD"]) # ВИКОРИСТОВУЄМО ПЕРЕКЛАД
        self.forward_button.setFixedSize(28, 28)
        self.forward_button.setEnabled(False)

        # Додаємо нові кнопки на панель
        path_layout.addWidget(self.back_button)
        path_layout.addWidget(self.forward_button)
        # --- КІНЕЦЬ ДОДАВАННЯ --

        path_layout.addWidget(self.path_stack)
        path_layout.addWidget(self.bookmark_action_button)
        remote_layout.addLayout(path_layout)
        
        self.remote_model = FileTableModel(
            settings_manager=self.settings_manager,
            sftp_client=self.sftp_client,
            main_window=self
        )
        self.remote_table = RemoteTableView(main_window=self)
        self.remote_table.setItemDelegate(NoFocusDelegate(self.remote_table))
        self.remote_table.setModel(self.remote_model)
        
        remote_layout.addWidget(self.remote_table)
        
        # --- Створення віджета зі списком серверів (Сторінка 2) ---
        self.server_list_widget = ServerListWidget(self.server_manager)
        
        # --- Створення QStackedWidget для перемикання ---
        self.right_panel_stack = QStackedWidget()
        self.right_panel_stack.addWidget(self.remote_widget)
        self.right_panel_stack.addWidget(self.server_list_widget)

        # --- Додавання елементів у головний спліттер ---
        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_panel_stack)
        self.main_splitter.setSizes([350, 850])
        
        self.main_layout.addWidget(self.main_splitter)

        # --- Встановлюємо початковий вигляд (список серверів) ---
        self.right_panel_stack.setCurrentWidget(self.server_list_widget)
        
        self.setup_ui_components()
        self.create_actions()
        self.create_menus()
        self.connect_signals()
        self.update_action_states()
        self.log_event_message(lang["MAINWINDOW_READY"])
        QTimer.singleShot(500, self.restore_last_session)
        QTimer.singleShot(1000, self.check_for_updates_silently)

    def _generate_smart_task_name(self, selected_items, prefix):
        """Генерує інформативний заголовок для завдання на основі обраних елементів."""
        count = len(selected_items)
        if count == 0:
            return prefix

        # Для списку рядків (шляхів) отримуємо базові імена
        if isinstance(selected_items[0], str):
            first_item_name = os.path.basename(selected_items[0])
        # Для списку словників (інформації про файли) беремо з ключа 'name'
        else:
            first_item_name = selected_items[0]['name']

        if count == 1:
            return lang["TASK_NAME_SINGLE"].format(prefix=prefix, name=first_item_name)
        else:
            more_count = count - 1
            return lang["TASK_NAME_MULTIPLE"].format(prefix=prefix, name=first_item_name, more_count=more_count)

    def _handle_upload_scan_complete(self, task_id, files_found, dirs_to_create):
        task = self.transfer_tasks.get(task_id)
        if not task: return

        if not files_found and not dirs_to_create: 
            self.log_event_message(lang["MAINWINDOW_NO_FILES_TO_TRANSFER"].format(name=task['name']))
            self.transfers_panel.complete_transfer(task_id, True, lang["MAINWINDOW_NO_FILES"])
            if task_id in self.transfer_tasks: del self.transfer_tasks[task_id]
            return

        if dirs_to_create:
            self.transfers_panel.set_task_indeterminate(task_id, lang["MAINWINDOW_CREATING_DIRS_ON_SERVER"])
            dir_thread = DirectoryCreationThread(
                self.sftp_client.client, 
                task['remote_base_path'], 
                dirs_to_create, 
                files_found
            )
            dir_thread.creation_complete.connect(lambda files: self.start_conflict_resolution(task_id, files))
            dir_thread.error.connect(self.handle_scan_error)
            dir_thread.finished.connect(dir_thread.deleteLater)
            self.worker_threads.append(dir_thread)
            dir_thread.start()
        else:
            # Якщо папок для створення немає, одразу переходимо до перевірки конфліктів
            self.start_conflict_resolution(task_id, files_found)

    def _fallback_to_standard_download(self, selected_files, destination_dir):
        """Запускає стандартне (пофайлове) скачування."""
        self.log_event_message(lang["MAINWINDOW_INSUFFICIENT_SPACE_LOG"].format(required_space="..."))
        # Просто викликаємо існуючий метод, який вже вміє обробляти такі завдання
        self.download_selected_items(selected_files)

    # Додайте цей новий метод у клас MainWindow
    def _post_connection_setup(self, restore_session=False):
        """Виконує дії після підключення та завершення всіх попередніх завдань (як очищення)."""
        path_to_load = None
        if restore_session and hasattr(self, 'auto_restore_remote_dir') and self.auto_restore_remote_dir:
            path_to_load = self.auto_restore_remote_dir
            self.auto_restore_remote_dir = None

        if path_to_load and path_to_load != self.sftp_client.current_directory:
            self.remote_table.setEnabled(False)
            self.setCursor(Qt.WaitCursor)
            self.dir_operation_thread = DirectoryOperationThread(self.sftp_client, self.sftp_lock, 'chdir', path=path_to_load)
            self.dir_operation_thread.change_dir_complete.connect(self._handle_change_dir_complete)
            self.dir_operation_thread.error.connect(self._handle_operation_error)
            self.dir_operation_thread.finished.connect(self._on_dir_operation_finished)
            self.dir_operation_thread.start()
        else:
            self.load_remote_files()

        self.update_bookmark_button_status()
        server_name = self.sftp_client.connection_details.get('name')
        if server_name:
            self.settings_manager.set_last_session(server_name, self.sftp_client.current_directory)
        self.start_connection_check()

    def run_pending_cleanup(self, server_name, on_finish_callback):
        """Запускає очищення і викликає on_finish_callback після завершення."""
        files_to_delete = self.settings_manager.get_pending_cleanup_files(server_name)
        
        if not files_to_delete:
            # Якщо файлів для очищення немає, одразу викликаємо функцію
            on_finish_callback()
            return

        self.log_event_message(lang["MAINWINDOW_CLEANUP_FOUND_FILES"].format(count=len(files_to_delete)))

        class CleanupThread(QThread):
            def __init__(self, sftp_client, settings_manager, server, files):
                super().__init__()
                self.sftp = sftp_client; self.settings = settings_manager;
                self.server_name = server; self.files = list(files)
            
            def run(self):
                for path in self.files:
                    success, msg = self.sftp.delete_file(path)
                    if success:
                        print(lang["MAINWINDOW_CLEANUP_SUCCESS"].format(path=path))
                        self.settings.remove_pending_cleanup_file(self.server_name, path)
                    else:
                        if "No such file" in msg:
                            print(lang["MAINWINDOW_CLEANUP_FILE_NOT_EXISTS"].format(path=path))
                            self.settings.remove_pending_cleanup_file(self.server_name, path)
                        else:
                            print(lang["MAINWINDOW_CLEANUP_ERROR"].format(path=path, msg=msg))

        self.cleanup_thread = CleanupThread(self.sftp_client, self.settings_manager, server_name, files_to_delete)
        # ПІДПИСУЄМОСЯ НА СИГНАЛ ЗАВЕРШЕННЯ ПОТОКУ
        self.cleanup_thread.finished.connect(on_finish_callback)
        self.cleanup_thread.finished.connect(self.refresh_remote) # оновлення списку файлів все ще потрібне
        self.cleanup_thread.start()
    


    def load_remote_files(self):
        if not self.sftp_client.sftp: return

        if self.dir_operation_thread and self.dir_operation_thread.isRunning():
            return

        self.remote_table.setEnabled(False)
        self.setCursor(Qt.WaitCursor)
        self.log_event_message(lang["MAINWINDOW_REFRESHING_FILE_LIST"])

        self.dir_operation_thread = DirectoryOperationThread(self.sftp_client, self.sftp_lock, 'list')
        self.dir_operation_thread.list_complete.connect(self._handle_list_complete)
        self.dir_operation_thread.error.connect(self._handle_operation_error)
        self.dir_operation_thread.finished.connect(self._on_dir_operation_finished)
        self.dir_operation_thread.start()

    def _handle_list_complete(self, files):
        try:
            self.remote_model.setFiles(files)
            self.apply_saved_sort()
            self.update_remote_path_label()

            if self.group_fetcher_thread and self.group_fetcher_thread.isRunning():
                self.group_fetcher_thread.terminate()
                self.group_fetcher_thread.wait()
            
            self.group_fetcher_thread = GroupInfoFetcherThread(self.sftp_client.client, self.sftp_client.current_directory)
            self.group_fetcher_thread.groups_fetched.connect(self.remote_model.update_group_info)
            self.group_fetcher_thread.error.connect(lambda msg: self.log_event_message(f"<span style='color: #faa61a;'>{msg}</span>"))
            self.group_fetcher_thread.start()

            if self.file_to_edit_after_refresh:
                for row in range(self.remote_model.rowCount()):
                    index = self.remote_model.index(row, 0)
                    if index.data() == self.file_to_edit_after_refresh:
                        self.remote_table.setCurrentIndex(index)
                        self.remote_table.setFocus()
                        QTimer.singleShot(0, lambda idx=index: self.remote_table.edit(idx))
                        break
                self.file_to_edit_after_refresh = None
            
            folder_count = sum(1 for item in files if item['is_dir'] and item['name'] != '..')
            file_count = sum(1 for item in files if not item['is_dir'])
            
            self.log_event_message(lang["MAINWINDOW_FILE_LIST_UPDATED"].format(folder_count=folder_count, file_count=file_count))

        except Exception as e:
            self.log_event_message(lang["MAINWINDOW_FILE_LIST_PROCESSING_ERROR"].format(e=str(e)))

    def _handle_change_dir_complete(self, old_path, new_path):
        self.log_event_message(lang["MAINWINDOW_DIR_CHANGED_TO"].format(path=new_path))
        self._update_history(new_path)
        self.update_bookmark_button_status()
        if self.sftp_client.connection_details:
            server_name = self.sftp_client.connection_details.get('name')
            if server_name:
                self.settings_manager.set_last_session(server_name, self.sftp_client.current_directory)
        
        self.next_operation_on_finish = self.load_remote_files

    def _handle_operation_error(self, operation, message):
        is_no_such_file_error = "[Errno 2]" in message or "No such file" in message
        
        if operation == 'chdir' and self.active_bookmark_navigation and is_no_such_file_error:
            bookmark = self.active_bookmark_navigation
            reply = QMessageBox.question(
                self,
                lang["MAINWINDOW_BOOKMARK_ERROR_TITLE"],
                lang["MAINWINDOW_BOOKMARK_ERROR_PROMPT"].format(path=bookmark['path'], name=bookmark['name']),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.delete_bookmark(bookmark, confirm=False)
            
            self.update_remote_path_label()

        else:
            op_text = lang["MAINWINDOW_OP_TEXT_CHDIR"] if operation == 'chdir' else lang["MAINWINDOW_OP_TEXT_LIST"]
            self.log_event_message(lang["MAINWINDOW_OP_ERROR_LOG"].format(op_text=op_text, message=message))
            QMessageBox.warning(self, lang["ERROR"], lang["MAINWINDOW_OP_FAILED"].format(message=message))
            self.update_remote_path_label()

    def _on_dir_operation_finished(self):
        self.dir_operation_thread = None
        self.remote_table.setEnabled(True)
        self.unsetCursor()

        if self.active_bookmark_navigation:
            self.active_bookmark_navigation = None

        if self.next_operation_on_finish:
            next_op = self.next_operation_on_finish
            self.next_operation_on_finish = None
            next_op()
        
    def remote_item_double_clicked(self, index):
        if not self.sftp_client.sftp or (self.dir_operation_thread and self.dir_operation_thread.isRunning()):
            return

        row = index.row()
        file_info = self.remote_model.files[row]

        if file_info['is_dir']:
            self.remote_table.setEnabled(False)
            self.setCursor(Qt.WaitCursor)

            self.dir_operation_thread = DirectoryOperationThread(self.sftp_client, self.sftp_lock, 'chdir', path=file_info['name'])
            self.dir_operation_thread.change_dir_complete.connect(self._handle_change_dir_complete)
            self.dir_operation_thread.error.connect(self._handle_operation_error)
            self.dir_operation_thread.finished.connect(self._on_dir_operation_finished)
            self.dir_operation_thread.start()
        else:
            remote_path = f"{self.sftp_client.current_directory}/{file_info['name']}".replace("//", "/")
            self._open_remote_file_for_editing(remote_path, file_info['name'])

    def remote_path_changed(self):
        if not self.sftp_client.sftp or (self.dir_operation_thread and self.dir_operation_thread.isRunning()):
            return
        
        new_path = self.remote_path_edit.text()
        if new_path == self.sftp_client.current_directory:
            return

        self.remote_table.setEnabled(False)
        self.setCursor(Qt.WaitCursor)

        self.dir_operation_thread = DirectoryOperationThread(self.sftp_client, self.sftp_lock, 'chdir', path=new_path)
        self.dir_operation_thread.change_dir_complete.connect(self._handle_change_dir_complete)
        self.dir_operation_thread.error.connect(self._handle_operation_error)
        self.dir_operation_thread.finished.connect(self._on_dir_operation_finished)
        self.dir_operation_thread.start()
        
    def remote_go_up(self):
        if not self.sftp_client.sftp or (self.dir_operation_thread and self.dir_operation_thread.isRunning()):
            return
        
        self.remote_table.setEnabled(False)
        self.setCursor(Qt.WaitCursor)

        self.dir_operation_thread = DirectoryOperationThread(self.sftp_client, self.sftp_lock, 'chdir', path="..")
        self.dir_operation_thread.change_dir_complete.connect(self._handle_change_dir_complete)
        self.dir_operation_thread.error.connect(self._handle_operation_error)
        self.dir_operation_thread.finished.connect(self._on_dir_operation_finished)
        self.dir_operation_thread.start()

    def upload_items_from_drop(self, local_paths, is_fast_mode=False):
        if not self.sftp_client.sftp:
            self.log_event_message(lang["MAINWINDOW_ERROR_NOT_CONNECTED"])
            return

        if not local_paths: return
        
        destination_path = self.sftp_client.current_directory

        if is_fast_mode:
            self._start_fast_archive_upload(local_paths, destination_path)
            return

        # --- ЗМІНЕНО: Використовуємо новий генератор для створення заголовка ---
        task_name = self._generate_smart_task_name(local_paths, lang["UPLOADING"])
        task_id = f"task_upload_batch_{time.time()}"

        source_dirs = {os.path.dirname(p) for p in local_paths}
        source_path_display = source_dirs.pop() if len(source_dirs) == 1 else lang["MAINWINDOW_FROM_MULTIPLE_DIRS"]
        
        self.log_event_message(lang["MAINWINDOW_UPLOAD_START_LOG"].format(count=len(local_paths), source=source_path_display, dest=destination_path))

        self.transfer_tasks[task_id] = {
            "name": task_name, "is_upload": True, "files_completed": 0,
            "files_failed": 0,
            "transferred_size": 0, "active_files_progress": {},
            "remote_base_path": destination_path
        }

        self.transfers_panel.add_task(task_id, task_name, is_upload=True)
        self.transfers_panel.set_task_indeterminate(task_id, lang["MAINWINDOW_SCANNING"])

        thread = OptimizedDirectoryUploadScannerThread(local_paths, destination_path)
        thread.scan_complete.connect(lambda files, dirs, tid=task_id: self._handle_upload_scan_complete(tid, files, dirs))
        thread.error.connect(self.handle_upload_scan_error)
        thread.finished.connect(thread.deleteLater)
        self.worker_threads.append(thread)
        thread.start()

    def _start_fast_archive_upload(self, local_paths, destination_path):
        self.log_event_message("<b>Режим швидкого завантаження (архівом) активовано.</b>")
        
        task_id = f"task_fast_upload_{time.time()}"
        
        # --- ЗМІНЕНО: Використовуємо "розумний" генератор для створення заголовка ---
        task_name = self._generate_smart_task_name(local_paths, lang["QUICK_UPLOAD_TASK_TITLE"])
        
        self.transfer_tasks[task_id] = {
            "name": task_name,
            "is_upload": True,
            "destination_path": destination_path
        }
        
        self.transfers_panel.add_task(task_id, task_name, is_upload=True)
        
        thread = ArchiveConflictCheckThread(
            local_paths,
            self.sftp_client.connection_details,
            destination_path,
            self
        )
        
        self.transfer_tasks[task_id]['worker_thread'] = thread
        
        thread.status_update.connect(lambda msg: self.transfers_panel.set_task_indeterminate(task_id, msg))
        thread.check_complete.connect(
            lambda file_map, non_conf, conf: self._handle_archive_conflicts(task_id, file_map, non_conf, conf)
        )
        thread.error.connect(lambda err: self._handle_fast_upload_complete(task_id, False, err))

        thread.start()

    def _handle_archive_upload_progress(self, task_id, transferred_bytes, total_bytes):
        """Handles progress updates specifically for the single-archive upload."""
        task = self.transfer_tasks.get(task_id)
        if not task:
            return
        
        # We can directly update the panel's progress bar.
        # The 'total_size' might not have been set for this task type, so we set it here.
        if 'total_size' not in task or task['total_size'] == 0:
            task['total_size'] = total_bytes
            
        self.transfers_panel.update_task_progress(task_id, transferred_bytes, total_bytes)

    def _handle_archive_conflicts(self, task_id, local_file_map, non_conflicts, conflicts):
        task = self.transfer_tasks.get(task_id)
        if not task or task.get("is_cancelled"): return
        
        # --- START OF MODIFICATION ---
        # Retrieve the saved destination path from the task
        destination_path = task.get('destination_path')
        if not destination_path:
            # Fallback in case something goes wrong, though it shouldn't
            self._handle_fast_upload_complete(task_id, False, "Внутрішня помилка: шлях призначення не знайдено.")
            return
        # --- END OF MODIFICATION ---

        approved_files_to_pack = list(non_conflicts)
        
        if conflicts:
            self.overwrite_action = None
            for conflict in conflicts:
                action = self.overwrite_action
                if not action:
                    filename = os.path.basename(conflict['arcname'])
                    dialog = AdvancedOverwriteDialog(filename, conflict['source_meta'], conflict['dest_meta'], 'upload', self)
                    dialog_result = dialog.exec()
                    choice, apply_to_all = dialog.get_choice()
                    action = 'cancel' if not dialog_result and choice == 'cancel' else choice
                    if apply_to_all: self.overwrite_action = action
                
                if action == 'cancel':
                    self.log_event_message("Операцію скасовано користувачем.")
                    self.cancel_transfer(task_id)
                    return

                local_path_for_conflict = local_file_map.get(conflict['arcname'])
                if not local_path_for_conflict: continue
                item_to_add = (local_path_for_conflict, conflict['arcname'])

                if action == 'overwrite':
                    approved_files_to_pack.append(item_to_add)
                elif action == 'update':
                    if int(conflict['source_meta']['mtime']) > int(conflict['dest_meta']['mtime']):
                        approved_files_to_pack.append(item_to_add)

        if not approved_files_to_pack:
             self._handle_fast_upload_complete(task_id, True, "Немає файлів для завантаження.")
             return

        self.transfers_panel.set_task_determinate(task_id)

        # Start the SECOND thread for packing and uploading, passing the correct destination_path
        final_thread = ArchiveCreationUploadThread(
            task_id,
            approved_files_to_pack,
            self.sftp_client.connection_details,
            destination_path, # Pass the correct path here
            self
        )
        task['worker_thread'] = final_thread
        
        final_thread.status_update.connect(lambda msg: self.transfers_panel.set_task_indeterminate(task_id, msg))
        final_thread.progress_updated.connect(self._handle_archive_upload_progress)
        final_thread.finished_with_success.connect(lambda msg: self._handle_fast_upload_complete(task_id, True, msg))
        final_thread.error.connect(lambda err: self._handle_fast_upload_complete(task_id, False, err))
        final_thread.start()
        
    def _handle_fast_upload_complete(self, task_id, success, message):
        task = self.transfer_tasks.get(task_id)
        if not task: return

        if success:
            self.log_event_message(f"<span style='color: #43b581;'>{task['name']}: {message}</span>")
            self.transfers_panel.complete_transfer(task_id, True, lang["COMPLETE"])
            self.refresh_remote()
        else:
            self.log_event_message(f"<span style='color: #f04747;'>{task['name']} - Помилка: {message}</span>")
            self.transfers_panel.complete_transfer(task_id, False, lang["ERROR"])
            QMessageBox.warning(self, "Помилка швидкого завантаження", message)

        if task_id in self.transfer_tasks:
            del self.transfer_tasks[task_id]

    def _on_worker_thread_finished(self):
        sender = self.sender()
        if sender in self.worker_threads:
            self.worker_threads.remove(sender)

    def _finalize_task_creation(self, task_id, file_list):
        task = self.transfer_tasks.get(task_id)
        if not task: return

        if not file_list:
            self.log_event_message(lang["MAINWINDOW_NO_FILES_TO_TRANSFER"].format(name=task['name']))
            self.transfers_panel.complete_transfer(task_id, True, lang["MAINWINDOW_NO_FILES"])
            if task_id in self.transfer_tasks:
                del self.transfer_tasks[task_id]
            return

        task["files"] = file_list
        # Сумуємо розмір з 4-го елемента кортежу (індекс 3)
        task["total_size"] = sum(item[3] for item in file_list)
        
        # Зберігаємо стабільний номер файла в межах задачі, щоб retry не ламали лічильник.
        for file_index, (source, target, mtime, size) in enumerate(file_list, start=1):
            transfer_id = f"file_{os.path.basename(source)}_{time.time()}_{file_index}"
            self.transfer_queue.append((task_id, transfer_id, source, target, size, file_index))
            
        self.transfers_panel.set_task_determinate(task_id)
        self.log_event_message(lang["MAINWINDOW_SCAN_COMPLETE_QUEUED"].format(name=task['name'], count=len(file_list)))
        self._process_transfer_queue()

    def upload_file_from_drop(self, local_path):
        if not self.sftp_client.sftp:
            self.log_event_message(lang["MAINWINDOW_ERROR_NOT_CONNECTED"])
            return

        filename = os.path.basename(local_path)
        remote_path = f"{self.sftp_client.current_directory}/{filename}".replace("//", "/")
        task_id = f"task_upload_file_{filename.replace(' ', '_')}_{time.time()}"

        try:
            file_size = os.path.getsize(local_path)
        except OSError as e:
            self.log_event_message(lang["MAINWINDOW_GET_FILE_SIZE_ERROR"].format(filename=filename, e=e))
            return

        self.transfer_tasks[task_id] = {
            "name": filename, "is_upload": True, "files_completed": 0,
            "transferred_size": 0, "active_files_progress": {},
            "files": [(local_path, remote_path, file_size)], "total_size": file_size
        }
        
        self.transfers_panel.add_task(task_id, filename, is_upload=True)
        file_list = [(local_path, remote_path, file_size)]
        self.start_conflict_resolution(task_id, file_list)

    def _handle_transfer_started(self, task_id, transfer_id, filename, file_num, total_files):
        """Оновлює назву активного файлу в панелі передач."""
        self._refresh_task_active_file_display(task_id, transfer_id)

    def _refresh_task_active_file_display(self, task_id, preferred_transfer_id=None):
        task = self.transfer_tasks.get(task_id)
        if not task:
            return

        active_file_names = task.get("active_file_names", {})
        if not active_file_names:
            return

        active_file_numbers = task.get("active_file_numbers", {})
        current_display_id = task.get("displayed_transfer_id")
        current_display_num = task.get("last_displayed_file_num", 0)

        if preferred_transfer_id in active_file_names:
            preferred_num = active_file_numbers.get(preferred_transfer_id, 0)
            if preferred_transfer_id == current_display_id or preferred_num >= current_display_num:
                display_transfer_id = preferred_transfer_id
            elif current_display_id in active_file_names:
                display_transfer_id = current_display_id
            elif active_file_numbers:
                display_transfer_id = max(active_file_numbers, key=active_file_numbers.get)
            else:
                display_transfer_id = next(iter(active_file_names))
        elif current_display_id in active_file_names:
            display_transfer_id = current_display_id
        elif active_file_numbers:
            display_transfer_id = max(active_file_numbers, key=active_file_numbers.get)
        else:
            display_transfer_id = next(iter(active_file_names))

        filename = active_file_names.get(display_transfer_id, "")
        file_num = active_file_numbers.get(display_transfer_id, 0)
        total_files = len(task.get("files", []))

        if filename and total_files > 0:
            task["displayed_transfer_id"] = display_transfer_id
            task["last_displayed_file_num"] = file_num
            self.transfers_panel.update_task_subtitle(task_id, filename, file_num, total_files)

    def _start_transfer_thread(self, transfer_data: tuple):
        """Створює та запускає потік FileTransferThread."""
        if len(transfer_data) >= 6:
            task_id, transfer_id, source_path, target_path, size, file_num = transfer_data[:6]
        else:
            task_id, transfer_id, source_path, target_path, size = transfer_data
            file_num = 0

        task = self.transfer_tasks.get(task_id)
        if not task or task.get("is_cancelled", False):
            return

        is_upload = task["is_upload"]
        task.setdefault("active_file_names", {})
        task.setdefault("active_file_numbers", {})
        files_total = len(task.get("files", []))
        filename = os.path.basename(source_path)

        task["active_file_names"][transfer_id] = filename
        task["active_file_numbers"][transfer_id] = file_num

        thread = FileTransferThread(
            is_upload, source_path, target_path,
            self.sftp_client.connection_details,
            task_id, transfer_id,
            self.settings_manager,
            size,
            file_num=file_num,
            total_files=files_total,
            parent=self
        )

        thread.transfer_started.connect(self._handle_transfer_started)
        thread.progress_updated.connect(self._handle_file_progress)
        thread.transfer_complete.connect(self._handle_file_complete)
        # --- FIX: The line below that caused the error has been removed ---
        # thread.connection_failed.connect(self._handle_connection_failure) 
        thread.finished.connect(thread.deleteLater)

        self.active_file_transfers[transfer_id] = thread
        task["active_files_progress"][transfer_id] = {"transferred": 0, "total": size}

        thread.start()

    def _handle_connection_failure(self, task_id, transfer_id, message):
        self.active_file_transfers.pop(transfer_id, None)
        # Повідомлення тепер генерується менеджером, тому тут воно не потрібне
        if self.adaptive_manager:
            self.adaptive_manager.report_connection_error(transfer_id)

    def _process_transfer_queue(self):
        if not self.sftp_client.sftp: return

        # --- ПОЧАТОК КАРДИНАЛЬНИХ ЗМІН: ЗАВЖДИ ВИКОРИСТОВУЄМО АДАПТИВНИЙ РЕЖИМ ---
        # Складна і ненадійна логіка if/else повністю видалена.

        # Створюємо менеджер, якщо його ще немає
        if not self.adaptive_manager:
            # Отримуємо з налаштувань максимальну стелю, яку встановив користувач
            ceiling = self.settings_manager.get_max_concurrent_transfers()
            # Передаємо цю стелю нашому менеджеру
            self.adaptive_manager = AdaptiveTransferManager(ceiling=ceiling)
            self.adaptive_manager.request_new_transfer.connect(self._start_transfer_thread)
            self.adaptive_manager.status_update.connect(
                lambda msg: self.log_event_message(msg, level='warning')
            )

        # Якщо в головній черзі є файли, передаємо їх менеджеру
        if self.transfer_queue:
            items_to_add = self.transfer_queue
            self.transfer_queue = []
            self.adaptive_manager.add_transfers(items_to_add)
        # --- КІНЕЦЬ ЗМІН ---

    def _handle_file_progress(self, task_id, transfer_id, transferred_bytes, total_bytes):
        task = self.transfer_tasks.get(task_id)
        if not task:
            return

        task["active_files_progress"][transfer_id] = {
            "transferred": transferred_bytes,
            "total": total_bytes
        }
        self._refresh_task_active_file_display(task_id, transfer_id)
        total_task_size = task.get("total_size", 0)
        if total_task_size == 0 and total_bytes > 0:
            task["total_size"] = total_bytes
            total_task_size = total_bytes

        if total_task_size > 0:
            completed_size = task.get("transferred_size", 0)
            active_size = sum(p["transferred"] for p in task["active_files_progress"].values())
            current_total_transferred = completed_size + active_size
            self.transfers_panel.update_task_progress(task_id, current_total_transferred, total_task_size)

    def _handle_file_complete(self, task_id, transfer_id, success, message):
        thread = self.active_file_transfers.pop(transfer_id, None)
        if not thread:
            return

        task = self.transfer_tasks.get(task_id)
        if not task:
            return

        # Визначаємо, чи було це скасування користувачем
        is_user_cancellation = not success and message == lang.get("CANCELED")
        is_network_error = (not success) and any(keyword in message.lower() for keyword in 
                             ["timeout", "connection reset", "broken pipe",
                              "connection lost", "forcibly closed",
                              "failed to respond", "connection error", "protocol banner"])

        if self.adaptive_manager:
            if success:
                self.adaptive_manager.report_success(transfer_id)
            elif is_user_cancellation:
                # Нова логіка: повідомляємо менеджеру про скасування без штрафів
                self.adaptive_manager.report_cancellation(transfer_id)
            else:
                # Тимчасові помилки мережі обробляються м'якше: файл автоматично повертається в чергу.
                if is_network_error:
                    self.adaptive_manager.report_connection_error(transfer_id)
                else:
                    self.adaptive_manager.report_failure(transfer_id)
        
        if task.get("is_cancelled", False):
            self.fixed_mode_banner_errors = 0
            self.fallback_to_adaptive_triggered = False

        if success and task.get("is_archive_download"):
            local_archive_path = task.get("local_archive_path")
            extract_to_dir = task.get("extract_to_dir")
            remote_path_to_delete = task.get("remote_archive_path_to_delete")
            
            if local_archive_path and extract_to_dir and remote_path_to_delete:
                self._prepare_archive_extraction(task_id, local_archive_path, extract_to_dir, remote_path_to_delete)

        if transfer_id in task["active_files_progress"]:
            del task["active_files_progress"][transfer_id]
        task.get("active_file_names", {}).pop(transfer_id, None)
        task.get("active_file_numbers", {}).pop(transfer_id, None)

        file_size = thread.file_size
        filename = os.path.basename(thread.source_path)
        
        if success:
            task["transferred_size"] += file_size
            task["files_completed"] += 1
        elif is_network_error:
            log_msg = lang["MAINWINDOW_TRANSFER_RETRY_LOG"].format(filename=filename, message=message)
            self.log_event_message(log_msg, level='warning')
        elif not is_user_cancellation:
            # Рахуємо помилки, тільки якщо це не скасування і не автоматичний ретрай
            log_msg = lang["MAINWINDOW_TRANSFER_ERROR_LOG"].format(filename=filename, message=message)
            self.log_event_message(log_msg, level='error')
            task["files_failed"] = task.get("files_failed", 0) + 1
        
        processed_files = task["files_completed"] + task.get("files_failed", 0)
        total_files_in_task = len(task.get("files", []))
        # Визначаємо, чи завершено завдання. Скасовані файли не враховуються у processed_files,
        # тому перевіряємо прапорець is_cancelled
        is_task_finished = (processed_files >= total_files_in_task and total_files_in_task > 0) or task.get("is_cancelled")

        if not is_task_finished:
            self._refresh_task_active_file_display(task_id)
        
        # Завершуємо завдання, лише якщо воно дійсно закінчилось і ще існує
        if is_task_finished and task_id in self.transfer_tasks:
            self.fixed_mode_banner_errors = 0
            self.fallback_to_adaptive_triggered = False
            failed_count = task.get("files_failed", 0)
            
            if task.get("is_cancelled"):
                # Якщо завдання було скасовано, показуємо відповідний статус
                self.transfers_panel.complete_transfer(task_id, False, lang["CANCELED"])
            elif failed_count > 0:
                final_message = lang["MAINWINDOW_TASK_COMPLETED_WITH_ERRORS"].format(failed_count=failed_count, total_files=total_files_in_task)
                self.transfers_panel.complete_transfer(task_id, False, final_message)
                log_msg = lang["MAINWINDOW_TASK_FAILED_LOG"].format(task_name=task['name'])
                self.log_event_message(log_msg, level='error')
            else:
                self.transfers_panel.complete_transfer(task_id, True, lang["COMPLETE"])
                self.log_event_message(lang["MAINWINDOW_TASK_SUCCESSFULLY_COMPLETED"].format(name=task['name']))
            
            if task_id in self.transfer_tasks:
                del self.transfer_tasks[task_id]
            if task.get("is_upload") and failed_count == 0:
                self.refresh_remote()
        
        self._process_transfer_queue()

    def on_extraction_finished(self, message, remote_path_to_delete):
        self.log_event_message(f"<span style='color: #43b581;'>{message}</span>")

        self.log_event_message(lang["MAINWINDOW_DELETING_TEMP_ARCHIVE"].format(archive_name=os.path.basename(remote_path_to_delete)))
        success, msg = self.sftp_client.delete_file(remote_path_to_delete)
        
        if success:
            self.log_event_message(lang["MAINWINDOW_TEMP_ARCHIVE_DELETED"])
            server_name = self.sftp_client.connection_details.get('name')
            if server_name:
                self.settings_manager.remove_pending_cleanup_file(server_name, remote_path_to_delete)
            self.refresh_remote() 
        else:
            error_log_msg = lang["MAINWINDOW_TEMP_ARCHIVE_DELETE_ERROR"].format(path=remote_path_to_delete, msg=msg)
            self.log_event_message(f"<span style='color: #f04747;'>{error_log_msg}</span>")
            QMessageBox.warning(self, lang["MAINWINDOW_CLEANUP_ERROR_TITLE"], error_log_msg)

    def on_extraction_error(self, archive_path, error_message):
        log_msg = lang["MAINWINDOW_EXTRACT_ERROR_LOG"].format(archive_name=os.path.basename(archive_path), error=error_message)
        self.log_event_message(f"<span style='color: #f04747;'>{log_msg}</span>")
        QMessageBox.warning(self, lang["MAINWINDOW_EXTRACT_ERROR_TITLE"], log_msg)

    def cancel_transfer(self, task_id):
        # 1. Скасовуємо потік пошуку файлів, якщо він активний для цього завдання
        if task_id in self.active_search_threads:
            thread = self.active_search_threads.pop(task_id, None)
            if thread and thread.isRunning():
                thread.cancel()
                thread.wait(500) # Даємо трохи часу на завершення

        task = self.transfer_tasks.get(task_id)
        if task:
            task["is_cancelled"] = True
            self.log_event_message(lang["MAINWINDOW_CANCELING_TASK"].format(name=task['name']))
            
            # 2. Скасовуємо будь-який активний фоновий потік (сканер, перевірка конфліктів)
            worker_thread = task.get('worker_thread')
            if worker_thread and hasattr(worker_thread, 'cancel') and worker_thread.isRunning():
                worker_thread.cancel()
                worker_thread.wait(500)

        # 3. Скасовуємо активні потоки передачі файлів
        for tid, thread in list(self.active_file_transfers.items()):
            if hasattr(thread, 'task_id') and thread.task_id == task_id:
                thread.cancel()  # Новий метод cancel тепер надійний

        # 4. Очищуємо черги
        self.transfer_queue = [item for item in self.transfer_queue if item[0] != task_id]
        
        # 5. Скидаємо стан адаптивного менеджера, щоб він не завис
        if self.adaptive_manager:
            self.adaptive_manager.reset()

        # 6. Завершуємо завдання в UI
        if task_id in self.transfer_tasks:
            self.transfers_panel.complete_transfer(task_id, False, lang["CANCELED"])
            # Видаляємо завдання зі списку, щоб уникнути подальшої обробки
            del self.transfer_tasks[task_id]
                
    def handle_conflict_resolution_complete(self, task_id, non_conflicts, conflicts):
        task = self.transfer_tasks.get(task_id)
        if not task: return

        # ВИРІШЕННЯ: Видаляємо посилання на потік, оскільки він завершив свою роботу.
        if 'worker_thread' in task:
            del task['worker_thread']

        # non_conflicts вже містить правильні кортежі з 4 елементів
        final_list_to_transfer = list(non_conflicts)
        
        if conflicts:
            self.overwrite_action = None
            skipped_files_count = 0

            for conflict in conflicts:
                action = self.overwrite_action
                
                if not action:
                    source_path = conflict['source_path']
                    filename = os.path.basename(source_path)
                    direction = 'upload' if task.get('is_upload', True) else 'download'
                    dialog = AdvancedOverwriteDialog(filename, conflict['source_meta'], conflict['dest_meta'], direction, self)
                    dialog_result = dialog.exec()
                    choice, apply_to_all = dialog.get_choice()
                    action = 'cancel' if not dialog_result and choice == 'cancel' else choice
                    if apply_to_all: self.overwrite_action = action
                
                if action == 'cancel':
                    self.log_event_message(lang["MAINWINDOW_OP_CANCELED_BY_USER_CONFLICT"])
                    self.cancel_transfer(task_id)
                    return

                item_to_transfer = (
                    conflict['source_path'],
                    conflict['target_path'],
                    conflict['source_meta']['mtime'],
                    conflict['source_meta']['size']
                )

                if action == 'overwrite':
                    final_list_to_transfer.append(item_to_transfer)
                elif action == 'update':
                    # ПОРІВНЮЄМО ТІЛЬКИ ЦІЛУ ЧАСТИНУ ЧАСУ (СЕКУНДИ), ІГНОРУЮЧИ МІЛІСЕКУНДИ
                    if int(conflict['source_meta']['mtime']) > int(conflict['dest_meta']['mtime']):
                        final_list_to_transfer.append(item_to_transfer)
                    else:
                        skipped_files_count += 1
                elif action == 'skip':
                    skipped_files_count += 1

            if skipped_files_count > 0:
                self.log_event_message(lang["MAINWINDOW_SKIPPED_N_FILES_BY_USER"].format(count=skipped_files_count))

        # Тепер сюди передається список, що складається виключно з кортежів з 4 елементів
        self._finalize_task_creation(task_id, final_list_to_transfer)

    # ЗАМІНІТЬ ЦЕЙ МЕТОД У КЛАСІ MainWindow
    def start_conflict_resolution(self, task_id, all_files, local_base_path=None):
        task = self.transfer_tasks.get(task_id)
        if not task or not all_files:
            self._finalize_task_creation(task_id, all_files or [])
            return

        self.transfers_panel.set_task_indeterminate(task_id, lang["MAINWINDOW_CHECKING_CONFLICTS"].format(count=len(all_files)))

        thread = ConflictResolutionThread(
            self.sftp_client.connection_details,
            all_files,
            task['is_upload'],
            remote_base_path=task.get('remote_base_path'),
            local_base_path=local_base_path
        )
        
        task['worker_thread'] = thread # <-- ДОДАНО

        thread.resolution_complete.connect(lambda nc, c, iu: self.handle_conflict_resolution_complete(task_id, nc, c))
        thread.error.connect(self.handle_scan_error)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_worker_thread_finished)
        
        self.worker_threads.append(thread)
        thread.start()

    def setup_ui_components(self):
        if qta:
            self.bookmark_action_button.setIcon(qta.icon("fa6s.star"))
            self.bookmark_action_button.setIconSize(QSize(18, 18))
        else:
            self.bookmark_action_button.setText("☆")
        self.bookmark_action_button.setCursor(Qt.PointingHandCursor)
        self.bookmark_action_button.setFixedSize(28, 28)
        self.bookmark_action_button.setEnabled(False)
        self.inactive_bookmark_style = "border: none; background: transparent; font-size: 16px; color: gray;"
        self.active_bookmark_style = "border: none; background: transparent; font-size: 16px; color: white;"
        self.bookmark_action_button.setStyleSheet(self.inactive_bookmark_style)
        
        self.remote_table.setEditTriggers(QAbstractItemView.SelectedClicked)
        self.remote_table.setFocusPolicy(Qt.StrongFocus)
        self.remote_table.verticalHeader().setVisible(False)
        self.remote_table.setSelectionBehavior(QTableView.SelectRows)
        self.remote_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.remote_table.setSortingEnabled(True)
        self.remote_table.setShowGrid(False)
        self.remote_table.setAlternatingRowColors(False)
        self.remote_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        
        header = self.remote_table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, 80)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
        self.initialize_tables()

    def create_actions(self):
        self.cut_action = QAction(qta.icon("fa6s.scissors", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_ACTION_CUT"], self)
        self.cut_action.setShortcut("Ctrl+X")
        self.copy_action = QAction(qta.icon("fa6s.copy", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_ACTION_COPY"], self)
        self.copy_action.setShortcut("Ctrl+C")
        self.paste_action = QAction(qta.icon("fa6s.paste", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_ACTION_PASTE"], self)
        self.paste_action.setShortcut("Ctrl+V")
        
        self.delete_action = QAction(qta.icon("fa6s.trash") if qta else QIcon(), lang["DELETE"], self)
        self.delete_action.setShortcut("Delete")
        self.delete_action.setObjectName("deleteAction")
        self.addAction(self.delete_action)

        self.create_dir_action_menu = QAction(qta.icon("fa6s.folder-plus", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_ACTION_CREATE_DIR"], self)
        self.create_dir_action_menu.setShortcut("Ctrl+Shift+N")
        self.create_file_action_menu = QAction(qta.icon("fa6s.file-circle-plus", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_ACTION_CREATE_FILE"], self)
        self.refresh_action_menu = QAction(qta.icon("fa6s.arrows-rotate", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_ACTION_REFRESH"], self)
        self.refresh_action_menu.setShortcut("F5")
        self.up_action_menu = QAction(qta.icon("fa6s.arrow-turn-up", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_ACTION_UP"], self)
        self.up_action_menu.setShortcut("Alt+Up")
        
        self.search_action = QAction(qta.icon("fa6s.magnifying-glass", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_ACTION_SEARCH"], self)
        self.search_action.setShortcut(QKeySequence.Find)
        
        self.sync_folder_action_menu = QAction(qta.icon("fa6s.arrows-spin", color="#b9bbbe") if qta else QIcon(), lang.get("SYNC_FOLDER", "Sync folder..."), self)
        
        self.about_action = QAction(qta.icon("fa6s.circle-info", color="#b9bbbe") if qta else QIcon(), lang.get("ABOUT_ACTION", "About SFTPanda..."), self)
        
        self.connection_actions = [
            self.cut_action, self.copy_action, self.paste_action, self.delete_action, 
            self.search_action, self.sync_folder_action_menu, self.create_dir_action_menu, 
            self.create_file_action_menu, self.refresh_action_menu, self.up_action_menu
        ]
        for action in self.connection_actions:
            action.setEnabled(False)

    def connect_signals(self):
        self.remote_model.rename_failed.connect(self.handle_rename_failed)
        self.transfers_panel.cancel_all_transfers.connect(self.cancel_all_transfers)
        self.transfers_panel.transfer_cancellation_requested.connect(self.cancel_transfer)
        self.remote_path_edit.returnPressed.connect(self.remote_path_changed)
        self.bookmark_action_button.clicked.connect(self.show_bookmark_action_menu)
        self.remote_table.customContextMenuRequested.connect(self.show_remote_context_menu)
        self.remote_table.doubleClicked.connect(self.remote_item_double_clicked)
        self.remote_table.selectionModel().selectionChanged.connect(self.update_action_states)
        self.remote_table.horizontalHeader().sortIndicatorChanged.connect(self.remote_sort_changed)
        self.cut_action.triggered.connect(lambda: self.handle_copy_or_cut("cut"))
        self.copy_action.triggered.connect(lambda: self.handle_copy_or_cut("copy"))
        self.paste_action.triggered.connect(self.handle_paste)
        self.delete_action.triggered.connect(self.handle_delete_action_triggered)
        self.create_dir_action_menu.triggered.connect(self.create_remote_directory)
        self.create_file_action_menu.triggered.connect(self.create_remote_file)
        self.refresh_action_menu.triggered.connect(self.refresh_remote)
        self.up_action_menu.triggered.connect(self.remote_go_up)
        self.file_watcher.fileChanged.connect(self.handle_file_changed)
        self.reconnect_timer.timeout.connect(self.check_connection)
        self.server_list_widget.server_selected.connect(self.connect_to_server)
        self.search_action.triggered.connect(self.show_search_dialog)
        self.sync_folder_action_menu.triggered.connect(self.trigger_sync_current_dir)
        self.about_action.triggered.connect(self.show_about_dialog)

        # --- ДОДАЙТЕ ЦІ РЯДКИ ---
        self.back_button.clicked.connect(self.navigate_back)
        self.forward_button.clicked.connect(self.navigate_forward)
        # --- КІНЕЦЬ ДОДАВАННЯ ---

    def update_action_states(self):
        has_selection = False
        if self.sftp_client.sftp:
            selected_rows = self.remote_table.selectionModel().selectedRows()
            has_selection = any(self.remote_model.files[index.row()]['name'] != ".." for index in selected_rows)
        can_paste = bool(self.internal_clipboard and self.sftp_client.sftp)
        self.cut_action.setEnabled(has_selection)
        self.copy_action.setEnabled(has_selection)
        self.delete_action.setEnabled(has_selection)
        self.paste_action.setEnabled(can_paste)

    def handle_rename_failed(self, old_name, error_message):
        self.log_event_message(lang["MAINWINDOW_RENAME_ERROR_LOG"].format(old_name=old_name, error=error_message))
        QMessageBox.warning(self, lang["MAINWINDOW_RENAME_ERROR_TITLE"], error_message)

    def create_menus(self):
        menubar = self.menuBar()
        menubar.clear()
        file_menu = menubar.addMenu(lang["MAINWINDOW_MENU_FILE"])
        connect_menu = file_menu.addMenu(qta.icon("fa6s.network-wired", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_CONNECTION"])
        self.connect_saved_action = QAction(qta.icon("fa6s.server", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_CONNECT_TO_SAVED"], self)
        self.connect_saved_action.triggered.connect(self.show_server_list_dialog)
        connect_menu.addAction(self.connect_saved_action)
        self.new_connection_action = QAction(qta.icon("fa6s.plus", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_NEW_CONNECTION"], self)
        self.new_connection_action.triggered.connect(self.show_server_dialog)
        connect_menu.addAction(self.new_connection_action)
        self.disconnect_action = QAction(qta.icon("fa6s.power-off", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_DISCONNECT"], self)
        self.disconnect_action.triggered.connect(self.disconnect)
        self.disconnect_action.setEnabled(False)
        connect_menu.addAction(self.disconnect_action)
        file_menu.addSeparator()
        new_menu = file_menu.addMenu(qta.icon("fa6s.file-medical", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_CREATE"])
        new_menu.addAction(self.create_dir_action_menu)
        new_menu.addAction(self.create_file_action_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.search_action)
        file_menu.addAction(self.sync_folder_action_menu)
        file_menu.addSeparator()
        exit_action = QAction(qta.icon("fa6s.right-from-bracket", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_EXIT"], self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        edit_menu = menubar.addMenu(lang["MAINWINDOW_MENU_EDIT"])
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        view_menu = menubar.addMenu(lang["MAINWINDOW_MENU_VIEW"])
        self.toggle_hidden_action = QAction(qta.icon("fa6s.eye-slash", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_SHOW_HIDDEN"], self)
        self.toggle_hidden_action.setCheckable(True)
        self.toggle_hidden_action.setChecked(self.settings_manager.get_show_hidden())
        self.toggle_hidden_action.triggered.connect(self.toggle_hidden_files)
        view_menu.addAction(self.toggle_hidden_action)
        columns_menu = view_menu.addMenu(qta.icon("fa6s.table-columns", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_COLUMNS"])
        visible_columns = self.settings_manager.get_visible_columns()
        column_map = [
            {"index": 0, "key": "name", "name": lang["HEADER_NAME"], "always_visible": True}, 
            {"index": 1, "key": "date", "name": lang["MAINWINDOW_COLUMN_DATE"]}, 
            {"index": 2, "key": "size", "name": lang["HEADER_SIZE"]}, 
            {"index": 3, "key": "group", "name": lang["HEADER_GROUP"]}, 
            {"index": 4, "key": "permissions", "name": lang["HEADER_PERMISSIONS"]}
        ]
        self.column_actions = []
        for column in column_map:
            action = QAction(column["name"], self)
            action.setCheckable(True)
            if column.get("always_visible", False):
                action.setChecked(True)
                action.setEnabled(False)
            else:
                action.setChecked(visible_columns[column["key"]])
            action.setData(column)
            action.triggered.connect(self.toggle_column_visibility)
            columns_menu.addAction(action)
            self.column_actions.append(action)
        self.apply_column_visibility()
        view_menu.addSeparator()
        view_menu.addAction(self.refresh_action_menu)
        view_menu.addAction(self.up_action_menu)
        self.bookmarks_menu = menubar.addMenu(lang["MAINWINDOW_MENU_BOOKMARKS"])
        self.bookmarks_menu.setEnabled(False)
        settings_menu = menubar.addMenu(lang["MAINWINDOW_MENU_SETTINGS"])
        
        settings_action = QAction(qta.icon("fa6s.sliders", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_GENERAL_SETTINGS"], self)
        settings_action.triggered.connect(self.show_settings_dialog)
        settings_menu.addAction(settings_action)

        # --- ДОДАНО НОВИЙ ПУНКТ МЕНЮ ---
        open_config_action = QAction(qta.icon("fa6s.folder-open", color="#b9bbbe") if qta else QIcon(), lang["MAINWINDOW_MENU_OPEN_CONFIG_FOLDER"], self)
        open_config_action.triggered.connect(self.open_config_folder)
        settings_menu.addAction(open_config_action)

        # Help Menu
        help_menu = menubar.addMenu(lang.get("MAINWINDOW_MENU_HELP", "Help"))
        help_menu.addAction(self.about_action)

    def connect_sorting_signals(self):
        self.remote_table.horizontalHeader().sortIndicatorChanged.connect(self.remote_sort_changed)

    def remote_sort_changed(self, column, order):
        if self.settings_manager:
            self.settings_manager.set_sort_settings(column, 0 if order == Qt.AscendingOrder else 1)
            self.remote_model.sort_column = column
            self.remote_model.sort_order = order
    
    def toggle_auto_connect(self):
        enabled = self.auto_connect_action.isChecked()
        self.settings_manager.set_auto_connect(enabled)
        log_message = lang["MAINWINDOW_AUTOCONNECT_ENABLED_LOG"] if enabled else lang["MAINWINDOW_AUTOCONNECT_DISABLED_LOG"]
        self.log_event_message(log_message)
    
    def restore_last_session(self):
        last_session = self.settings_manager.get_last_session()
        if not last_session.get("auto_connect", True):
            return
        server_name = last_session.get("server_name", "")
        remote_dir = last_session.get("remote_directory", "")
        if server_name:
            server_data = self.server_manager.get_server(server_name)
            if server_data:
                self.log_event_message(lang["MAINWINDOW_AUTOCONNECTING_TO"].format(server=server_name))
                self.auto_restore_remote_dir = remote_dir
                self.connect_to_server(server_data, restore_session=True)

    def log_event_message(self, message, level='info'):
        """
        Оновлений метод логування з підтримкою рівнів та кольорів.
        level: 'info' (білий), 'warning' (жовтий), 'error' (червоний).
        """
        timestamp = self.get_current_time_str()
        
        color = "#dcddde" # Default color for 'info'
        if level == 'warning':
            color = "#faa61a" # Yellow/Orange
        elif level == 'error':
            color = "#f04747" # Red

        log_entry = (f"<span style='color: #8e9297;'>[{timestamp}]</span> "
                     f"<span style='color: {color};'>{message}</span>")
        
        self.event_log_widget.add_log_message(log_entry)
    
    def get_current_time_str(self):
        return datetime.now().strftime("%H:%M:%S")
    
    def handle_file_changed(self, path):
        current_time = time.time()
        last_save_time = self.last_save_timestamps.get(path, 0)
        if current_time - last_save_time < 1.0: # Ігнорувати, якщо з останнього збереження пройшло < 1 секунди
            return
        self.last_save_timestamps[path] = current_time
        if path in self.edited_files:
            remote_path = self.edited_files[path]
            filename = os.path.basename(path)
            if self.sftp_client.sftp and self.sftp_client.check_connection():
                try:
                    self.log_event_message(lang["MAINWINDOW_FILE_CHANGED_SAVING"].format(filename=filename))
                    
                    # --- ПОЧАТОК ВИПРАВЛЕННЯ ---
                    if not os.path.exists(path):
                        self.log_event_message(f"<span style='color: #faa61a;'>Файл '{filename}' не знайдено, можливо, його було видалено.</span>")
                        return

                    # Отримуємо розмір та час модифікації ОДНИМ запитом
                    stat_info = os.stat(path)
                    size = stat_info.st_size
                    mtime = stat_info.st_mtime
                    
                    # Створюємо ПРАВИЛЬНИЙ кортеж з 4 елементів
                    files_to_upload = [(path, remote_path, mtime, size)]
                    # --- КІНЕЦЬ ВИПРАВЛЕННЯ ---
                    
                    task_id = f"task_edit_{filename.replace(' ', '_')}_{time.time()}"
                    self.transfer_tasks[task_id] = {
                        "name": lang["SAVE"], "is_upload": True, "files": files_to_upload, 
                        "total_size": size, "files_completed": 0, 
                        "files_failed": 0,
                        "transferred_size": 0, "active_files_progress": {}
                    }
                    self.transfers_panel.add_task(task_id, lang["SAVE"], is_upload=True)
                    self._finalize_task_creation(task_id, files_to_upload)
                    QApplication.beep()

                except Exception as e:
                    self.log_event_message(lang["MAINWINDOW_AUTOUPLOAD_ERROR"].format(filename=filename, e=str(e)))
                    if not self.sftp_client.check_connection():
                        self.pending_uploads.append((path, remote_path))
            else:
                self.pending_uploads.append((path, remote_path))
                self.log_event_message(lang["MAINWINDOW_FILE_CHANGED_QUEUED"].format(filename=filename))
            if path not in self.file_watcher.files():
                self.file_watcher.addPath(path)
    
    def start_connection_check(self):
        reconnect_settings = self.settings_manager.get_reconnect_settings()
        if reconnect_settings["enabled"]:
            interval = reconnect_settings["interval"] * 1000
            self.reconnect_timer.start(interval)
            self.reconnect_attempt_count = 0
    
    def stop_connection_check(self):
        if self.reconnect_timer.isActive():
            self.reconnect_timer.stop()
    
    def check_connection(self):
        if not self.sftp_client.connection_details:
            self.stop_connection_check()
            return
        if not self.sftp_client.check_connection():
            if not self.is_reconnecting:
                self.is_reconnecting = True
                self.reconnect_attempt_count = 0
                self.log_event_message(lang["MAINWINDOW_CONNECTION_LOST"])
            self.attempt_reconnect()
        elif self.is_reconnecting:
            self.is_reconnecting = False
            self.reconnect_attempt_count = 0
            self.process_pending_uploads()
    
    def attempt_reconnect(self):
        reconnect_settings = self.settings_manager.get_reconnect_settings()
        max_attempts = reconnect_settings["max_attempts"]
        if self.reconnect_attempt_count >= max_attempts:
            self.log_event_message(lang["MAINWINDOW_RECONNECT_FAILED"].format(count=max_attempts))
            self.stop_connection_check()
            self.is_reconnecting = False
            return
        self.reconnect_attempt_count += 1
        self.log_event_message(lang["MAINWINDOW_RECONNECT_ATTEMPT"].format(current=self.reconnect_attempt_count, max=max_attempts))
        success, message = self.sftp_client.reconnect()
        if success:
            self.log_event_message(lang["MAINWINDOW_RECONNECT_SUCCESS"])
            self.is_reconnecting = False
            self.reconnect_attempt_count = 0
            self.refresh_remote()
            self.process_pending_uploads()
    
    def process_pending_uploads(self):
        if not self.pending_uploads or not self.sftp_client.check_connection():
            return
        self.log_event_message(lang["MAINWINDOW_UPLOADING_PENDING_FILES"].format(count=len(self.pending_uploads)))
        
        task_id = f"task_pending_{time.time()}"
        task_name = lang["MAINWINDOW_PENDING_UPLOADS_TASK_NAME"]
        self.transfer_tasks[task_id] = {
            "name": task_name, "is_upload": True, "files_completed": 0,
            "files_failed": 0, # <-- ДОДАНО
            "transferred_size": 0, "active_files_progress": {}
        }
        self.transfers_panel.add_task(task_id, task_name, is_upload=True)

        files_to_queue = []
        for local_path, remote_path in self.pending_uploads:
            size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
            files_to_queue.append((local_path, remote_path, size))
        self.pending_uploads.clear()
        
        self._finalize_task_creation(task_id, files_to_queue)
        
        if self.sftp_client.sftp:
            self.refresh_remote()

    def show_reconnect_settings(self):
        dialog = ReconnectSettingsDialog(self, self.settings_manager)
        dialog.exec()
    
    def toggle_column_visibility(self):
        action = self.sender()
        if not action: return
        column_data = action.data()
        if not column_data: return
        self.settings_manager.set_column_visibility(column_data["key"], action.isChecked())
        self.apply_column_visibility()

    def apply_column_visibility(self):
        visible_columns = self.settings_manager.get_visible_columns()
        for action in self.column_actions:
            column_data = action.data()
            if column_data.get("always_visible", False): continue
            visible = visible_columns[column_data["key"]]
            index = column_data["index"]
            self.remote_table.setColumnHidden(index, not visible)

    def initialize_tables(self):
        visible_columns = self.settings_manager.get_visible_columns()
        for column_key, visible in visible_columns.items():
            for i, header in enumerate(self.remote_model.headers):
                if header.lower() == column_key and column_key != "name":
                    self.remote_table.setColumnHidden(i, not visible)
    
    def update_remote_path_label(self):
        self.remote_path_edit.setText(self.sftp_client.current_directory)
        if hasattr(self, 'breadcrumb_bar'):
            self.breadcrumb_bar.set_path(self.sftp_client.current_directory)

    def navigate_via_breadcrumbs(self, path):
        self._navigate_to_path(path)

    def enable_path_edit_mode(self):
        self.remote_path_edit.setText(self.sftp_client.current_directory)
        self.path_stack.setCurrentWidget(self.remote_path_edit)
        self.remote_path_edit.setFocus()
        self.remote_path_edit.selectAll()

    def disable_path_edit_mode(self):
        # If text changed, try to navigate
        if self.remote_path_edit.text() != self.sftp_client.current_directory:
            self.remote_path_changed()
        
        # Switch back to breadcrumbs
        # Use QTimer to delay switching slightly to handle focus events correctly
        QTimer.singleShot(100, lambda: self.path_stack.setCurrentWidget(self.breadcrumb_container))
    
    def show_settings_dialog(self):
        dialog = SettingsDialog(self, self.settings_manager)
        if dialog.exec():
            self.toggle_hidden_action.setChecked(self.settings_manager.get_show_hidden())
            if self.sftp_client.sftp: self.refresh_remote()
            if self.sftp_client.check_connection():
                self.stop_connection_check()
                self.start_connection_check()
    
    def show_about_dialog(self):
        dialog = AboutDialog(self)
        dialog.exec()

    def check_for_updates_silently(self):
        self.startup_checker = VersionCheckerThread(self)
        self.startup_checker.check_finished.connect(self.on_startup_check_finished)
        self.startup_checker.start()
        
    def on_startup_check_finished(self, success, online_version, update_url):
        if success:
            try:
                local_parts = [int(x) for x in APP_VERSION.split(".")]
                online_parts = [int(x) for x in online_version.split(".")]
                has_update = online_parts > local_parts
            except Exception:
                has_update = online_version != APP_VERSION
                
            if has_update:
                reply = QMessageBox.question(
                    self, 
                    lang.get("UPDATE_AVAILABLE_TITLE", "Update Available"),
                    lang.get("UPDATE_AVAILABLE_PROMPT", "A new version of SFTPanda ({version}) is available. Would you like to visit the download page?").format(version=online_version),
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    from PySide6.QtGui import QDesktopServices
                    QDesktopServices.openUrl(QUrl(update_url))
    
    def open_config_folder(self):
        # Отримуємо повний шлях до файлу конфігурації
        config_file_path = self.settings_manager.config_path
        # Визначаємо теку, в якій знаходиться цей файл
        config_dir_path = os.path.dirname(config_file_path)

        # Перевіряємо, чи існує така тека
        if os.path.exists(config_dir_path):
            # Використовуємо QDesktopServices для крос-платформного відкриття теки
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(config_dir_path))
        else:
            # На випадок, якщо тека з якихось причин не була створена
            QMessageBox.warning(self, lang["WARNING"], f"Теку не знайдено:\n{config_dir_path}")

    def toggle_hidden_files(self):
        show_hidden = self.toggle_hidden_action.isChecked()
        self.settings_manager.set_show_hidden(show_hidden)
        log_message = lang["MAINWINDOW_SHOW_HIDDEN_ENABLED_LOG"] if show_hidden else lang["MAINWINDOW_SHOW_HIDDEN_DISABLED_LOG"]
        self.log_event_message(log_message)
        if self.sftp_client.sftp: self.refresh_remote()
    
    def show_server_dialog(self):
        dialog = ServerDialog(self)
        if dialog.exec():
            server_data = dialog.get_server_data()
            if QMessageBox.question(self, lang["MAINWINDOW_SAVE_SERVER_TITLE"], lang["MAINWINDOW_SAVE_SERVER_PROMPT"], QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
                self.server_manager.add_server(server_data)
            self.connect_to_server(server_data)
    
    def show_server_list_dialog(self):
        dialog = ServerListDialog(self, self.server_manager)
        if dialog.exec() and hasattr(dialog, 'selected_server'):
            self.connect_to_server(dialog.selected_server)
    
    def _update_navigation_buttons_state(self):
        """Оновлює стан активності кнопок Назад/Вперед."""
        self.back_button.setEnabled(self.dir_history_index > 0)
        self.forward_button.setEnabled(self.dir_history_index < len(self.dir_history) - 1)

    def _reset_history(self):
        """Скидає історію навігації."""
        self.dir_history = []
        self.dir_history_index = -1
        self._update_navigation_buttons_state()

    def _update_history(self, new_path):
        """Оновлює історію після успішної зміни каталогу."""
        if self.is_navigating_history:
            self.is_navigating_history = False  # Скидаємо прапорець тут
            # Оновлюємо кнопки, але не змінюємо саму історію
            self._update_navigation_buttons_state() 
            return

        # Якщо ми знаходимось не в кінці історії (тобто, були натискання "Назад"),
        # і переходимо до нового каталогу, то "майбутня" історія видаляється.
        if self.dir_history_index < len(self.dir_history) - 1:
            self.dir_history = self.dir_history[:self.dir_history_index + 1]

        # Уникаємо дублювання однакових шляхів поспіль
        if not self.dir_history or self.dir_history[-1] != new_path:
            self.dir_history.append(new_path)
            self.dir_history_index = len(self.dir_history) - 1
        
        self._update_navigation_buttons_state()

    def _navigate_to_path(self, path):
        """Централізований метод для навігації до вказаного шляху."""
        if not self.sftp_client.sftp or (self.dir_operation_thread and self.dir_operation_thread.isRunning()):
            return
        
        if path == self.sftp_client.current_directory:
            return

        self.remote_table.setEnabled(False)
        self.setCursor(Qt.WaitCursor)

        self.dir_operation_thread = DirectoryOperationThread(self.sftp_client, self.sftp_lock, 'chdir', path=path)
        self.dir_operation_thread.change_dir_complete.connect(self._handle_change_dir_complete)
        self.dir_operation_thread.error.connect(self._handle_operation_error)
        self.dir_operation_thread.finished.connect(self._on_dir_operation_finished)
        self.dir_operation_thread.start()

    def navigate_back(self):
        """Переходить до попереднього каталогу в історії."""
        if self.dir_history_index > 0:
            self.is_navigating_history = True
            self.dir_history_index -= 1
            path_to_go = self.dir_history[self.dir_history_index]
            self._navigate_to_path(path_to_go)
            self._update_navigation_buttons_state()

    def navigate_forward(self):
        """Переходить до наступного каталогу в історії."""
        if self.dir_history_index < len(self.dir_history) - 1:
            self.is_navigating_history = True
            self.dir_history_index += 1
            path_to_go = self.dir_history[self.dir_history_index]
            self._navigate_to_path(path_to_go)
            self._update_navigation_buttons_state()


    # У класі MainWindow
    def connect_to_server(self, server_data, restore_session=False):
        self._reset_history()
        server_name = server_data.get('name', server_data.get('host'))
        full_server_data = self.server_manager.get_server_credentials(server_name)

        if not full_server_data or full_server_data.get('password') is None:
            if full_server_data: full_server_data = full_server_data.copy()
            else: full_server_data = server_data.copy()
            
            dialog = PasswordPromptDialog(server_name, self)
            if dialog.exec():
                password = dialog.get_password()
                if password:
                    full_server_data['password'] = password
                    try:
                        keyring.set_password(APP_SERVICE_NAME, server_name, password)
                        if not self.server_manager.get_server(server_name):
                            data_to_save = full_server_data.copy()
                            data_to_save.pop('password', None)
                            self.server_manager.add_server(data_to_save)
                    except Exception as e:
                        self.log_event_message(lang["MAINWINDOW_ERROR_SAVING_PASSWORD"].format(e=e))
                else:
                    self.log_event_message(lang["MAINWINDOW_CONNECT_CANCELED_NO_PASS"].format(server_name=server_name))
                    return
            else:
                self.log_event_message(lang["MAINWINDOW_CONNECT_CANCELED_BY_USER"].format(server_name=server_name))
                return

        self.log_event_message(lang["MAINWINDOW_CONNECTING_TO"].format(host=full_server_data['host']))
        
        success, message = self.sftp_client.connect(
            full_server_data['host'], full_server_data['port'],
            full_server_data['username'], full_server_data.get('password'),
            full_server_data['directory'], key_filename=full_server_data.get("key_filename")
        )
        
        if success:
            server_name_for_log = full_server_data.get('name', full_server_data['host'])
            self.sftp_client.connection_details['name'] = server_name_for_log
            self.log_event_message(lang["MAINWINDOW_CONNECTED_TO"].format(server=server_name_for_log))
            
            self.right_panel_stack.setCurrentWidget(self.remote_widget)
            self.disconnect_action.setEnabled(True)
            self.bookmark_action_button.setEnabled(True)
            self.update_bookmarks_menu()
            for action in self.connection_actions: action.setEnabled(True)
            self.update_action_states()
            
            # --- ПОЧАТОК НОВОЇ ЛОГІКИ ПОСЛІДОВНОСТІ ---
            # Створюємо callback-функцію, яка буде викликана після очищення
            # lambda використовується, щоб передати аргумент restore_session
            post_cleanup_action = lambda: self._post_connection_setup(restore_session=restore_session)
            
            # Запускаємо очищення, передаючи йой нашу функцію
            self.run_pending_cleanup(server_name_for_log, on_finish_callback=post_cleanup_action)
            # --- КІНЕЦЬ НОВОЇ ЛОГІКИ ПОСЛІДОВНОСТІ ---
        else:
            QMessageBox.warning(self, lang["MAINWINDOW_CONNECTION_ERROR_TITLE"], message)
            self.log_event_message(lang["MAINWINDOW_CONNECTION_ERROR_LOG"].format(message=message))

    def disconnect(self):
        self.stop_connection_check()
        self.is_reconnecting = False
        self.cancel_all_transfers()
        if self.group_fetcher_thread and self.group_fetcher_thread.isRunning():
            self.group_fetcher_thread.terminate()
            self.group_fetcher_thread.wait()
        self.sftp_client.disconnect()
        self._reset_history()
        self.remote_model.setFiles([])
        self.server_list_widget.load_servers()
        self.right_panel_stack.setCurrentWidget(self.server_list_widget)
        self.disconnect_action.setEnabled(False)
        self.bookmark_action_button.setEnabled(False)
        self.update_bookmarks_menu()
        self.internal_clipboard.clear()
        for action in self.connection_actions: action.setEnabled(False)
        self.log_event_message(lang["MAINWINDOW_DISCONNECTED"])
        self.settings_manager.set_last_session("", "")
        self.remote_path_edit.clear()
        self.pending_uploads = []
        self.update_bookmark_button_status()

    def cancel_all_transfers(self):
        # Виправлено: отримуємо ID всіх активних завдань безпосередньо з панелі
        for task_id in list(self.transfers_panel.tasks.keys()):
            self.cancel_transfer(task_id)
        self.log_event_message(lang["MAINWINDOW_ALL_TRANSFERS_CANCELED"])

    def apply_saved_sort(self):
        if not self.sftp_client.connected: return
        col, order_int = self.settings_manager.get_sort_settings()
        order_enum = Qt.AscendingOrder if order_int == 0 else Qt.DescendingOrder
        self.remote_table.sortByColumn(col, order_enum)

    def is_current_path_bookmarked(self):
        if not self.sftp_client.sftp or not self.sftp_client.connection_details: return None
        server_name = self.sftp_client.connection_details.get('name')
        if not server_name: return None
        server = self.server_manager.get_server(server_name)
        if server:
            bookmarks = server.get('bookmarks', [])
            current_path = self.sftp_client.current_directory
            for bm in bookmarks:
                if bm['path'] == current_path: return bm
        return None

    def update_bookmark_button_status(self):
        is_bookmarked = self.is_current_path_bookmarked()
        if qta:
            if is_bookmarked:
                self.bookmark_action_button.setIcon(qta.icon('fa6s.star', color='white'))
                self.bookmark_action_button.setToolTip(lang["MAINWINDOW_TOOLTIP_EDIT_DELETE_BOOKMARK"])
            else:
                self.bookmark_action_button.setIcon(qta.icon('fa6s.star', color='#8e9297', opacity=0.7))
                self.bookmark_action_button.setToolTip(lang["MAINWINDOW_TOOLTIP_ADD_BOOKMARK"])
        else:
            self.bookmark_action_button.setText("★" if is_bookmarked else "☆")
            self.bookmark_action_button.setStyleSheet(self.active_bookmark_style if is_bookmarked else self.inactive_bookmark_style)

    def show_bookmark_action_menu(self):
        if not self.sftp_client.sftp: return
        menu = QMenu(self)
        existing_bookmark = self.is_current_path_bookmarked()
        if existing_bookmark:
            edit_action = QAction(qta.icon("fa6s.pencil") if qta else QIcon(), lang["MAINWINDOW_ACTION_EDIT_BOOKMARK"], self)
            edit_action.triggered.connect(lambda: self.edit_bookmark(existing_bookmark))
            menu.addAction(edit_action)
            delete_action = QAction(qta.icon("fa6s.trash") if qta else QIcon(), lang["MAINWINDOW_ACTION_DELETE_BOOKMARK"], self)
            delete_action.triggered.connect(lambda: self.delete_bookmark(existing_bookmark))
            menu.addAction(delete_action)
        else:
            add_action = QAction(qta.icon("fa6s.star") if qta else QIcon(), lang["MAINWINDOW_ACTION_ADD_BOOKMARK"], self)
            add_action.triggered.connect(self.add_bookmark)
            menu.addAction(add_action)
        menu.exec(self.bookmark_action_button.mapToGlobal(self.bookmark_action_button.rect().bottomLeft()))

    def add_bookmark(self):
        if not self.sftp_client.sftp or not self.sftp_client.connection_details: return
        current_path = self.sftp_client.current_directory
        dialog = BookmarkDialog(self, path=current_path)
        if dialog.exec():
            bookmark_data = dialog.get_bookmark_data()
            server_name = self.sftp_client.connection_details.get('name')
            if not server_name:
                 QMessageBox.critical(self, lang["ERROR"], lang["MAINWINDOW_UNKNOWN_SERVER_ERROR"])
                 return
            server = self.server_manager.get_server(server_name)
            if server:
                bookmarks = server.setdefault('bookmarks', [])
                bookmarks.append(bookmark_data)
                self.server_manager.save_servers()
                self.log_event_message(lang["MAINWINDOW_BOOKMARK_ADDED"].format(name=bookmark_data['name']))
                self.update_bookmarks_menu()
                self.update_bookmark_button_status()

    def edit_bookmark(self, bookmark):
        dialog = BookmarkDialog(self, path=bookmark['path'], name=bookmark['name'])
        if not dialog.exec(): return
        new_data = dialog.get_bookmark_data()
        server_name = self.sftp_client.connection_details.get('name')
        server = self.server_manager.get_server(server_name)
        if server:
            for i, bm in enumerate(server.get('bookmarks', [])):
                if bm['path'] == bookmark['path']:
                    server['bookmarks'][i]['name'] = new_data['name']
                    break
            self.server_manager.save_servers()
            self.log_event_message(lang["MAINWINDOW_BOOKMARK_UPDATED"].format(name=new_data['name']))
            self.update_bookmarks_menu()
            self.update_bookmark_button_status()

    def delete_bookmark(self, bookmark, confirm=True):
        do_delete = False
        if not confirm:
            do_delete = True
        elif QMessageBox.question(self, lang["MAINWINDOW_DELETE_BOOKMARK_TITLE"], lang["MAINWINDOW_DELETE_BOOKMARK_PROMPT"].format(name=bookmark['name']), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            do_delete = True

        if do_delete:
            server_name = self.sftp_client.connection_details.get('name')
            server = self.server_manager.get_server(server_name)
            if server:
                bookmarks = server.get('bookmarks', [])
                bookmarks[:] = [bm for bm in bookmarks if bm['path'] != bookmark['path']]
                self.server_manager.save_servers()
                self.log_event_message(lang["MAINWINDOW_BOOKMARK_DELETED"].format(name=bookmark['name']))
                self.update_bookmarks_menu()
                self.update_bookmark_button_status()

    def update_bookmarks_menu(self):
        self.bookmarks_menu.clear()
        if not self.sftp_client.sftp or not self.sftp_client.connection_details:
            self.bookmarks_menu.setEnabled(False)
            return
        server_name = self.sftp_client.connection_details.get('name')
        if not server_name:
            self.bookmarks_menu.setEnabled(False)
            return
        current_dir = self.sftp_client.current_directory
        server = self.server_manager.get_server(server_name)
        bookmarks = server.get('bookmarks', [])
        if bookmarks:
            self.bookmarks_menu.setEnabled(True)
            for bookmark in sorted(bookmarks, key=lambda x: x['name']):
                action = QAction(qta.icon("fa6s.star"), bookmark['name'], self) if qta else QAction(f"★ {bookmark['name']}", self)
                action.setToolTip(bookmark['path'])
                action.triggered.connect(lambda checked=False, bm=bookmark: self.navigate_to_bookmark(bm))
                if bookmark['path'] == current_dir:
                    font = action.font()
                    font.setBold(True)
                    action.setFont(font)
                self.bookmarks_menu.addAction(action)
        else:
            no_bookmarks_action = QAction(lang["MAINWINDOW_NO_SAVED_BOOKMARKS"], self)
            no_bookmarks_action.setEnabled(False)
            self.bookmarks_menu.addAction(no_bookmarks_action)
            self.bookmarks_menu.setEnabled(False)

    def navigate_to_bookmark(self, bookmark):
        if not self.sftp_client.sftp: return
        
        self.active_bookmark_navigation = bookmark
        self.remote_path_edit.setText(bookmark['path'])
        self.remote_path_changed()

    def handle_upload_scan_error(self, local_path, error_message):
        log_msg = lang["MAINWINDOW_SCAN_ERROR_LOG"].format(name=os.path.basename(local_path), error=error_message)
        self.log_event_message(f"<span style='color: #f04747;'>{log_msg}</span>")
        QMessageBox.warning(self, lang["MAINWINDOW_SCAN_ERROR_TITLE"], log_msg)

    def handle_scan_error(self, error_message):
        self.log_event_message(f"<span style='color: #f04747;'>{error_message}</span>")
        QMessageBox.warning(self, lang["ERROR"], error_message)

    def show_remote_context_menu(self, position):
        if not self.sftp_client.sftp:
            return
        menu = QMenu()
        index = self.remote_table.indexAt(position)
        if index.isValid():
            selected = self.remote_table.selectionModel().selectedRows()
            selected_files = [self.remote_model.files[idx.row()] for idx in selected if self.remote_model.files[idx.row()]['name'] != ".."]
            if not selected_files:
                return
            if len(selected_files) == 1:
                file_info = selected_files[0]
                if file_info['is_dir']:
                    open_dir_action = QAction(qta.icon("fa6s.folder-open") if qta else QIcon(), lang["MAINWINDOW_ACTION_OPEN"], self)
                    open_dir_action.triggered.connect(lambda: self.remote_item_double_clicked(selected[0]))
                    menu.addAction(open_dir_action)
                    sync_dir_action = QAction(qta.icon("fa6s.arrows-rotate") if qta else QIcon(), lang.get("SYNC_FOLDER", "Sync folder..."), self)
                    remote_dir_path = f"{self.sftp_client.current_directory}/{file_info['name']}".replace("//", "/")
                    sync_dir_action.triggered.connect(lambda checked=False, r_path=remote_dir_path: self.trigger_sync_dir(r_path))
                    menu.addAction(sync_dir_action)
                else:
                    open_action = QAction(qta.icon("fa6s.pen-to-square") if qta else QIcon(), lang["MAINWINDOW_ACTION_OPEN_IN_EDITOR"], self)
                    open_action.triggered.connect(lambda: self.remote_item_double_clicked(selected[0]))
                    menu.addAction(open_action)
            download_action = QAction(qta.icon("fa6s.download") if qta else QIcon(), lang["MAINWINDOW_ACTION_DOWNLOAD"], self)
            download_action.triggered.connect(lambda: self.download_selected_items(selected_files))
            menu.addAction(download_action)
            download_archive_action = QAction(qta.icon("fa6s.bolt") if qta else QIcon(), lang["MAINWINDOW_ACTION_DOWNLOAD_ARCHIVE"], self)
            download_archive_action.triggered.connect(lambda: self.download_selected_items_as_archive(selected_files))
            menu.addAction(download_archive_action)
            menu.addSeparator()
            menu.addAction(self.cut_action)
            menu.addAction(self.copy_action)
            menu.addSeparator()
            if len(selected_files) == 1:
                rename_action = QAction(qta.icon("fa6s.i-cursor") if qta else QIcon(), lang["RENAME_TITLE"], self)
                rename_action.triggered.connect(lambda: self.remote_table.edit(selected[0]))
                menu.addAction(rename_action)
            menu.addAction(self.delete_action)
            menu.addSeparator()
            archive_action = QAction(qta.icon("fa6s.file-zipper") if qta else QIcon(), lang["MAINWINDOW_ACTION_CREATE_ZIP"], self)
            archive_action.triggered.connect(lambda: self.create_zip_archive_from_selection([f['name'] for f in selected_files]))
            menu.addAction(archive_action)
            if len(selected_files) == 1 and not selected_files[0]['is_dir'] and selected_files[0]['name'].lower().endswith('.zip'):
                extract_action = QAction(qta.icon("fa6s.box-open") if qta else QIcon(), lang["MAINWINDOW_ACTION_EXTRACT_ZIP"], self)
                extract_action.triggered.connect(lambda: self.extract_zip_archive(selected_files[0]['name']))
                menu.addAction(extract_action)
            menu.addSeparator()
            # Створюємо підменю для керування доступом
            access_menu = QMenu(lang["ACCESS_CONTROL_TITLE"], self)
            if qta:
                access_menu.setIcon(qta.icon("fa6s.shield-halved"))
            perm_action = QAction(qta.icon("fa6s.lock") if qta else QIcon(), lang["CHANGE_PERMISSIONS_TITLE"], self)
            perm_action.triggered.connect(lambda: self.edit_permissions(selected_files))
            access_menu.addAction(perm_action)
            change_group_action = QAction(qta.icon("fa6s.users") if qta else QIcon(), lang["CHANGE_GROUP_TITLE"], self)
            change_group_action.triggered.connect(lambda: self.change_remote_item_group(selected_files))
            access_menu.addAction(change_group_action)
            menu.addMenu(access_menu)
        else:
            menu.addAction(self.paste_action)
            if self.paste_action.isEnabled():
                menu.addSeparator()
            create_dir_action = QAction(qta.icon("fa6s.folder-plus") if qta else QIcon(), lang["MAINWINDOW_ACTION_CREATE_DIR_CONTEXT"], self)
            create_dir_action.triggered.connect(self.create_remote_directory)
            menu.addAction(create_dir_action)
            create_file_action = QAction(qta.icon("fa6s.file-circle-plus") if qta else QIcon(), lang["MAINWINDOW_ACTION_CREATE_FILE_CONTEXT"], self)
            create_file_action.triggered.connect(self.create_remote_file)
            menu.addAction(create_file_action)
            menu.addSeparator()
            sync_action = QAction(qta.icon("fa6s.arrows-rotate") if qta else QIcon(), lang.get("SYNC_FOLDER", "Sync folder..."), self)
            sync_action.triggered.connect(self.trigger_sync_current_dir)
            menu.addAction(sync_action)
            menu.addSeparator()
            menu.addAction(self.refresh_action_menu)
            menu.addAction(self.up_action_menu)
        menu.exec(self.remote_table.viewport().mapToGlobal(position))
        
    def trigger_sync_current_dir(self):
        self.trigger_sync_dir(self.sftp_client.current_directory)

    def trigger_sync_dir(self, remote_dir_path):
        if not self.sftp_client.sftp:
            return
        last_path = self.settings_manager.get_last_sync_path()
        default_dir = last_path if (last_path and os.path.exists(last_path)) else os.path.expanduser("~")
        local_dir = QFileDialog.getExistingDirectory(self, lang.get("SELECT_LOCAL_FOLDER_FOR_SYNC", "Select local folder for synchronization"), default_dir)
        if not local_dir:
            return
        self.settings_manager.set_last_sync_path(local_dir)
        
        dialog = SyncDialog(self, self.sftp_client, remote_dir_path, local_dir, self.settings_manager)
        if dialog.exec():
            uploads, downloads = dialog.get_selected_transfers()
            
            if uploads:
                task_id = f"task_sync_upload_{time.time()}"
                task_name = f"Sync Upload: {os.path.basename(local_dir)}"
                self.transfer_tasks[task_id] = {
                    "name": task_name, "is_upload": True, "files_completed": 0,
                    "files_failed": 0,
                    "transferred_size": 0, "active_files_progress": {}, "collected_files": uploads
                }
                self.transfers_panel.add_task(task_id, task_name, is_upload=True)
                self.start_conflict_resolution(task_id, uploads, local_base_path=local_dir)
                
            if downloads:
                task_id = f"task_sync_download_{time.time()}"
                task_name = f"Sync Download: {os.path.basename(remote_dir_path)}"
                self.transfer_tasks[task_id] = {
                    "name": task_name, "is_upload": False, "files_completed": 0,
                    "files_failed": 0,
                    "transferred_size": 0, "active_files_progress": {}, "collected_files": downloads
                }
                self.transfers_panel.add_task(task_id, task_name, is_upload=False)
                self.start_conflict_resolution(task_id, downloads, local_base_path=local_dir)

    def handle_copy_or_cut(self, operation):
        selected_rows = self.remote_table.selectionModel().selectedRows()
        if not selected_rows: return
        
        items_to_process = [self.remote_model.files[index.row()] for index in selected_rows if self.remote_model.files[index.row()]['name'] != ".."]
        source_directory = self.sftp_client.current_directory
        
        if items_to_process:
            self.internal_clipboard = {
                "operation": operation, "items": items_to_process, "source_dir": source_directory
            }
            log_message = lang["MAINWINDOW_ITEMS_READY_TO_MOVE"] if operation == 'cut' else lang["MAINWINDOW_ITEMS_READY_TO_COPY"]
            self.log_event_message(log_message.format(count=len(items_to_process)))
            self.update_action_states()
            self.remote_model.layoutChanged.emit()

    def handle_paste(self):
        if not self.internal_clipboard: return
        dest_dir = self.sftp_client.current_directory
        operation = self.internal_clipboard["operation"]
        source_items = self.internal_clipboard["items"]
        source_dir = self.internal_clipboard["source_dir"]

        if operation == 'copy' and source_dir == dest_dir:
            self.log_event_message(lang["MAINWINDOW_PASTE_SAME_FOLDER_LOG"].format(count=len(source_items)))
            for file_info in source_items:
                self.duplicate_remote_item(file_info)
            self.internal_clipboard.clear()
            self.update_action_states()
            self.refresh_remote()
            return

        self.log_event_message(lang["MAINWINDOW_PASTING_ITEMS_LOG"].format(count=len(source_items), dest=dest_dir))
        for file_info in source_items:
            base_name = file_info['name']
            source_path = f"{source_dir}/{base_name}".replace("//", "/")
            dest_path = f"{dest_dir}/{base_name}".replace("//", "/")
            
            if dest_path.startswith(source_path + '/') and operation == "cut":
                self.log_event_message(lang["MAINWINDOW_MOVE_INTO_SELF_ERROR"].format(name=base_name))
                continue
            
            if source_path == dest_path and operation == "cut":
                continue

            op_func = self.sftp_client.move_item if operation == "cut" else self.sftp_client.copy_item
            success, message = op_func(source_path, dest_path)
            
            if success:
                log_msg = lang["MAINWINDOW_ITEM_MOVED"] if operation == 'cut' else lang["MAINWINDOW_ITEM_COPIED"]
                self.log_event_message(log_msg.format(name=base_name))
            else:
                self.log_event_message(lang["MAINWINDOW_PASTE_ERROR_FOR_ITEM"].format(name=base_name, error=message))
                title = lang["MAINWINDOW_PASTE_ERROR_TITLE"].format(op=operation)
                msg_body = lang["MAINWINDOW_PASTE_ERROR_MSG"].format(name=base_name, error=message)
                QMessageBox.warning(self, title, msg_body)

        self.internal_clipboard.clear()
        self.update_action_states()
        self.refresh_remote()

    def handle_delete_action_triggered(self):
        selected_rows = self.remote_table.selectionModel().selectedRows()
        selected_files = [self.remote_model.files[idx.row()] for idx in selected_rows if self.remote_model.files[idx.row()]['name'] != ".."]
        if selected_files:
            self.delete_remote_items(selected_files)
        
    def duplicate_remote_item(self, file_info):
        if not self.sftp_client.sftp: return
        dialog = DuplicateDialog(self, original_name=file_info['name'])
        if dialog.exec():
            new_name = dialog.get_new_name()
            if new_name and new_name != file_info['name']:
                self.log_event_message(lang["MAINWINDOW_DUPLICATING_ITEM_LOG"].format(old_name=file_info['name'], new_name=new_name))
                success, message = self.sftp_client.duplicate_item(file_info['name'], new_name)
                if success:
                    self.log_event_message(message)
                    self.refresh_remote()
                else:
                    self.log_event_message(lang["MAINWINDOW_DUPLICATE_ERROR_LOG"].format(error=message))
                    QMessageBox.warning(self, lang["MAINWINDOW_DUPLICATE_ERROR_TITLE"], message)
    
    def change_remote_item_group(self, selected_files):
        if not self.sftp_client.sftp or not selected_files: return
        try:
            stdin, stdout, stderr = self.sftp_client.client.exec_command("getent group | cut -d: -f1")
            groups = stdout.read().decode('utf-8').strip().split('\n')
        except: groups = []
        initial_group = selected_files[0]['group']
        is_dir_selected = any(f['is_dir'] for f in selected_files)
        dialog = ChangeGroupDialog(self, initial_group, groups, is_dir=is_dir_selected)
        if dialog.exec():
            new_group, recursive = dialog.get_new_group()
            if new_group:
                for file_info in selected_files:
                    apply_recursive = recursive and file_info['is_dir']
                    self.log_event_message(lang["MAINWINDOW_CHANGING_GROUP_FOR"].format(name=file_info['name'], group=new_group))
                    success, message = self.sftp_client.change_group(file_info['name'], new_group, apply_recursive)
                    if success:
                        self.log_event_message(lang["MAINWINDOW_GROUP_CHANGED_FOR"].format(name=file_info['name']))
                    else:
                        title = lang["MAINWINDOW_CHANGE_GROUP_ERROR_TITLE"]
                        msg_body = lang["MAINWINDOW_CHANGE_GROUP_ERROR_MSG"].format(name=file_info['name'], error=message)
                        QMessageBox.warning(self, title, msg_body)
                        self.log_event_message(lang["MAINWINDOW_PASTE_ERROR_FOR_ITEM"].format(name=file_info['name'], error=message))
                self.load_remote_files()

    def delete_remote_items(self, items):
        num_files = sum(1 for item in items if not item['is_dir'])
        num_dirs = sum(1 for item in items if item['is_dir'])

        if num_files == 0 and num_dirs == 0:
            return

        dialog = DeleteConfirmationDialog(num_files, num_dirs, self)
        
        if dialog.exec() == QDialog.Accepted:
            errors, success_count = [], 0
            for is_dir in [False, True]:
                for item in items:
                    if item['is_dir'] == is_dir:
                        log_msg = lang["MAINWINDOW_DELETING_DIR"] if is_dir else lang["MAINWINDOW_DELETING_FILE"]
                        self.log_event_message(log_msg.format(name=item['name']))
                        success, msg = self.sftp_client.delete_directory_recursive(item['name']) if is_dir else self.sftp_client.delete_file(item['name'])
                        if success:
                            success_count += 1
                        else:
                            errors.append(f"{item['name']}: {msg}")
            
            if not errors:
                log_msg = lang["MAINWINDOW_ITEM_DELETED_SUCCESSFULLY"] if success_count == 1 else lang["MAINWINDOW_ITEMS_DELETED_SUCCESSFULLY"].format(count=success_count)
                self.log_event_message(log_msg)
            else:
                error_log_msg = lang["MAINWINDOW_DELETE_PARTIAL_ERROR"].format(count=success_count) if success_count > 0 else lang["MAINWINDOW_DELETE_TOTAL_ERROR"]
                self.log_event_message(f"<span style='color: #f04747;'>{error_log_msg}</span>")
                detailed_error_msg = f"{error_log_msg}:\n\n" + "\n".join(errors)
                QMessageBox.warning(self, lang["MAINWINDOW_DELETE_ERROR_TITLE"], detailed_error_msg)
            
            self.refresh_remote()
            
    def refresh_remote(self):
        if not self.sftp_client.check_connection():
            self.log_event_message(lang["MAINWINDOW_CONNECTION_LOST"])
            self.is_reconnecting = True
            self.attempt_reconnect()
            return
        self.load_remote_files()
    
    def edit_permissions(self, selected_files):
        if not selected_files: return
        initial_permissions = selected_files[0]['permissions']
        is_dir_selected = any(f['is_dir'] for f in selected_files)
        dialog = PermissionsDialog(self, initial_permissions, is_dir=is_dir_selected)
        if dialog.exec():
            new_permissions, recursive = dialog.get_permissions()
            for file_info in selected_files:
                apply_recursive = recursive and file_info['is_dir']
                self.log_event_message(lang["MAINWINDOW_CHANGING_PERMISSIONS_FOR"].format(name=file_info['name']))
                success, message = self.sftp_client.change_permissions(file_info['name'], new_permissions, apply_recursive)
                if success:
                    self.log_event_message(f"{message} для '{file_info['name']}'")
                else:
                    self.log_event_message(lang["MAINWINDOW_PASTE_ERROR_FOR_ITEM"].format(name=file_info['name'], error=message))
                    title = lang["MAINWINDOW_PERMISSIONS_ERROR_TITLE"]
                    msg_body = lang["MAINWINDOW_PERMISSIONS_ERROR_MSG"].format(name=file_info['name'], error=message)
                    QMessageBox.warning(self, title, msg_body)
            self.load_remote_files()

    def download_selected_items(self, selected_files, preselected_dir=None):
        if not self.sftp_client.sftp: return

        local_dir = preselected_dir
        if not local_dir:
            local_dir = QFileDialog.getExistingDirectory(self, lang["MAINWINDOW_SELECT_SAVE_FOLDER"])

        if not local_dir: return

        # --- ЗМІНЕНО: Використовуємо новий генератор для створення заголовка ---
        task_name = self._generate_smart_task_name(selected_files, lang["DOWNLOADING"])
        
        task_id = f"task_download_batch_{time.time()}"
        source_path = self.sftp_client.current_directory
        self.log_event_message(lang["MAINWINDOW_DOWNLOAD_START_LOG"].format(count=len(selected_files), source=source_path, dest=local_dir))

        self.transfer_tasks[task_id] = {
            "name": task_name, "is_upload": False, "files_completed": 0,
            "files_failed": 0,
            "transferred_size": 0, "active_files_progress": {}, "collected_files": []
        }
        self.transfers_panel.add_task(task_id, task_name, is_upload=False)
        self.transfers_panel.set_task_indeterminate(task_id, lang["MAINWINDOW_SCANNING"])

        items_to_scan = [f['name'] for f in selected_files if f['is_dir']]
        direct_files_to_add = [f for f in selected_files if not f['is_dir']]

        for file_info in direct_files_to_add:
            remote_path = f"{self.sftp_client.current_directory}/{file_info['name']}".replace("//", "/")
            local_path = os.path.join(local_dir, file_info['name'])
            mtime = file_info.get('date_modified').timestamp() if file_info.get('date_modified') else 0
            self.transfer_tasks[task_id]["collected_files"].append((remote_path, local_path, mtime, file_info['size']))

        if items_to_scan:
            thread = OptimizedDirectoryScannerThread(
                ssh_client=self.sftp_client.client,
                remote_base_dir=self.sftp_client.current_directory,
                local_base_dir=local_dir,
                files_to_scan=items_to_scan
            )
            thread.scan_complete.connect(lambda files, tid=task_id, ldir=local_dir: self._handle_optimized_scan_complete(tid, files, ldir))
            thread.error.connect(self.handle_scan_error)
            thread.finished.connect(thread.deleteLater)
            self.worker_threads.append(thread)
            thread.start()
        else:
            self.log_event_message(lang["MAINWINDOW_NO_FOLDERS_TO_SCAN"])
            self.start_conflict_resolution(task_id, self.transfer_tasks[task_id]["collected_files"], local_base_path=local_dir)

    def download_selected_items_as_archive(self, selected_files):
        """
        Запускає процес швидкого скачування (архівом) для обраних файлів.
        Спочатку запитує у користувача теку для збереження.
        """
        if not self.sftp_client.sftp or not selected_files:
            return

        # 1. Запитуємо у користувача, куди зберегти файл
        destination_dir = QFileDialog.getExistingDirectory(self, lang["MAINWINDOW_SELECT_SAVE_FOLDER"])

        # 2. Якщо користувач обрав теку, запускаємо існуючу логіку архівації
        if destination_dir:
            self._initiate_server_side_archiving(selected_files, destination_dir)

    def _handle_optimized_scan_complete(self, task_id, scanned_files, local_dir):
        task = self.transfer_tasks.get(task_id)
        if not task:
            return

        task["collected_files"].extend(scanned_files)
        
        self.log_event_message(lang["MAINWINDOW_DOWNLOAD_SCAN_COMPLETE"].format(name=task['name'], count=len(task['collected_files'])))
        # Передаємо local_dir в функцію запуску
        self.start_conflict_resolution(task_id, task["collected_files"], local_base_path=local_dir)

    # --- ЗМІНЕНО: Метод тепер приймає 'selected_files' для генерації заголовка ---
    def _download_and_process_archive(self, selected_files, remote_archive_path, extract_to_dir):
        archive_filename = os.path.basename(remote_archive_path)
        local_temp_archive_path = os.path.join(tempfile.gettempdir(), archive_filename)
        task_id = f"task_download_archive_{archive_filename.replace(' ', '_')}_{time.time()}"

        # --- ЗМІНЕНО: Використовуємо наш генератор для створення красивого заголовка ---
        task_name = self._generate_smart_task_name(
            selected_files,
            lang["QUICK_DOWNLOAD_TASK_TITLE"]
        )
        
        self.transfer_tasks[task_id] = {
            "name": task_name, "is_upload": False, "files_completed": 0,
            "files_failed": 0,
            "transferred_size": 0, "active_files_progress": {},
            "is_archive_download": True, "extract_to_dir": extract_to_dir,
            "local_archive_path": local_temp_archive_path,
            "remote_archive_path_to_delete": remote_archive_path
        }
        
        self.transfers_panel.add_task(task_id, task_name, is_upload=False)
        
        files_to_download = [(remote_archive_path, local_temp_archive_path, 0, 0)]
        self._finalize_task_creation(task_id, files_to_download)

    # КРОК 2.2: ПОВНІСТЮ ЗАМІНІТЬ ЦЕЙ МЕТОД
    def _prepare_archive_extraction(self, task_id, local_archive_path, extract_to_dir, remote_path_to_delete):
        conflicts = []
        non_conflicts = []
        
        try:
            with zipfile.ZipFile(local_archive_path, 'r') as zf:
                for member in zf.infolist():
                    target_path = os.path.join(extract_to_dir, member.filename)
                    
                    # Конфліктом вважаємо тільки файли, каталоги просто створюються
                    if os.path.exists(target_path) and not member.is_dir():
                        local_stat = os.stat(target_path)
                        conflicts.append({
                            "archive_member": member,
                            "source_meta": {
                                'mtime': datetime(*member.date_time).timestamp(),
                                'size': member.file_size
                            },
                            "dest_meta": {
                                'mtime': local_stat.st_mtime,
                                'size': local_stat.st_size
                            }
                        })
                    else:
                        non_conflicts.append(member)
        except Exception as e:
            QMessageBox.warning(self, lang["MAINWINDOW_ARCHIVE_READ_ERROR_TITLE"], lang["MAINWINDOW_ARCHIVE_READ_ERROR_MSG"].format(e=e))
            self.cancel_transfer(task_id)
            return

        final_members_to_extract = list(non_conflicts)
        
        if conflicts:
            self.overwrite_action = None
            for conflict in conflicts:
                action = self.overwrite_action
                if not action:
                    dialog = AdvancedOverwriteDialog(
                        os.path.basename(conflict['archive_member'].filename),
                        conflict['source_meta'],
                        conflict['dest_meta'],
                        'download',
                        self
                    )
                    dialog_result = dialog.exec()
                    choice, apply_to_all = dialog.get_choice()
                    action = 'cancel' if not dialog_result and choice == 'cancel' else choice
                    if apply_to_all:
                        self.overwrite_action = action
                
                if action == 'cancel':
                    self.log_event_message(lang["MAINWINDOW_EXTRACT_CANCELED_CONFLICT"])
                    # Видаляємо тимчасові архіви
                    if os.path.exists(local_archive_path): os.remove(local_archive_path)
                    self.sftp_client.delete_file(remote_path_to_delete)
                    self.refresh_remote()
                    self.transfers_panel.complete_transfer(task_id, False, lang["MAINWINDOW_CANCELED_BY_USER"])
                    if task_id in self.transfer_tasks: del self.transfer_tasks[task_id]
                    return

                if action == 'overwrite':
                    final_members_to_extract.append(conflict['archive_member'])
                elif action == 'update':
                    if conflict['source_meta']['mtime'] > conflict['dest_meta']['mtime']:
                        final_members_to_extract.append(conflict['archive_member'])

        # Якщо скасування не було, запускаємо розпакування обраних файлів
        self.start_archive_extraction(local_archive_path, extract_to_dir, remote_path_to_delete, final_members_to_extract)

    # КРОК 2.1: ДОДАЙТЕ ЦЕЙ НОВИЙ МЕТОД У КЛАС MainWindow
    def start_archive_extraction(self, local_archive_path, extract_to_dir, remote_path_to_delete, members_to_extract):
        self.log_event_message(lang["MAINWINDOW_EXTRACTING_ARCHIVE_START"].format(archive_name=os.path.basename(local_archive_path)))
        
        # Створюємо потік для розпакування, передаючи йому список файлів
        self.extractor_thread = ArchiveExtractorThread(local_archive_path, extract_to_dir, members_to_extract)
        self.extractor_thread.finished_signal.connect(lambda msg: self.on_extraction_finished(msg, remote_path_to_delete))
        self.extractor_thread.error_signal.connect(self.on_extraction_error)
        
        self.worker_threads.append(self.extractor_thread) 
        self.extractor_thread.finished.connect(self._on_worker_thread_finished)
        
        self.extractor_thread.start()


    def _initiate_server_side_archiving(self, selected_files, destination_dir):
        """Створює архів на сервері та запускає процес його завантаження і розпаковки."""
        if not self.sftp_client.sftp or not destination_dir:
            return

        base_name = os.path.basename(selected_files[0]['name']) if len(selected_files) == 1 else "archive"
        archive_name = f"{base_name}_{int(time.time())}.zip"
        files_to_archive = [f['name'] for f in selected_files]
        
        self.log_event_message(lang["MAINWINDOW_CHECKING_DISK_SPACE"])
        
        success, message = self.sftp_client.create_zip_archive(files_to_archive, archive_name)
        
        if not success:
            if message.startswith("INSUFFICIENT_SPACE"):
                try:
                    required_size_bytes = int(message.split(':')[1])
                    required_size_mb = f"{required_size_bytes / (1024*1024):.2f}"
                except:
                    required_size_mb = "?"
                self.log_event_message(lang["MAINWINDOW_INSUFFICIENT_SPACE_LOG"].format(required_space=required_size_mb))
                QMessageBox.information(self, lang["MAINWINDOW_INSUFFICIENT_SPACE_TITLE"], lang["MAINWINDOW_INSUFFICIENT_SPACE_LOG"].format(required_space=required_size_mb).replace("<span style='color: #faa61a;'>", "").replace("</span>", ""))
                
                self.download_selected_items(selected_files, preselected_dir=destination_dir)
                return

            elif message == "MISSING_ZIP":
                 if QMessageBox.question(self, lang["MAINWINDOW_ZIP_MISSING_TITLE"], lang["MAINWINDOW_ZIP_MISSING_PROMPT"], QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
                    self.log_event_message(lang["MAINWINDOW_INSTALLING_ZIP"])
                    success_install, install_message = self.sftp_client.install_package("zip")
                    if success_install:
                        self.log_event_message(lang["MAINWINDOW_ZIP_INSTALLED_RETRY"])
                        self._initiate_server_side_archiving(selected_files, destination_dir)
                    else:
                        QMessageBox.warning(self, lang["MAINWINDOW_ZIP_INSTALL_ERROR_TITLE"], install_message)
            else:
                self.log_event_message(lang["MAINWINDOW_ARCHIVE_CREATION_ERROR_LOG"].format(error=message))
                QMessageBox.warning(self, lang["MAINWINDOW_ARCHIVE_CREATION_ERROR_TITLE"], lang["MAINWINDOW_ARCHIVE_CREATION_ERROR_MSG"].format(error=message))
            return
            
        remote_archive_path = os.path.join(self.sftp_client.current_directory, archive_name).replace(os.path.sep, '/')
        
        server_name = self.sftp_client.connection_details.get('name')
        if server_name:
            self.settings_manager.add_pending_cleanup_file(server_name, remote_archive_path)
        else:
            self.log_event_message(lang["MAINWINDOW_ARCHIVE_TRACKING_ERROR"])

        self.log_event_message(lang["MAINWINDOW_ARCHIVE_CREATED_DOWNLOADING"].format(name=archive_name))
        
        # --- ЗМІНЕНО: Передаємо 'selected_files' у наступну функцію ---
        self._download_and_process_archive(selected_files, remote_archive_path, destination_dir)

    def create_remote_directory(self):
        if not self.sftp_client.sftp:
            QMessageBox.warning(self, lang["ERROR"], lang["CONNECT_TO_SERVER_FIRST"])
            return
        base_name = lang["MAINWINDOW_NEW_FOLDER_DEFAULT_NAME"]; new_name = base_name; counter = 1
        current_names = [f['name'] for f in self.remote_model.files]
        while new_name in current_names:
            new_name = f"{base_name}({counter})"; counter += 1
        self.log_event_message(lang["MAINWINDOW_CREATING_DIR"].format(name=new_name))
        if not self.sftp_client.check_connection():
            self.log_event_message(lang["MAINWINDOW_CONNECTION_LOST_RETRY"])
            if not self.is_reconnecting: self.is_reconnecting = True; self.attempt_reconnect()
            return
        success, message = self.sftp_client.create_directory(new_name)
        if success:
            self.log_event_message(lang["DIRECTORY_CREATED_SUCCESSFULLY"])
            self.file_to_edit_after_refresh = new_name
            self.refresh_remote()
        else:
            self.log_event_message(lang["MAINWINDOW_CREATE_DIR_ERROR_LOG"].format(error=message))
            QMessageBox.warning(self, lang["MAINWINDOW_CREATE_DIR_ERROR_TITLE"], message)
            
    def create_remote_file(self):
        if not self.sftp_client.sftp:
            QMessageBox.warning(self, lang["ERROR"], lang["CONNECT_TO_SERVER_FIRST"])
            return
        base_name = lang["MAINWINDOW_NEW_FILE_DEFAULT_NAME"]; extension = ".txt"; new_name = f"{base_name}{extension}"; counter = 1
        current_filenames = [f['name'] for f in self.remote_model.files]
        while new_name in current_filenames:
            new_name = f"{base_name}({counter}){extension}"; counter += 1
        self.log_event_message(lang["MAINWINDOW_CREATING_FILE"].format(name=new_name))
        success, message = self.sftp_client.create_empty_file(new_name)
        if success:
            self.log_event_message(lang["MAINWINDOW_FILE_CREATED_REFRESHING"].format(name=new_name))
            self.file_to_edit_after_refresh = new_name
            self.refresh_remote()
        else:
            self.log_event_message(lang["MAINWINDOW_CREATE_FILE_ERROR_LOG"].format(error=message))
            QMessageBox.warning(self, lang["MAINWINDOW_CREATE_FILE_ERROR_TITLE"], message)
    
    def create_zip_archive_from_selection(self, file_names):
        if not self.sftp_client.sftp:
            QMessageBox.warning(self, lang["ERROR"], lang["CONNECT_TO_SERVER_FIRST"])
            return
        archive_name = f"{file_names[0]}.zip" if len(file_names) == 1 else "archive.zip"
        archive_name, ok = QInputDialog.getText(self, lang["MAINWINDOW_ARCHIVE_NAME_TITLE"], lang["MAINWINDOW_ARCHIVE_NAME_PROMPT"], QLineEdit.Normal, archive_name)
        if ok and archive_name:
            file_names_str = ", ".join([f"'{name}'" for name in file_names])
            self.log_event_message(lang["MAINWINDOW_CREATING_ARCHIVE_FROM_ITEMS"].format(name=archive_name, items=file_names_str))
            if not self.sftp_client.check_connection():
                self.log_event_message(lang["MAINWINDOW_CONNECTION_LOST_RETRY"])
                if not self.is_reconnecting: self.is_reconnecting = True; self.attempt_reconnect()
                return
            success, message = self.sftp_client.create_zip_archive(file_names, archive_name)
            if success:
                self.log_event_message(lang["ARCHIVE_CREATED_SUCCESSFULLY"].format(archive_name=archive_name))
                self.load_remote_files()
            elif message == "MISSING_ZIP":
                if QMessageBox.question(self, lang["MAINWINDOW_ZIP_MISSING_TITLE"], lang["MAINWINDOW_ZIP_MISSING_PROMPT"], QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
                    self.log_event_message(lang["MAINWINDOW_INSTALLING_ZIP"])
                    success, install_message = self.sftp_client.install_package("zip")
                    if success:
                        self.log_event_message(lang["MAINWINDOW_ZIP_INSTALLED_RETRY"])
                        success, message = self.sftp_client.create_zip_archive(file_names, archive_name)
                        if success: 
                            self.log_event_message(lang["ARCHIVE_CREATED_SUCCESSFULLY"].format(archive_name=archive_name))
                            self.load_remote_files()
                        else: QMessageBox.warning(self, lang["MAINWINDOW_ARCHIVE_CREATION_ERROR_TITLE"], message)
                    else: QMessageBox.warning(self, lang["MAINWINDOW_ZIP_INSTALL_ERROR_TITLE"], install_message)
                else: QMessageBox.warning(self, lang["MAINWINDOW_ZIP_MISSING_TITLE"], lang["MAINWINDOW_ZIP_MISSING_ERROR"])
            else: QMessageBox.warning(self, lang["MAINWINDOW_ARCHIVE_CREATION_ERROR_TITLE"], message)
    
    def extract_zip_archive(self, archive_name):
        if not self.sftp_client.sftp:
            QMessageBox.warning(self, lang["ERROR"], lang["CONNECT_TO_SERVER_FIRST"])
            return
        if QMessageBox.question(self, lang["MAINWINDOW_EXTRACT_CONFIRM_TITLE"], lang["MAINWINDOW_EXTRACT_CONFIRM_PROMPT"].format(name=archive_name), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
            self.log_event_message(lang["MAINWINDOW_EXTRACTING_ARCHIVE_LOG"].format(name=archive_name))
            if not self.sftp_client.check_connection():
                self.log_event_message(lang["MAINWINDOW_CONNECTION_LOST_RETRY"])
                if not self.is_reconnecting: self.is_reconnecting = True; self.attempt_reconnect()
                return
            success, message = self.sftp_client.extract_zip_archive(archive_name)
            if success:
                self.log_event_message(lang["ARCHIVE_EXTRACTED_SUCCESSFULLY"].format(archive_name=archive_name))
                self.load_remote_files()
            elif message == "MISSING_UNZIP":
                if QMessageBox.question(self, lang["MAINWINDOW_UNZIP_MISSING_TITLE"], lang["MAINWINDOW_UNZIP_MISSING_PROMPT"], QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
                    self.log_event_message(lang["MAINWINDOW_INSTALLING_UNZIP"])
                    success, install_message = self.sftp_client.install_package("unzip")
                    if success:
                        self.log_event_message(lang["MAINWINDOW_UNZIP_INSTALLED_RETRY"])
                        success, message = self.sftp_client.extract_zip_archive(archive_name)
                        if success: 
                            self.log_event_message(lang["ARCHIVE_EXTRACTED_SUCCESSFULLY"].format(archive_name=archive_name))
                            self.load_remote_files()
                        else: QMessageBox.warning(self, lang["MAINWINDOW_EXTRACT_ERROR_TITLE"], message)
                    else: QMessageBox.warning(self, lang["MAINWINDOW_UNZIP_INSTALL_ERROR_TITLE"], install_message)
                else: QMessageBox.warning(self, lang["MAINWINDOW_UNZIP_MISSING_TITLE"], lang["MAINWINDOW_UNZIP_MISSING_ERROR"])
            else: QMessageBox.warning(self, lang["MAINWINDOW_EXTRACT_ERROR_TITLE"], message)
    
    def show_search_dialog(self):
        if not self.sftp_client.sftp:
            QMessageBox.warning(self, lang["ERROR"], lang["CONNECT_TO_SERVER_FIRST"])
            return

        dialog = SearchDialog(self, search_path=self.sftp_client.current_directory)
        dialog.file_open_requested.connect(self.handle_open_file_from_search)
        dialog.exec()

        self.search_thread = None

    def start_search(self, dialog, query, search_type, case_insensitive):
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.cancel()
            self.search_thread.wait()

        self.search_thread = SearchThread(
            ssh_client=self.sftp_client.client,
            base_path=self.sftp_client.current_directory,
            query=query, search_type=search_type, case_insensitive=case_insensitive
        )
        dialog.search_thread = self.search_thread
        self.search_thread.result_found.connect(dialog.add_result)
        self.search_thread.search_complete.connect(dialog.on_search_complete)
        self.search_thread.error.connect(dialog.on_search_error)
        self.search_thread.error.connect(lambda msg: self.log_event_message(lang["MAINWINDOW_SEARCH_ERROR_LOG"].format(error=msg)))
        self.search_thread.start()

    # У класі MainWindow
    def _open_remote_file_for_editing(self, remote_path, filename_for_log):
        editor_path = self.settings_manager.get_editor_path()
        if not editor_path:
            QMessageBox.warning(self, lang["ERROR"], lang["MAINWINDOW_EDITOR_NOT_CONFIGURED"])
            return

        self.log_event_message(lang["MAINWINDOW_OPENING_FILE_FOR_EDIT"].format(filename=filename_for_log))
        
        # --- ПОЧАТОК ВИПРАВЛЕННЯ ---
        # Правильний виклик методу з двома аргументами
        success, local_path_or_error, remote_path_from_sftp = self.sftp_client.download_for_edit(remote_path, editor_path)
        # --- КІНЕЦЬ ВИПРАВЛЕННЯ ---

        if success:
            local_path = local_path_or_error
            self.edited_files[local_path] = remote_path_from_sftp
            if local_path not in self.file_watcher.files():
                self.file_watcher.addPath(local_path)
            self.log_event_message(lang["MAINWINDOW_FILE_OPENED_IN_EDITOR"].format(filename=filename_for_log))
        else:
            error_message = local_path_or_error
            QMessageBox.warning(self, lang["MAINWINDOW_FILE_OPEN_ERROR_TITLE"], lang["MAINWINDOW_FILE_OPEN_ERROR_MSG"].format(error=error_message))
            self.log_event_message(lang["MAINWINDOW_FILE_OPEN_ERROR_LOG"].format(filename=filename_for_log, error=error_message))
            
    def handle_open_file_from_search(self, remote_path):
        if not self.sftp_client.sftp:
            return
        filename = remote_path.split('/')[-1]
        self._open_remote_file_for_editing(remote_path, filename)



    def closeEvent(self, event):
        if hasattr(self, 'reconnect_timer') and self.reconnect_timer.isActive():
            self.reconnect_timer.stop()
        self.cancel_all_transfers()
        if self.sftp_client.sftp:
            self.sftp_client.disconnect()
        super().closeEvent(event)

class TranslationDict(dict):
    def __missing__(self, key):
        # Повертаємо гарно відформатований ключ у разі відсутності перекладу
        cleaned = key.replace("MAINWINDOW_", "")
        words = cleaned.split("_")
        return " ".join(words).strip().capitalize()

def load_language_from_files(settings_manager):
    """
    Завантажує мовний файл із підкаталогу 'lang' на основі налаштувань.
    Спочатку шукає біля скрипта, потім у теці з конфігурацією.
    """
    lang_code = settings_manager.get_language()
    
    # --- ПОЧАТОК ЗМІН ---
    # Шлях 1: Шукаємо біля основного Python-скрипта (зручно для розробки)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_lang_path = os.path.join(script_dir, 'lang', f"{lang_code}.json")

    # Шлях 2: Шукаємо біля файлу конфігурації (стандартна поведінка)
    config_dir = os.path.dirname(settings_manager.config_path)
    config_lang_path = os.path.join(config_dir, 'lang', f"{lang_code}.json")

    lang_file_path = ""
    # Спочатку перевіряємо, чи є файл локалізації біля скрипта
    if os.path.exists(script_lang_path):
        lang_file_path = script_lang_path
    # Якщо ні, шукаємо в теці з конфігурацією
    elif os.path.exists(config_lang_path):
        lang_file_path = config_lang_path
    # --- КІНЕЦЬ ЗМІН ---

    # Якщо файл для обраної мови не знайдено, перемикаємось на англійську
    if not lang_file_path or not os.path.exists(lang_file_path):
        print(f"Warning: Language file for '{lang_code}' not found. Falling back to English.")
        lang_code = "en"
        # Повторюємо пошук для англійської мови
        script_lang_path_en = os.path.join(script_dir, 'lang', "en.json")
        config_lang_path_en = os.path.join(config_dir, 'lang', "en.json")
        if os.path.exists(script_lang_path_en):
            lang_file_path = script_lang_path_en
        else:
            lang_file_path = config_lang_path_en

    try:
        with open(lang_file_path, 'r', encoding='utf-8') as f:
            return TranslationDict(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"CRITICAL: Could not load language file {lang_file_path}. Error: {e}")
        return TranslationDict()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # --- Language Initialization ---
    # Створюємо один екземпляр менеджера налаштувань
    settings_manager = JsonSettingsManager()
    
    # Завантажуємо мову з JSON-файлів
    lang = load_language_from_files(settings_manager)
    
    DISCORD_STYLE = """
        /* General Window and Widget Styling */
        QMainWindow, QDialog {
            background-color: #36393f;
            color: #dcddde;
        }
        QWidget {
            background-color: #36393f;
            color: #dcddde;
            font-size: 13px;
        }

        /* Menu Bar */
        QMenuBar {
            background-color: #2f3136;
            color: #b9bbbe;
        }
        QMenuBar::item {
            background-color: transparent;
            padding: 4px 10px;
        }
        QMenuBar::item:selected {
            background-color: #40444b;
            color: #ffffff;
        }

        /* Menu Dropdowns */
        QMenu {
            background-color: #2f3136;
            color: #b9bbbe;
            border: 1px solid #202225;
            padding: 5px;
            min-width: 180px;
        }
        QMenu::item {
            padding: 6px 10px 6px 10px;
            border-radius: 3px;
        }
        QMenu::icon {
            margin-left: 5px;
        }
        QMenu::item:selected {
            background-color: #40444b;
            color: #ffffff;
        }
        QMenu::item#deleteAction {
            color: #f04747;
            font-weight: bold;
        }
        QMenu::item#deleteAction:selected {
            background-color: #f04747;
            color: #ffffff;
        }
        QMenu::separator {
            height: 1px;
            background-color: #40444b;
            margin: 5px 0;
        }

        /* Table View */
        QTableView {
            background-color: #2f3136;
            color: #dcddde;
            border: 0px;
            gridline-color: transparent;
            border-radius: 3px 3px 0px 0px;
        }
        QTableView::item {
            outline: 0;
            border: 0;
            padding: 5px;
            border: none;
            background-color: transparent;
        }
        QTableView::item:hover {
            background-color: #393c43;
        }
        QTableView::item:selected {
            outline: 0;
            background-color: #485483;
            color: #ffffff;
        }
        QTableView::item:focus {
            outline: 0;
            border: 0px;
        }
        QTableView QLineEdit {
            padding: 0px;
            border: none;
            border-radius: 0;
        }
        
        /* Table Header */
        QHeaderView::section {
            background-color: #202225;
            color: #b9bbbe;
            padding: 5px;
            border: 0px solid #2f3136;
            font-weight: bold;
        }
        QHeaderView::section:first {
            border-top-left-radius: 3px;
        }
        QHeaderView::section:last {
            border-top-right-radius: 3px;
        }

        /* Server List Widget */
        QListWidget {
            background-color: #2f3136;
            border: none;
            border-radius: 5px;
            padding: 3px;
        }
        QListWidget::item {
            border-radius: 4px;
            padding: 8px 10px;
            margin: 1px 0px;
            background-color: transparent;
        }
        QListWidget::item:hover {
            background-color: #393c43;
        }
        QListWidget::item:selected {
            background-color: #485483;
            color: #ffffff;
        }

        /* Splitter */
        QSplitter::handle {
            background-color: #36393f;
            width: 1px;
        }
        QSplitter::handle:hover {
            background-color: #7289da;
        }
        
        /* Line Edit, Combo Box, Labels */
        QLineEdit, QComboBox, QLabel {
            background-color: #202225;
            color: #dcddde;
            border: 1px solid #202225;
            border-radius: 3px;
            padding: 5px;
        }
        QLineEdit:focus, QComboBox:focus {
            border: 1px solid #7289da;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox::down-arrow {
            image: url(down_arrow.png);
        }
        QComboBox QAbstractItemView {
            background-color: #202225;
            border: 1px solid #40444b;
            selection-background-color: #40444b;
        }
        QLabel {
            background-color: transparent;
            border: none;
            padding: 5px;
        }

        /* Buttons */
        QPushButton {
            background-color: #4f545c;
            color: #ffffff;
            border: none;
            border-radius: 3px;
            padding: 8px 12px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #5d6269;
        }
        QPushButton:pressed {
            background-color: #3e4147;
        }
        QPushButton#PrimaryButton {
            background-color: #7289da;
        }
        QPushButton#PrimaryButton:hover {
            background-color: #677bc4;
        }
        QPushButton#CancelAllButton {
            background-color: #7289da;
            padding: 2px 8px 3px 8px;
            font-size: 12px;
        }
        QPushButton#CancelAllButton:hover {
            background-color: #677bc4;
        }
        QPushButton#CancelButton {
            background-color: #f04747;
            color: white;
            font-weight: bold;
            font-size: 15px;
            padding: 0px;
            border: none;
            border-top-left-radius: 0px;
            border-bottom-left-radius: 0px;
            border-top-right-radius: 2px;
            border-bottom-right-radius: 2px;
            padding-bottom: 3px;
        }
        QPushButton#CancelButton:hover {
            background-color: #d84141;
        }
        QPushButton#CancelButton:disabled {
            background-color: #52575f;
        }

        /* Panel Titles */
        QLabel#PanelTitle {
            color: #b9bbbe;
            font-weight: 700;
            font-size: 12px;
            padding: 5px 0px 5px 0px;
            margin: 0px;
            background-color: transparent;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* Log Browser & Scroll Areas */
        QTextBrowser#LogBrowser {
            background-color: #202225;
            color: #dcddde;
            border-radius: 3px;
            border: none;
        }
        QScrollArea#TransfersScrollArea {
            background-color: #202225;
            border-radius: 4px;
            border: none;
        }
        QWidget#TransfersContainer {
            background-color: transparent;
        }
        QWidget#TransfersContainer > QWidget {
            background-color: #2f3136;
            border-radius: 2px;
        }
        QWidget#TransferDetailsContainer {
            background-color: #292b2f;
            border-radius: 4px;
        }
        
        /* Scroll Bars */
        QScrollBar:vertical {
            background: #2f3136;
            width: 8px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #202225;
            min-height: 20px;
            border-radius: 4px;
        }
        QScrollBar:horizontal {
            background: #2f3136;
            height: 8px;
            margin: 0;
        }
        QScrollBar::handle:horizontal {
            background: #202225;
            min-width: 20px;
            border-radius: 4px;
        }
        
        /* Progress Bar */
        QProgressBar {
            border: 1px solid #40444b;
            border-right: none;
            text-align: center;
            color: #ffffff;
            background-color: #202225;
            font-size: 11px;
        }
        QProgressBar::chunk {
            background-color: #40444b;
        }
        QProgressBar#ProgressBarQueued { color: #8e9297; }
        QProgressBar#ProgressBarQueued::chunk { background-color: #40444b; }
        QProgressBar#ProgressBarSuccess::chunk { background-color: #43b581; }
        QProgressBar#ProgressBarCanceled { color: #ffffff; }
        QProgressBar#ProgressBarCanceled::chunk { background-color: #faa61a; }
        QProgressBar#ProgressBarError { color: #ffffff; }
        QProgressBar#ProgressBarError::chunk { background-color: #f04747; }
        
        /* Status Bar */
        QStatusBar {
            background-color: #202225;
            color: #b9bbbe;
        }

        /* Dialogs, GroupBoxes, Tabs */
        QDialog {
            border: none;
        }
        QMessageBox {
            background-color: #36393f;
        }
        QMessageBox QLabel {
            color: #dcddde;
        }
        QGroupBox {
            border: 1px solid #40444b;
            margin-top: 10px;
            padding: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
        }
        QTabWidget::pane {
            border: none;
        }
        QTabBar::scroller {
            border-bottom: 1px solid #202225;
        }
        QTabBar::tab {
            background-color: transparent;
            color: #8e9297;
            padding: 8px 15px;
            border: none;
        }
        QTabBar::tab:hover:!selected {
            background-color: #2f3136;
            color: #b9bbbe;
            border-radius: 0 0 4px 4px;
            border-bottom: 2px solid #41559a;
        }
        QTabBar::tab:selected {
            background-color: transparent;
            color: #ffffff;
            border-bottom: 2px solid #7289da;
            padding-bottom: 6px;
        }
        
        /* Custom Dialog Styling */
        QLabel#DialogTitle {
            font-size: 16px;
            font-weight: bold;
            color: #ffffff;
            padding-left: 0;
        }
        QLabel#DialogMessage {
            padding-left: 0;
            color: #b9bbbe;
        }
        QWidget#DialogFooter {
            background-color: #2f3136;
            border-bottom-left-radius: 5px;
            border-bottom-right-radius: 5px;
        }

        /* --- [ПОКРАЩЕНО] Стилізація для QCheckBox та StyledCheckBox --- */
        QCheckBox, StyledCheckBox {
            spacing: 10px; /* Відступ між квадратиком та текстом */
            color: #dcddde;
        }
        QDialog QCheckBox, QDialog StyledCheckBox {
            margin-left: 4px;
        }
        
        /* Стиль для самого квадратика (індикатора) */
        QCheckBox::indicator, StyledCheckBox::indicator {
            width: 18px;
            height: 18px;
            
            /* Фон та рамка у звичайному стані */
            background-color: #202225;
            border: 2px solid #4f545c;
            border-radius: 4px;
        }

        /* Ефект при наведенні миші на невибраний чекбокс */
        QCheckBox::indicator:hover:!checked, StyledCheckBox::indicator:hover:!checked {
            border-color: #7289da;
            background-color: #2f3136;
        }

        /* Стиль для вибраного стану з текстовою галочкою */
        QCheckBox::indicator:checked, StyledCheckBox::indicator:checked {
            background-color: #7289da;
            border-color: #7289da;
            color: white;
            font-weight: bold;
            font-size: 12px;
            text-align: center;
        }
        
        /* Псевдо-контент видалено, оскільки використовуємо paintEvent для малювання квадрата */
        
        /* Ефект при наведенні на вже вибраний чекбокс */
        QCheckBox::indicator:checked:hover, StyledCheckBox::indicator:checked:hover {
            background-color: #677bc4;
            border-color: #677bc4;
        }

        /* Стиль для неактивного (disabled) стану */
        QCheckBox::indicator:disabled, StyledCheckBox::indicator:disabled {
            background-color: #2f3136;
            border-color: #40444b;
        }
        
        /* Стиль для неактивного та вибраного стану */
        QCheckBox::indicator:checked:disabled, StyledCheckBox::indicator:checked:disabled {
            background-color: #4f545c;
            border-color: #4f545c;
        }

        /* SpinBox and StyledSpinBox Styling */
        QSpinBox, StyledSpinBox {
            background-color: #202225;
            color: #dcddde;
            border: 1px solid #202225;
            border-radius: 3px;
            padding: 5px;
        }
        QSpinBox:focus, StyledSpinBox:focus {
            border: 1px solid #7289da;
        }

        /* Style for custom buttons inside StyledSpinBox */
        StyledSpinBox QPushButton#upButton, StyledSpinBox QPushButton#downButton {
            background-color: transparent;
            border: none;
            width: 18px;
            height: 14px;
            padding: 0;
        }
        
        StyledSpinBox QPushButton#upButton:hover, StyledSpinBox QPushButton#downButton:hover {
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 2px;
        }
    """

    app.setStyleSheet(DISCORD_STYLE)

    font = QFont()
    if sys.platform == "win32":
        font.setFamily("Segoe UI")
    else:
        font.setFamily("Noto Sans")
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
