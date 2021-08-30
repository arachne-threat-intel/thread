<!-- NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital -->

# THREAD

THREAD is a tool for analysts to map finished reports and articles to MITRE ATT&CK<sup>®</sup>.

THREAD was originally forked from TRAM when it was in its beta phase, and we wanted to build upon it. Therefore, further changes to the original TRAM repo may not be incorporated into THREAD as the codebases have largely diverged. 

## Requirements
- [python3](https://www.python.org/) (3.7+)
- Google Chrome is our only supported/tested browser

## Installation

Please note: if your environment has multiple Python interpreters (e.g. `python` is for Python 2.x and `python3` is for Python 3.x, please adjust some of the commands below accordingly. For example, `pip` may be `python3 -m pip install ...` and `python main.py` may be `python3 main.py`).

Start by cloning this repository.
```
git clone https://github.com/arachne-threat-intel/thread.git
```
From the root of this project, install the PIP requirements.
```
pip install -r requirements.txt
```
Then start the server.
```
python main.py
```
Once the server has started, point your browser to localhost:9999, and you can then enter a URL on the home page.
It currently takes several minutes to analyse a report, so please do not leave the page while it processes.

Configuration defaults can be changed [here](https://github.com/arachne-threat-intel/thread/wiki/THREAD-Configuration)

## Shared vs. Local
We are currently working on making THREAD a live application where you can view your reports and those of others. You can currently use THREAD as a local, single user application. 

## How do I contribute?

We welcome your help in improving THREAD.

Read our [contribution guidelines](CONTRIBUTING.md) for further information. There's also a Developer Certificate of Origin that you'll need to sign off on.

## Notice

Copyright 2021 Arachne Digital

Licensed under the Apache License, Version 2.0.

Please see our [NOTICE](NOTICE.txt) and [LICENSE](LICENSE.txt) files for further information. 
