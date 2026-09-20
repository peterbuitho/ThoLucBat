@echo off
rem Start the poem page on Windows against LM Studio's local server (home use only).
rem Before the first run:
rem   1) In LM Studio load a VietPoet GGUF and start the local server (Developer tab, port 1234).
rem   2) In this folder:  py -m venv .venv-win   then   .venv-win\Scripts\pip install -r requirements.txt
cd /d "%~dp0.."
if "%VIETPOET_BASE_URL%"=="" set VIETPOET_BASE_URL=http://localhost:1234/v1
if "%VIETPOET_MODEL%"=="" set /p VIETPOET_MODEL=Model identifier shown in LM Studio: 
set GRADIO_ANALYTICS_ENABLED=False
echo Starting the page on http://127.0.0.1:7860  (Ctrl+C to stop)
".venv-win\Scripts\python" -m app.webui
pause
