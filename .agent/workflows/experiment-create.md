---
description: Creates an experiment (similar to a github commit but local)
---

Create a folder with the following name template "experiment-%experimentnamegivenbyuser%"
Copy everything from root except any cache and dot directories (do not copy the run_gui.sh script either) (use a filter to copy everything thats not run_gui.sh or something prepended with a dot) to the experiment directory
Create a copy of the run_gui.sh script in the root with the name template "run_experiment-%experimentnamegivenbyuser%" and modify its content to run the experiment script instead of the main one (production one) also dont forget to make it use the requirements.txt from the experiment