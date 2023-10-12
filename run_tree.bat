call ..\sd_env\Scripts\activate.bat

@SET MY_VAR=
FOR /F %%I IN ('python check_if_should_run.py') DO @SET "MY_VAR=%%I"
@ECHO %MY_VAR%

If %MY_VAR% == 0 (
	Pushd ..\stable-diffusion-webui
	START webui-user-tree.bat
	popd
	call ..\sd_env\Scripts\activate.bat
	python draw_tree.py
	wmic process where "commandline like '%%webui%%'" delete
)