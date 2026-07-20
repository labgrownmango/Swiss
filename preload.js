const { contextBridge, webUtils, ipcRenderer } = require('electron');

// Expose standard file path helper and window control to the web page safely
contextBridge.exposeInMainWorld('electronAPI', {
  getPathForFile: (file) => {
    try {
      return webUtils.getPathForFile(file);
    } catch (e) {
      console.error("Error in getPathForFile preload:", e);
      return "";
    }
  },
  minimize: () => {
    ipcRenderer.send('minimize-window');
  }
});
