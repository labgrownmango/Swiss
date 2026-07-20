const { app, BrowserWindow, ipcMain, Tray, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let pythonProcess;
let tray = null;
let isQuitting = false;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false
    },
    autoHideMenuBar: true,
    titleBarStyle: 'default'
  });

  // Clear session cache to force reload HTML changes
  mainWindow.webContents.session.clearCache().then(() => {
    mainWindow.loadFile('index.html');
    mainWindow.webContents.openDevTools();
  });

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
    return false;
  });
}

function createTray() {
  const iconPath = path.join(__dirname, 'icon.png');
  tray = new Tray(iconPath);
  
  const contextMenu = Menu.buildFromTemplate([
    { label: 'Swiss anzeigen', click: () => { if (mainWindow) mainWindow.show(); } },
    { type: 'separator' },
    { label: 'Beenden', click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);
  
  tray.setToolTip('Swiss Tools');
  tray.setContextMenu(contextMenu);
  
  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
    }
  });
}

function resolvePythonPath() {
  const possiblePaths = [];

  const localAppData = process.env.LOCALAPPDATA;
  if (localAppData) {
    const pythonLocalDir = path.join(localAppData, 'Programs', 'Python');
    if (fs.existsSync(pythonLocalDir)) {
      try {
        const dirs = fs.readdirSync(pythonLocalDir);
        dirs.sort((a, b) => {
          if (a.includes('312') || a.includes('3.12')) return -1;
          if (b.includes('312') || b.includes('3.12')) return 1;
          if (a.includes('311') || a.includes('3.11')) return -1;
          if (b.includes('311') || b.includes('3.11')) return 1;
          return b.localeCompare(a);
        });
        for (const dir of dirs) {
          if (dir.toLowerCase().startsWith('python')) {
            const p = path.join(pythonLocalDir, dir, 'python.exe');
            if (fs.existsSync(p)) possiblePaths.push(p);
          }
        }
      } catch (e) {}
    }
  }

  const programFiles = process.env.ProgramFiles;
  if (programFiles) {
    const pfDir = path.join(programFiles, 'Python');
    if (fs.existsSync(pfDir)) {
      try {
        const dirs = fs.readdirSync(pfDir);
        dirs.sort((a, b) => {
          if (a.includes('312') || a.includes('3.12')) return -1;
          if (b.includes('312') || b.includes('3.12')) return 1;
          if (a.includes('311') || a.includes('3.11')) return -1;
          if (b.includes('311') || b.includes('3.11')) return 1;
          return b.localeCompare(a);
        });
        for (const dir of dirs) {
          if (dir.toLowerCase().startsWith('python')) {
            const p = path.join(pfDir, dir, 'python.exe');
            if (fs.existsSync(p)) possiblePaths.push(p);
          }
        }
      } catch (e) {}
    }
  }

  possiblePaths.push('C:\\Python312\\python.exe');
  possiblePaths.push('C:\\Python311\\python.exe');
  possiblePaths.push('C:\\Python314\\python.exe');

  for (const p of possiblePaths) {
    if (p === 'python' || p === 'py') continue;
    if (fs.existsSync(p)) {
      return p;
    }
  }
  return 'python';
}

// Start Python Backend
function startPython() {
  const logDir = app.getPath('userData');
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }
  const logFile = path.join(logDir, 'server.log');
  const out = fs.openSync(logFile, 'a'); // append mode

  if (app.isPackaged) {
    let backendExe = path.join(__dirname, 'backend', 'dist', 'backend.exe');
    backendExe = backendExe.replace('app.asar', 'app.asar.unpacked');
    
    if (!fs.existsSync(backendExe)) {
      backendExe = path.join(__dirname, 'backend', 'backend.exe').replace('app.asar', 'app.asar.unpacked');
    }
    
    fs.appendFileSync(logFile, `Spawning packaged backend: "${backendExe}"\n`);
    pythonProcess = spawn(backendExe, [], {
      stdio: ['ignore', out, out],
      windowsHide: true
    });
  } else {
    const pythonCmd = resolvePythonPath();
    const pythonScript = path.join(__dirname, 'backend', 'app.py');
    fs.appendFileSync(logFile, `Spawning development backend: "${pythonCmd}" "${pythonScript}"\n`);
    pythonProcess = spawn(pythonCmd, [pythonScript], {
      stdio: ['ignore', out, out],
      windowsHide: true,
      env: { ...process.env, PYTHONUNBUFFERED: "1" }
    });
  }

  pythonProcess.on('error', (err) => {
    fs.appendFileSync(logFile, `Failed to spawn Python process: ${err.message}\n`);
  });
}

// IPC listener to minimize the window
ipcMain.on('minimize-window', () => {
  if (mainWindow) {
    mainWindow.minimize();
  }
});

app.whenReady().then(() => {
  startPython();
  createWindow();
  createTray();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  isQuitting = true;
  if (pythonProcess) {
    pythonProcess.kill();
  }
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
