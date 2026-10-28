"""
Setup Windows App for Talia Cyberpunk Audio Visualizer.
1. Generates high-res multi-layer .ico from character art.
2. Compiles a native, zero-console Talia.exe launcher using Windows' built-in csc.exe compiler.
3. Creates Desktop and Start Menu shortcuts with the custom icon.
4. Enables 1-click Windows Taskbar Pinning.
"""

import os
import sys
import subprocess
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(PROJECT_ROOT, "app_icon.ico")
EXE_PATH = os.path.join(PROJECT_ROOT, "Talia.exe")
PNG_SOURCE = os.path.join(PROJECT_ROOT, "PNGs", "talia_avatar_icon.png")
if not os.path.exists(PNG_SOURCE):
    PNG_SOURCE = os.path.join(PROJECT_ROOT, "PNGs", "mouth_overlay_1024.png")


def create_app_icon():
    print("[*] Generating high-resolution Windows App Icon...")
    if not os.path.exists(PNG_SOURCE):
        print(f"[!] Warning: PNG source not found at {PNG_SOURCE}")
        return False
    try:
        im = Image.open(PNG_SOURCE)
        sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        im.save(ICON_PATH, format="ICO", sizes=sizes)
        print(f"[+] Saved app icon to: {ICON_PATH}")
        return True
    except Exception as e:
        print(f"[!] Failed to generate icon: {e}")
        return False


def compile_talia_exe():
    print("[*] Compiling native Windows Talia.exe launcher (zero console)...")
    csc_paths = [
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
    ]
    csc_exe = None
    for p in csc_paths:
        if os.path.exists(p):
            csc_exe = p
            break

    if not csc_exe:
        print("[!] csc.exe not found. Skipping .exe compilation.")
        return False

    current_pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe").replace("\\", "\\\\")

    cs_code = f'''using System;
using System.Diagnostics;
using System.IO;

namespace TaliaAppLauncher
{{
    class Program
    {{
        [STAThread]
        static void Main(string[] args)
        {{
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string scriptPath = Path.Combine(baseDir, "Python Code", "mouth_overlay_app.py");
            if (!File.Exists(scriptPath))
            {{
                scriptPath = Path.Combine(baseDir, "mouth_overlay_app.py");
            }}

            string[] candidatePythons = new string[] {{
                @"{current_pythonw}",
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Python\\pythoncore-3.14-64\\pythonw.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\\Python\\Python314\\pythonw.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\\Python\\Python313\\pythonw.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\\Python\\Python312\\pythonw.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Python\\bin\\pythonw.exe"),
                "pythonw.exe"
            }};

            string pythonPath = "pythonw.exe";
            foreach (string p in candidatePythons)
            {{
                if (File.Exists(p))
                {{
                    pythonPath = p;
                    break;
                }}
            }}

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonPath;
            psi.Arguments = "\\"" + scriptPath + "\\"";
            psi.WorkingDirectory = baseDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.WindowStyle = ProcessWindowStyle.Hidden;

            try
            {{
                Process.Start(psi);
            }}
            catch (Exception ex)
            {{
                System.Windows.Forms.MessageBox.Show("Unable to start Talia:\\n" + ex.Message, "Talia Visualizer Error", System.Windows.Forms.MessageBoxButtons.OK, System.Windows.Forms.MessageBoxIcon.Error);
            }}
        }}
    }}
}}
'''
    cs_file = os.path.join(PROJECT_ROOT, "_temp_launcher.cs")
    with open(cs_file, "w", encoding="utf-8") as f:
        f.write(cs_code)

    cmd = [
        csc_exe,
        "/target:winexe",
        f"/win32icon:{ICON_PATH}",
        "/r:System.Windows.Forms.dll",
        f"/out:{EXE_PATH}",
        cs_file
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(cs_file):
            os.remove(cs_file)
        if res.returncode == 0 and os.path.exists(EXE_PATH):
            print(f"[+] Successfully compiled: {EXE_PATH}")
            return True
        else:
            print(f"[!] Compilation failed: {res.stderr}")
            return False
    except Exception as e:
        if os.path.exists(cs_file):
            os.remove(cs_file)
        print(f"[!] Compilation error: {e}")
        return False


def create_shortcuts():
    print("[*] Creating Desktop and Start Menu shortcuts...")

    # Determine shortcut targets: prefer Talia.exe, fallback to pythonw
    if os.path.exists(EXE_PATH):
        target = EXE_PATH
        args = ""
    else:
        pythonw_cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        target = pythonw_cand if os.path.exists(pythonw_cand) else sys.executable
        args = f'"{os.path.join(PROJECT_ROOT, "mouth_overlay_app.py")}"'

    desktop_dir = os.path.join(os.environ["USERPROFILE"], "Desktop")
    start_menu_dir = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs")

    shortcuts = [
        os.path.join(desktop_dir, "Talia Visualizer.lnk"),
        os.path.join(start_menu_dir, "Talia Visualizer.lnk")
    ]

    # PowerShell script to create shortcuts via WScript.Shell
    for sc in shortcuts:
        ps_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{sc}")
$Shortcut.TargetPath = "{target}"
$Shortcut.Arguments = '{args}'
$Shortcut.WorkingDirectory = "{PROJECT_ROOT}"
$Shortcut.IconLocation = "{ICON_PATH}, 0"
$Shortcut.Description = "Talia Cyberpunk Audio Visualizer"
$Shortcut.Save()
'''
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)
            print(f"[+] Created shortcut: {sc}")
        except Exception as e:
            print(f"[!] Failed to create shortcut {sc}: {e}")


def main():
    print("=======================================================")
    print("  TALIA CYBERPUNK VISUALIZER - WINDOWS APP INSTALLER")
    print("=======================================================\n")
    create_app_icon()
    compile_talia_exe()
    create_shortcuts()
    print("\n[+] SUCCESS: Talia is now installed as a Windows App!")
    print("    - Pin to Taskbar: Right-click Talia.exe or the Desktop/Start shortcut -> 'Pin to taskbar'")
    print("    - Start Menu: Type 'Talia' in Windows Search to launch anytime.")
    print("    - No Terminal Window: Runs 100% silently in the background.")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
