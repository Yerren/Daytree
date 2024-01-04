"""
Makes the calls to the auto1111 webui to actually generate the image. The generation process is as follows:
1) Generate a 512x512 image using img2img and ControlNet, with the previous iteration's image as the input image (or, if
    it's the first day, a simple placeholder). The ControlNet image is created anew each day to slightly "grow" the
    tree.
2) Use img2img to upscale to (912x512)*[image_scale]. This step has two functions. The first is to create an image that
    matches the desktop resolution. The second is to add more variety to the output: when using img2img to non-square
    resolutions, the result often has unpredictable elements. This can result in strange artifacts and less
    aesthetically appealing images; however, they are also more exiting and fun (often small travellers will appear, or
    multiple trees, etc.)
3) Use R-ESRGAN 4x+ to upscale to 2k.
4) Apply a blurring and dimming to the left and right sides of the image (which, from step 2, are usually just vague
    lines of colour).

The webui needs to be open at http://127.0.0.1:7860. (This is handled by the batch script).

"""

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import requests
import io
import base64
import os
import numpy as np
from datetime import date
from time import sleep
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Parameters

image_scale = 2  # image_scale = 1 is a (912x512) image.

# Position of the bottom of the tree (as a proportion of the image height)
tree_bottom_prop = 0.68

# Starting and final position of the top of the tree trunk (as proportions of the image height)
tree_top_prop_min = 0.60
tree_top_prop_max = 0.28

# Starting and final scale factors for the tree leave image.
leaves_size_prop_min = 1 / 5
leaves_size_prop_max = 1.8

# Starting and final widths of the tree trunk (in pixels).
tree_width_min = 4
tree_width_max = 30

# How many iterations to run for.
total_iters = 365

# Fixed sections of the prompt that are shared across seasons.
prompt_middle = "something surprising, a detailed foreground and background"
prompt_suffix = "8k, photo realistic, beautiful oil painting by greg rutkowski, thomas kinkade"


def final_image_processing(img_name, img_path):
    """
    Blurs and dims the edges of an input image. Loads the input image from [img_path]/[img_name].png.
    Saves the resulting image to [img_path]/blur_[img_name].bmp and [img_path]/desktop_img.bmp.

    :param img_name: Filename (without extension) of the png image to process.
    :type img_name: str
    :param img_path: Path to the directory where the images and loaded from and saved to.
    :type img_path: str
    """
    with Image.open(f"{img_path}/{img_name}.png") as pre_blur_img:
        width, height = pre_blur_img.size
        sidebar_size = (width - height) // 2

        mask = np.zeros((pre_blur_img.size[1], pre_blur_img.size[0]), dtype="uint8")

        for col in range(sidebar_size):
            mask[:, :sidebar_size-col] = 255
            mask[:, col-sidebar_size:] = 255

        mask_img = Image.fromarray(mask)
        mask_img.save(f"test_mask.png", "PNG")

        blur_img = pre_blur_img.filter(ImageFilter.GaussianBlur(5))

        enhancer = ImageEnhance.Brightness(blur_img)
        blur_img = enhancer.enhance(0.75)

        pre_blur_img.paste(blur_img, mask=mask_img)
        pre_blur_img.save(f"{img_path}/blur_{img_name}.bmp", "BMP")
        pre_blur_img.save(f"{img_path}/desktop_img.bmp", "BMP")
        pre_blur_img.save(f"{img_path}/output_latest.bmp", "BMP")

        # Save "story so far" gif
        if not os.path.isfile("output_imgs/story_so_far.gif"):
            # First time: just save a single image
            pre_blur_img.save(fp="output_imgs/story_so_far.gif", format='GIF', save_all=True, duration=200, loop=0)
        else:
            # Add to existing gif
            gif = Image.open("output_imgs/story_so_far.gif")
            gif.save(fp="output_imgs/story_so_far.gif", format='GIF', append_images=[pre_blur_img],
                     save_all=True, duration=200, loop=0)


def draw_tree(bg_img_name, fg_img_name, trunk_fill):
    """
    Creates a basic input image that can be given passed to the generative model. Constructs this by taking the
    background image, and pasting the tree "top" and "trunk" on top of this.

    :param bg_img_name: The filename of the background image (i.e., the ground) that to be used as the base for every
        generation.
    :type bg_img_name: str
    :param fg_img_name: The filename of the top of the tree. The size of this is increase each generation, and its
        location adjusted.
    :type fg_img_name: str
    :param trunk_fill: An (R, G, B) tuple indicating the colour to draw the tree "trunk" in.
    :type trunk_fill: tuple
    :return: A tuple containing the constructed image (as a PIL Image), and that image converted to base64.
    :rtype: tuple
    """
    with Image.open(bg_img_name) as background_img:
        with Image.open(fg_img_name) as colour_head_img:

            tree_center_x = int(background_img.size[0] // 2)
            tree_top_y = int(background_img.size[1] * tree_top_prop)

            colour_head_img = colour_head_img.resize((int(colour_head_img.size[0] * leaves_size_prop),
                                                      int(colour_head_img.size[1] * leaves_size_prop)))

            leaves_top_x = tree_center_x - colour_head_img.size[0]//2
            leaves_top_y = tree_top_y - colour_head_img.size[1]//2

            background_img.paste(colour_head_img, (leaves_top_x, leaves_top_y), colour_head_img)

            draw = ImageDraw.Draw(background_img)
            draw.line([(tree_center_x, int(background_img.size[1] * tree_bottom_prop)), (tree_center_x, tree_top_y)],
                      fill=trunk_fill,
                      width=tree_width)

            return background_img, pil_to_base64_v2(background_img)


def pil_to_base64_v2(pil_image):
    """
    Converts a PIL image to base64.

    :param pil_image: The image to convert to base64.
    :type pil_image: Image.Image
    :return: A base64 image encoding of the given PIL Image.
    :rtype: str
    """
    with io.BytesIO() as stream:
        pil_image.save(stream, "PNG", pnginfo=None)
        base64_str = base64.b64encode(stream.getvalue()).decode("utf-8")
        return base64_str


def parameter_schedule(progress_proportion, proportion_of_last_season_change):
    """
    Returns the dynamic parameters (i.e., the parameters that change each generation) passed to the generative model:
    the denoising strength, the guidance value, and the ControlNet weight.
    
    The schedule for these have been set through trial and error. They factor in the overall progress, as well as how 
    long it has been since the last change of season (to ensure that there is a smooth shift between seasons).

    :param progress_proportion: How far through the total process (as a proportion between 0.0 and 1.0) this iteration 
        is.
    :type progress_proportion: float
    :param proportion_of_last_season_change: The value of progress_proportion at the time of the most recent change of
        season.
    :type proportion_of_last_season_change: float
    :return: A tuple containing: (denoising strength, guidance value, ControlNet weight).
    :rtype: tuple
    """
    denoising_strength_max = 0.98
    denoising_strength_min = 0.70
    denoising_strength_after_season = 0.5

    guidance_max = 1
    guidance_min = 0.9

    controlnet_weight_max = 2
    controlnet_weight_min = 0.7

    progress_min_point = 0.1  # Progress percentage at which values will reach minimum
    post_season_low_strength_duration = 0.1  # How long (as a percentage) to stay at minimum denoising after a season change

    initial_progress_proportion = min(progress_proportion / progress_min_point, 1)

    past_season_progress = (progress_proportion - proportion_of_last_season_change) / post_season_low_strength_duration

    if past_season_progress <= 1:
        denoising_strength_out = (1 - past_season_progress) * denoising_strength_after_season + \
                                 past_season_progress * denoising_strength_min
    else:
        denoising_strength_out = (1 - initial_progress_proportion) * denoising_strength_max + \
                                 initial_progress_proportion * denoising_strength_min

    guidance_out = (1 - initial_progress_proportion) * guidance_max + initial_progress_proportion * guidance_min
    controlnet_weight_out = (1 - initial_progress_proportion) * controlnet_weight_max + \
                            initial_progress_proportion * controlnet_weight_min

    return denoising_strength_out, guidance_out, controlnet_weight_out


# Start
date_today = date.today()
date_format = "%y-%m-%d"

current_month = int(date_today.strftime("%m"))

if current_month == 12 or current_month <= 2:
    season = "summer"
elif current_month <= 5:
    season = "autumn"
elif current_month <= 8:
    season = "winter"
elif current_month <= 11:
    season = "spring"

with open("datafile.txt", "r") as datafile:
    """
    format of datafile:
    
    Previous run's date (str)
    Previous run's iteration (int)
    Percent of progress when previous season change occurred (float)
    Previous season (str)
    """

    data = datafile.readlines()

    previous_iteration = int(data[1].strip().strip())

    last_season_change = float(data[2].strip().strip())
    previous_season = data[3].strip().strip()

    current_iteration = previous_iteration + 1

    if current_iteration >= total_iters:
        print(f"Generated all {total_iters} iterations!")
        exit()


auto1111_subprocess = None
url = "http://127.0.0.1:7860"

try:
    while True:
        try:
            # Get Url
            get = requests.get(url)
            # if the request succeeds
            if get.status_code == 200:
                break
        except requests.exceptions.RequestException as e:
            pass
        sleep(1)

    im_number = current_iteration

    interp_percent = (im_number+1)/total_iters

    tree_top_prop = (1 - interp_percent) * tree_top_prop_min + interp_percent * tree_top_prop_max
    leaves_size_prop = (1 - interp_percent) * leaves_size_prop_min + interp_percent * leaves_size_prop_max
    tree_width = int((1 - interp_percent) * tree_width_min + interp_percent * tree_width_max)

    if interp_percent < 1/3:
        tree_age_modifier = "very young, small "
    elif interp_percent < 2/3:
        tree_age_modifier = ""
    else:
        tree_age_modifier = "old "

    if season != previous_season:
        print("season change")
        previous_season = season
        last_season_change = im_number/total_iters

    denoising_strength, controlnet_guidance, controlnet_weight = parameter_schedule(im_number/total_iters, last_season_change)
    print(f"Denoising strength: {denoising_strength}, controlnet guidance: {controlnet_guidance}, controlnet weight: {controlnet_weight}")

    if season == "summer":
        prompt = f"A single {tree_age_modifier}tree in summer, full of green leaves, in a green field with {prompt_middle}, beautiful sunny day, {prompt_suffix}",
    elif season == "autumn":
        prompt = f"A single {tree_age_modifier}tree in autumn, with mottled autumn colored leaves, in a field with leaves on it and {prompt_middle} beautiful autumn day, {prompt_suffix}",
    elif season == "winter":
        prompt = f"A single {tree_age_modifier}bare tree in winter, in a field, and {prompt_middle}, beautiful cold winter day, {prompt_suffix}",
    elif season == "spring":
        prompt = f"A single {tree_age_modifier}budding tree in spring, with pink buds and sparse leaves, in a field with spring flowers,and {prompt_middle}, beautiful spring day, {prompt_suffix}",


    controlnet_img_sketch, encoded_controlnet_img_sketch = draw_tree("SketchBG.png", "Tree_Head.png", (255, 255, 255))
    controlnet_img_sketch.save(f"controlnet_img_sketch.png", "PNG")

    if im_number == 0:
        controlnet_img, encoded_controlnet_img = draw_tree("GenericBG.png", "Tree_Head_Colour.png", (96, 56, 19))
        controlnet_img.save(f"controlnet_img.png", "PNG")
        encoded_prev_img = encoded_controlnet_img
    else:
        with Image.open(f"output_imgs/output_{im_number-1:03d}.png") as im:
            encoded_prev_img = pil_to_base64_v2(im)

    payload = {
        "init_images": [
            encoded_prev_img
        ],
        "controlnet_input_image": [
            encoded_controlnet_img_sketch
        ],
        "negative_prompt": "jpeg artifacts, cropped, worst quality, low quality, lowres, bad anatomy, longbody, signature",
        "denoising_strength": denoising_strength,
        "prompt": str(prompt),
        "sampler_index": "Euler a",
        "steps": 50,
        "controlnet_module": "none",
        "controlnet_model": "control_sd15_scribble [fef5e48e]",
        "width": 512,
        "height": 512,
        "controlnet_guidance": controlnet_guidance,
        "controlnet_weight": controlnet_weight
    }
    print("Generating small square image...")
    response = requests.post(url=f'{url}/controlnet/img2img', json=payload)
    r = response.json()
    img_out = r['images'][0]
    image = Image.open(io.BytesIO(base64.b64decode(img_out.split(",",1)[0])))
    image.save(f'output_imgs/output_{im_number:03d}.png')

    # img2img "upscale"
    payload_upscale = {
        "init_images": [
            img_out
        ],
        "controlnet_input_image": [
            encoded_controlnet_img_sketch
        ],
        "negative_prompt": "jpeg artifacts, cropped, worst quality, low quality, lowres, bad anatomy, longbody, signature",
        "denoising_strength": 0.5,
        "prompt": str(prompt),
        "sampler_name": "DPM2 a",
        "steps": 100,
        "width": 912*image_scale,
        "height": 512*image_scale,
        "resize_mode": 2,
    }

    print("Generating small rectangular image...")
    response = requests.post(url=f'{url}/sdapi/v1/img2img', json=payload_upscale)
    r = response.json()
    img_out = r['images'][0]
    image = Image.open(io.BytesIO(base64.b64decode(img_out.split(",",1)[0])))
    image.save(f'output_imgs/lrg_output_{im_number:03d}.png')

    # actual upscale
    payload_resize = {
        "resize_mode": 0,
        "gfpgan_visibility": 0,
        "codeformer_visibility": 0,
        "codeformer_weight": 0,
        "upscaling_resize": 2,
        "upscaler_1": "R-ESRGAN 4x+",
        "image": img_out
    }

    print("Upscaling to 2k...")
    response = requests.post(url=f'{url}/sdapi/v1/extra-single-image', json=payload_resize)
    r = response.json()
    img_out = r['image']
    image = Image.open(io.BytesIO(base64.b64decode(img_out.split(",", 1)[0])))
    image.save(f'output_imgs/2k_output_{im_number:03d}.png')

    print("Final image post-processing...")
    final_image_processing(f"2k_output_{im_number:03d}", "output_imgs")

    with open("datafile.txt", "w") as datafile:
        """
        format of datafile:
    
        Previous run's date (str)
        Previous run's iteration (int)
        Percent of progress when previous season change occurred (float)
        Previous season (str)
        """

        output_lines = []
        output_lines.append(date_today.strftime(date_format) + "\n")
        output_lines.append(str(current_iteration) + "\n")
        output_lines.append(str(last_season_change) + "\n")
        output_lines.append(str(previous_season) + "\n")

        data = datafile.writelines(output_lines)

    print("Done.")
except Exception as e:
    print(e)
