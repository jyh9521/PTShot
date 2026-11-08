import '@kyralabs/m3e-tokens/fonts-rond.css';
import '@kyralabs/m3e-tokens/tokens.css';
import '@kyralabs/m3e-tokens/theme.css';
import '@kyralabs/m3e-css/index.css';
import '@kyralabs/m3e-tokens/material-symbols.css';
import { createTheme } from '@kyralabs/m3e-tokens/theme';
import { createRoot } from 'react-dom/client';
import App from './App';
import './style.css';

const theme = createTheme({ seed: '#7452bd', variant: 'tonalSpot', mode: 'system', motionScheme: 'expressive' });
const sheet = new CSSStyleSheet();
sheet.replaceSync(theme.cssText);
document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
createRoot(document.getElementById('root')!).render(<App />);
