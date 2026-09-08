一些命令

```bash

conda deactivate
conda env remove -n ocr_cpu
conda create -n ocr_cpu python=3.10 -y


pip install "tencentcloud-sdk-python-common[async]" tencentcloud-sdk-python-ocr


nuitka --standalone --msvc=latest --show-memory --show-progress --plugin-enable=tk-inter --windows-console-mode=disable main_win.py


signtool sign /fd sha256 /f "D:\tools\cert\t100.pfx" /tr http://timestamp.digicert.com /td sha256 /v "D:\source\pythonpath\ocr-wx\main_win.dist\main_win.exe"

```
