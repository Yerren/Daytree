"""
Checks whether to run the generation script for today. Does not run if the GPU is currently in use (based on if it's memory utilization percentage is greater than
[GPU_MEM_THRESH]. Also does not run if there has already been an image generated today.

Also initialises the datafile if needed. The datafile is in the format:
Previous run's date (str)
Previous run's iteration (int)
Percent of progress when previous season change occurred (float)
Previous season (str).
"""


import os
from datetime import datetime, date
import GPUtil

GPU_MEM_THRESH = 0.3

# Start
current_gpu_mem_util = GPUtil.getGPUs()[0].memoryUtil

if current_gpu_mem_util > GPU_MEM_THRESH:
    print("1")
    exit(1)

date_today = date.today()
date_format = "%y-%m-%d"

# Create and initialise the datafile if it doesn't already exist (i.e., if this is the first time a generation is being
# run).
if not os.path.isfile("datafile.txt"):
    current_month = int(date_today.strftime("%m"))

    # Seasons just based on the current month, not the solstices.
    if current_month == 12 or current_month <= 2:
        season = "summer"
    elif current_month <= 5:
        season = "autumn"
    elif current_month <= 8:
        season = "winter"
    elif current_month <= 11:
        season = "spring"

    current_iteration = -1
    last_season_change = -1
    previous_season = season

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

else:
    with open("datafile.txt", "r") as datafile:
        """
        format of datafile:

        Previous run's date (str)
        Previous run's iteration (int)
        Percent of progress when previous season change occurred (float)
        Previous season (str)
        """

        data = datafile.readlines()

        last_date = datetime.strptime(data[0].strip(), date_format).date()

        if date_today == last_date:
            # Already generated today
            print("1")
            exit(1)

print("0")

