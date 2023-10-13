# Daytree
Uses Stable Diffusion to slowly grow a tree, day by day[^1] (and then automatically sets it as a desktop background).

The tree slowly grows over time (using ControlNet), and adapts to the current (real-world) season. More stable generations could be achieved by using a fixed seed (as well as skipping step 2 in the process outlined below). However, this project prioritises creating exciting images instead. All StableDiffusion generation is done through the use of the Automatic1111[^2] API. 


## Today's Tree:
![Today's Tree](https://github.com/Yerren/Daytree/blob/main/output_imgs/desktop_img.bmp?raw=true)
Previous trees can be seen in the output_imgs folder.

## Generation Process Overview:
1) Generate a 512x512 image using img2img and ControlNet, with the previous iteration's image as the input image (or, if it's the first day, a simple placeholder). The ControlNet image is created anew each day to slightly "grow" the tree.
2) Use img2img to upscale to (912x512)*[image_scale]. This step has two functions. The first is to create an image that matches the desktop resolution. The second is to add more variety to the output: when using img2img to non-square resolutions, the result often has unpredictable elements. This can result in strange artifacts and less aesthetically appealing images; however, they are also more exiting and fun (often small travellers will appear, or multiple trees, etc.)
3) Use R-ESRGAN 4x+ to upscale to 2k.
4) Apply a blurring and dimming to the left and right sides of the image (which, from step 2, are usually just vague lines of colour).

_TODO: Add image links to each step of the process once they have been commited_

_TODO: Add animaged gif of story so far_

[^1]: Provided that the workstation isn't fully utilized that day.
[^2]: https://github.com/AUTOMATIC1111/stable-diffusion-webui
