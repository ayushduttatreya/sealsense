# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

You can also install [eslint-plugin-react-x](https://npmx.dev/package/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://npmx.dev/package/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

## SealSense IoT & Machine Learning Architecture

SealSense is an IoT environmental and bioacoustic monitoring platform for grain storage silos.

### Backend & Model Adapters
The backend is powered by FastAPI, SQLite with WAL mode, and modular model adapters:
- **Rule-Based Engine (`backend/app/alert_rules.py`)**: Authoritative, deterministic environmental alerts (<1ms latency) for CO₂, temperature, and air relative humidity (Air RH != grain moisture).
- **Nocturne Mini Adapter (`backend/app/adapters/nocturne.py`)**: Isolated bioacoustic adapter for `stratus-labs/nocturne-v1-mini` (9.4M EfficientNet-B1 student model). Preprocesses 10-second mono 16 kHz audio. Lazy-loaded to ensure FastAPI starts with zero ML dependencies.
- **Zeus Adapter (`backend/app/adapters/zeus.py`)**: Isolated adapter for `GestaltCog/zeus` (102M time-series foundation model). Assesses hardware requirements (CUDA + FlashAttention-2) and maintains rule-based fallback on edge/CPU hardware.

### Testing & Verification
```bash
# Run model adapter compatibility tests
backend/.venv/bin/python3 backend/model_adapter_test.py

# Run comprehensive unit test suite
backend/.venv/bin/python3 -m unittest backend/tests/test_model_adapters.py
backend/.venv/bin/python3 backend/tests/test_rea_features.py

# Build frontend
npm run build
```
# sealsense
