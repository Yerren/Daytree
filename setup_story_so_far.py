from PIL import Image

# Setup "story so far" gif
total_images = 133

img_list = []
for img_number in range(0, total_images):
    img_list.append(Image.open(f"output_imgs/blur_2k_output_{img_number:03d}.bmp"))

gif = img_list[0]

gif.save(fp="output_imgs/story_so_far.gif", format='GIF', append_images=img_list[1:],
         save_all=True, duration=200, loop=0)
