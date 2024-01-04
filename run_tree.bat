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
	git add output_imgs\*
	git add controlnet_img_sketch.png
	git commit -m "Post Generation Commit."
	git push -u origin main
)