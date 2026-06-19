# 🐼 SFTPanda

A modern, fast, and feature-rich SFTP client built with Python and PySide6 (Qt). Designed with a sleek, Discord-inspired dark theme, it offers a premium user experience and advanced features for file management and synchronization.

<img width="901" height="622" alt="python_cQt0rhSel0 copy" src="https://github.com/user-attachments/assets/e5dcb01a-d5ad-4731-b61c-305c782b13bd" />


---

## ✨ Key Features

- **🚀 Extreme Transfer Speeds:** Finely tuned Paramiko request and window sizes, enabling transfer speeds optimized up to OpenSSH limits.
- **⚡ Adaptive Multi-Connection Mode:** Dynamically scales concurrent connection threads up to a user-defined ceiling to maximize available bandwidth.
- **🔄 Folder Synchronization:** 
  - Dual-directory comparison with a beautiful visual difference viewer.
  - Supports "Upload", "Download", and "Merge" actions.
  - Customize ignore patterns (e.g., `.git`, `node_modules`, `.env`) directly from settings or right-click context menus.
  - Remembers last used synchronization paths per session.
- **🔒 Secure Credential Storage:** Securely saves passwords and passphrases using the native system keyring (via Python's `keyring` library), avoiding plain-text secrets in configuration files.
- **🎨 Premium Dark Theme UI:** Discord-inspired slate-dark aesthetic featuring:
  - Dynamic breadcrumb navigation bar.
  - Smooth visual transitions and fade animations.
  - Custom styled widgets (tables, check boxes, spin boxes).
  - Fully customizable table column visibility.
- **📈 Advanced Transfer Queue:** A dedicated transfers panel displaying real-time speed, progress bars per file, and pause/cancellation controls.
- **🔒 Flexible Authentication:** Supports standard password authentication as well as private SSH keys (PEM, PPK) with passphrase support.
- **🛠️ Built-in Server Operations:**
  - Search files recursively on the remote server.
  - Change file and folder permissions (Octal/Symbolic) and ownership recursively.
  - Create and extract ZIP archives directly on the server.
- **🌐 Multi-Language Interface:** Dynamic UI localization supporting English and Ukrainian out of the box.

---

## 🔒 Security & Privacy Notice (Public Repository Risks)

If you are hosting this repository publicly on GitHub:
1. **Config Safety:** The local settings file (`sftp_settings.json`) is already added to `.gitignore`. It contains server list profiles.
2. **No Hardcoded Secrets:** Connection passwords and SSH passphrases are **never** stored in config files. They are stored securely in your operating system's Credential Manager via the `keyring` library.
3. **No Private Keys in Repo:** Ensure you never commit your private `.pem` or `.ppk` files to the repository.

---

## 🛠️ Installation & Setup

### Prerequisites
- **Python 3.10+**

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/SFTPanda.git
cd SFTPanda
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```
*(Dependencies include: `PySide6`, `paramiko`, `keyring`, `qtawesome`, `pillow`, `pywin32` on Windows).*

### 3. Run the application
```bash
python Python.py
```

---

## 📦 Building Standalone Executable

You can compile **SFTPanda** into a single standalone executable using PyInstaller.

On Windows, simply run the automated build script:
```cmd
buildPyInstaller.bat
```
This script will:
1. Create a clean virtual environment.
2. Install necessary requirements.
3. Compile all resources (including icons and translations).
4. Output the ready-to-run package in `SFTPanda_PyInstaller/`.

---

## 🛠️ Technologies Used

- **GUI Framework:** [PySide6](https://doc.qt.io/qtforpython-6/) (Official Qt for Python)
- **SFTP Client:** [Paramiko](https://www.paramiko.org/)
- **Secure Keyring:** [Keyring](https://github.com/jaraco/keyring)
- **Icons:** [QtAwesome](https://github.com/spyder-ide/qtawesome) (FontAwesome Integration)

---

## 🎸 Vibe-Coding Disclaimer

This project is **100% vibe-coded** (built collaboratively by a single human developer and an AI assistant). While it has been optimized and tested, it is provided "as is" under the MIT License. Use it at your own discretion, and enjoy the vibe!

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
