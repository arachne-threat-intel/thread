<!-- NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital -->

# Thread
Thread is a tool for analysts to map finished reports and articles to [MITRE ATT&CK<sup>®</sup>](https://attack.mitre.org).

Thread was originally forked from TRAM when it was in its beta phase, and we wanted to build upon it. Therefore, further changes to the original TRAM repo may not be incorporated into Thread as the codebases have largely diverged. 

* [Requirements](#requirements)
* [Installation](#installation)
* [Submitting a Report](#submitting-a-report)
* [Shared vs. Local](#shared-vs-local)
* [Analysing a Report](#analysing-a-report)
* [Exporting a Report](#exporting-a-report)
* [How do I contribute?](#how-do-i-contribute)
* [Contact Us](#contact-us)
* [Notice](#notice)

## Requirements
- [Python 3](https://www.python.org/) (3.8+)
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

Configuration defaults can be changed [here](https://github.com/arachne-threat-intel/thread/wiki/Thread-Configuration)

You are also welcome to check our test-suite via:
```
python -m unittest discover tests/
```

## Submitting a Report
On Thread's homepage, enter a web page URL (sorry no PDFs yet) to process it and begin a report based on it. It takes a few minutes to analyse a URL, this is dependent on the amount of text found from the URL. You are advised to periodically check if your submission is still in the queue.

If you see an error in the queue, this means the website did not like us trying to fetch its contents, or something on the site could not be parsed. We will periodically check for these errors and work on improvements to the submission process.

When the URL has been processed and its report is ready, a new card will appear (in the **Needs Review** column). Each card will have two buttons:
- **Source**: this links back to original URL where the report originated from
- **Analyse**: this button links to the Thread-analysed report

You will also have the option to delete reports that 1. are not in the queue or 2. those in the queue that have an error.

## Shared vs. Local
We are currently working on making Thread a live application where you can view your reports and those of others. You can currently use Thread as a local, single user application.

When Thread becomes a live application, if you run Thread via our Arachne website, your reports will be visible to others. You can clone this repo, set it up, and use it locally to ensure all your reports stay only on your machine.

## Analysing a Report
Thread's prediction model will try its best to find ATT&CK techniques in the report, but since our current data set is very limited, our models are not 100% accurate, so the tool requires you to review and refine the technique prediction.

When you click on a sentence in the report, you can do the following:
- **Accept** a technique: the correct technique is in the selected sentence. That sentence and technique will be considered a **true positive** (if this is not a missing technique you have introduced).
- **Reject** a technique: the technique is not in the selected sentence. That sentence and technique will be considered a **false positive** (again, if this is not a missing technique you have introduced).
- **Add a Missing Technique**: allows you to manually add any techniques that were missed in the selected sentence. Select the missing technique from the provided searchable-dropdown. You can repeat this for numerous missing techniques. When one is added, this is considered a **false negative** (if this is not a technique you initially rejected).

As more data is fed to the tool and is reviewed, any rebuilt models are expected to become more accurate with these predictions.

If you have made changes you are not happy with and cannot undo easily (e.g. deleted a sentence), you can rollback a report via the homepage (found in the **In Review** column).

## Exporting a Report
Once you have reviewed the entire report, Thread’s results can be exported as a PDF by clicking the **Export PDF** button on the top centre of the page. This will create a PDF containing a raw text version of the report, and a table with the ATT&CK technique and its corresponding sentence. This can be done for all reports out of the queue but those not in the **Completed** column will be considered draft reports.

## How do I contribute?
We welcome your help in improving Thread.

Read our [contribution guidelines](CONTRIBUTING.md) for further information. There's also a Developer Certificate of Origin that you'll need to sign off on.

## Contact Us
You can contact us by emailing us at contact[at]arachne[dot]digital.

If you have found **any security issues** with Thread, we ask that you **please contact us directly** (so we can work on it without it being discovered and exploited). We will be transparent about any security issues in our documentation.

If you have found any other bugs with Thread, please feel free to contact us or raise an issue here in our GitHub repo.

If you have any questions or comments about Thread, please feel free to contact us via the email address above.

## Notice
Copyright 2021 Arachne Digital

Licensed under the Apache License, Version 2.0.

Please see our [NOTICE](NOTICE.txt) and [LICENSE](LICENSE.txt) files for further information. 
