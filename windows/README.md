# Build AutoClicker.exe (Windows)

Compila el autoclicker para Windows en `dist/AutoClicker.exe`.

## En Windows (local)

```powershell
pip install pyinstaller keyboard
pyinstaller --onefile --windowed --name AutoClicker windows/autoclicker.py
```

O directamente:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-exe.ps1
```

## En GitHub Actions (recomendado)

El workflow `.github/workflows/build-exe.yml` compila el `.exe` en un runner
de Windows de forma automática:

- **Manual:** pestaña *Actions* → *build-exe* → *Run workflow*.
- **Automático al etiquetar:** al subir una etiqueta `v*`, el `.exe` se adjunta
  a la Release correspondiente.

El artefacto `AutoClicker.exe` queda disponible en *Actions* → *build-exe* →
*Artifacts*.