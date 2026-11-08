const { contextBridge, ipcRenderer, webUtils } = require('electron');

const invoke = (channel, ...args) => ipcRenderer.invoke(`ptshot:${channel}`, ...args);
contextBridge.exposeInMainWorld('ptshot', Object.freeze({
  bootstrap: () => invoke('bootstrap'),
  chooseVideos: () => invoke('choose-videos'),
  chooseFolder: () => invoke('choose-folder'),
  importPaths: (paths) => invoke('import-paths', paths),
  pathForFile: (file) => webUtils.getPathForFile(file),
  chooseOutput: () => invoke('choose-output'),
  chooseTool: (name) => invoke('choose-tool', name),
  openSession: () => invoke('open-session'),
  start: (request) => invoke('start', request),
  retry: (settings) => invoke('retry', settings),
  cancel: () => invoke('cancel'),
  inspect: (settings) => invoke('inspect', settings),
  install: (settings) => invoke('install', settings),
  savePreferences: (preferences) => invoke('preferences', preferences),
  copy: (text) => invoke('copy', text),
  openOutput: () => invoke('open-output'),
  openImage: (index) => invoke('open-image', index),
  openProject: () => invoke('open-project'),
  onEvent: (callback) => {
    const listener = (_event, value) => callback(value);
    ipcRenderer.on('ptshot:event', listener);
    return () => ipcRenderer.removeListener('ptshot:event', listener);
  },
}));
