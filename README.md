<!-- NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital -->

# Welcome to the Thread project!
Hello and welcome to Thread, the open-source project that's changing cyber threat intelligence (CTI) mapping! We're thrilled that you've dropped by to learn more about what Thread has to offer and how you can get involved in this exciting community.

Behind Thread is a passionate team of cybersecurity enthusiasts who believe in the power of collaborative, open-source solutions. Our aim is to empower individuals, security professionals, and organisations with streamlined threat intelligence processes, making the digital world a safer place for all.

Whether you're here to explore Thread as a user, potential contributor, or simply out of curiosity, we extend a warm welcome. Your interest and involvement mean a lot to us, and we can't wait to embark on this cybersecurity journey together. So, let's dive in and discover how Thread can revolutionise the way we approach CTI!

## Project Mission & Summary:
Thread is an open-source initiative dedicated to enhancing cyber threat intelligence (CTI) mapping by automating the process of linking cybersecurity reports and articles to MITRE ATT&CK®. Our mission is to empower security professionals, organisations, and analysts by providing efficient, empowering, and community driven CTI capabilities.

* [Thread in simple terms](#thread-in-simple-terms)
* [Why Thread?](#why-thread)
* [Website](#website)
* [Requirements](#requirements)
* [Installation](#installation)
* [Submitting a report](#submitting-a-report)
* [Shared vs. local](#shared-vs-local)
* [Analysing a report](#analysing-a-report)
* [Exporting a report](#exporting-a-report)
* [Project description](#project-description)
* [Required resources](#required-resources)
* [Code of Conduct](#code-of-conduct)
* [How do I contribute?](#how-do-i-contribute)
* [Contact us](#contact-us)
* [Understanding MITRE ATT&CK, TTPs and how to leverage them](#understanding-mitre-attck-ttps-and-how-to-leverage-them)
* [Notice](#notice)

## Thread in simple terms
Thread is a tool for analysts to map finished reports and articles about cyber attacks to [MITRE ATT&CK<sup>®</sup>](https://attack.mitre.org).

Thread was originally forked from TRAM when it was in its beta phase, and we wanted to build upon it. Therefore, further changes to the original TRAM repo may not be incorporated into Thread as the codebases have largely diverged. 

## Why Thread?
Thread isn't just another cybersecurity tool; it redefines how we approach CTI mapping. We've distilled the essence of Thread's unique value proposition into an experience that's efficient, empowering, and community-driven.

Efficiency Unleashed: Bid farewell to tedious, manual processes of mapping reports to MITRE ATT&CK tactics, techniques and procedures (TTPs) that consume hours of your valuable time. Thread's intelligent algorithms work tirelessly to automate the mapping of TTPs. What used to be a painstaking endeavour now takes mere minutes. With Thread, you'll liberate yourself from data wrangling and reclaim your focus for strategic insights.

Empowerment in Your Hands: Thread is all about putting the power of threat intelligence back where it belongs – in your hands. Take control of your security posture by refining and verifying threat data. Our platform ensures that your decisions are based on data that you know is relevant to you. Say goodbye to relying on outdated or inaccurate information; with Thread, you're in control.

Community Collaboration: Thread is being built into an open-source community committed to advancing the field of CTI. By choosing Thread, you become part of a network of cybersecurity experts who share your passion for creating a safer digital world. Together, we forge a path towards a future where CTI is agile, collaborative, and precise.

## Website
If you want to use Thread right now, feel free to use the web version at https://arachne.digital/thread.

## Requirements
- [Python 3](https://www.python.org/) (3.8+)

## Installation
Please note: if your environment has multiple Python interpreters (e.g. `python` is for Python 2.x and `python3` is for Python 3.x, please adjust some of the commands below accordingly. For example, `pip` may be `python3 -m pip install ...` and `python main.py` may be `python3 main.py`).

Start by cloning this repository.
```
git clone https://github.com/arachne-threat-intel/thread.git
```
From the root of this project, install the PIP requirements.**
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

** For package maintenance, you may find the command below useful. Please be warned this has risks such as code-breakages from an upgraded package version where this command upgraded multiple packages at once causing debugging to be difficult.

```
pip install --upgrade -r requirements.txt
```

## Submitting a report
On Thread's homepage, enter a web page URL (sorry no PDFs yet) to process it and begin a report based on it. It takes a few minutes to analyse a URL, this is dependent on the amount of text found from the URL. You are advised to periodically check if your submission is still in the queue.

If you see an error in the queue, this means the website did not like us trying to fetch its contents, or something on the site could not be parsed. We will periodically check for these errors and work on improvements to the submission process.

When the URL has been processed and its report is ready, a new card will appear (in the **Needs Review** column). Each card will have two buttons:
- **Source**: this links back to original URL where the report originated from
- **Analyse**: this button links to the Thread-analysed report

You will also have the option to delete reports that 1. are not in the queue or 2. those in the queue that have an error.

## Shared vs. local
You are able to use Thread via https://arachne.digital/thread.

If you use Thread via our Arachne website, your reports will be visible to others and accessible by the Arachne team. To reduce its visibility, you can flag reports as private on report-submission (please note, these reports will still be accessible by the Arachne team); you will need to sign up for an account on the Arachne website and remain logged-in during report-submission.

Alternatively, you can clone this repo, set it up, and use it locally to ensure all your reports stay only on your machine.

## Analysing a report
Thread's prediction model will try its best to find ATT&CK techniques in the report, but since our current data set is very limited, our models are not 100% accurate, so the tool requires you to review and refine the technique prediction.

When you click on a sentence in the report, you can do the following:
- **Accept** a technique: the correct technique is in the selected sentence. That sentence and technique will be considered a **true positive** (if this is not a missing technique you have introduced).
- **Reject** a technique: the technique is not in the selected sentence. That sentence and technique will be considered a **false positive** (again, if this is not a missing technique you have introduced).
- **Add a Missing Technique**: allows you to manually add any techniques that were missed in the selected sentence. Select the missing technique from the provided searchable-dropdown. You can repeat this for numerous missing techniques. When one is added, this is considered a **false negative** (if this is not a technique you initially rejected).

As more data is fed to the tool and is reviewed, any rebuilt models are expected to become more accurate with these predictions.

If you have made changes you are not happy with and cannot undo easily (e.g. deleted a sentence), you can rollback a report via the homepage (found in the **In Review** column).

## Exporting a report
Once you have reviewed the entire report, Thread’s results can be exported as a PDF by clicking the **Export PDF** button on the top centre of the page. This will create a PDF containing a raw text version of the report, and a table with the ATT&CK technique and its corresponding sentence. This can be done for all reports out of the queue but those not in the **Completed** column will be considered draft reports.

## Project description
Thread is a project that brings together a diverse and passionate community of cybersecurity experts to start to revolutionise the world of CTI. At its core, Thread aims to simplify and expedite the process of CTI mapping, a crucial component of effective cybersecurity. By collaborating with this vibrant community, we're on a mission to empower not only cybersecurity professionals but also organisations and analysts across the globe. Our primary goal is to provide them with the tools they need to swiftly and accurately map TTPs to the MITRE ATT&CK framework.

This initiative doesn't stop at mere efficiency; it's about fundamentally enhancing threat detection and fortifying your security posture. We recognise that time-consuming manual mapping has long been a significant hurdle in the world of cybersecurity. By harnessing the collective expertise of our community, we're determined to tackle this issue head-on. Our commitment to working open is a testament to our belief in the power of collaboration and giving back to the open-source community.

Arachne Digital's ethos revolves around supporting the projects we utilise. We've pledged to contribute in various ways, from sharing a portion of our profits to dedicating developer resources for bug fixes and maintenance. Moreover, when we encounter abandoned projects, we will attempt to step in, fork, and maintain these repositories. Our mission is clear: to ensure the longevity of valuable open-source resources and foster a thriving ecosystem of collaborative cybersecurity research. Thread is more than just a tool; it's a catalyst for change in the world of cybersecurity, and we invite everyone, regardless of their background, to join us on this exciting journey of discovery and innovation. Together, we can strengthen our collective defence against the ever-evolving landscape of cyber threats.

## Required resources
Creating and maintaining Thread, your go-to platform for CTI mapping, requires a diverse set of resources. Some of these resources are provided by Arachne Digital, the for profit company that maintains Thread. However, the collective is strong through diversity, which is why Arachne Digital is opening Thread up to the community. From design and development to community building and infrastructure, here's what powers Thread:

- Design: Craft an intuitive user experience with UI/UX design and establish Thread's unique identity through branding and visual elements.
- Development: Skilled developers, machine learning experts, data managers, cybersecurity specialists, and quality assurance testers bring Thread's software to life, ensuring it's robust and secure. CI/CD pipelines keep everything running smoothly.
- Community Building: Our community thrives with dedicated managers, vigilant moderators, and technical writers who create comprehensive documentation and tutorials for Thread's users and contributors.
- Infrastructure and Hardware: Server infrastructure, data backup, scalability measures, and cloud resources guarantee a seamless experience for Thread's users.
- Additional Resources: Thread also commits to legal compliance, marketing, outreach, community events, maintenance, and support. Plus, we actively contribute to other open-source projects, fostering collaboration across the ecosystem.

## Code of Conduct
The Thread community has adopted the Contributor Covenant. Before contributing, please read the [code of conduct](CODE_OF_CONDUCT.md). By contributing to the Thread community you agree to the code of conduct.

## How do I contribute?
We welcome your help as part of the Thread community!

Read our [contribution guidelines](CONTRIBUTING.md) for further information. 

To get access to our Arachne Digital Slack channel, email contact[at]arachne[dot]digital with a bit about who you are and how you want to get involved.

## Contact us
You can contact us by emailing us at contact[at]arachne[dot]digital.

If you have found **any security issues** with Thread, we ask that you **please contact us directly** (so we can work on it without it being discovered and exploited). We will be transparent about any security issues in our documentation.

If you have found any other bugs with Thread, please feel free to contact us or raise an issue here in our GitHub repo.

If you have any questions or comments about Thread, please feel free to contact us via the email address above.

## Understanding MITRE ATT&CK, TTPs and how to leverage them
We've mentioned MITRE ATT&CK, TTPs and CTI mapping a great deal, but why are these things even relevant to cybersecurity? What does CTI mapping actually yield?

### MITRE ATT&CK®:
[MITRE ATT&CK](https://attack.mitre.org/) (Adversarial Tactics, Techniques, and Common Knowledge) is a comprehensive knowledge base used globally in the cybersecurity community. It provides a structured framework to understand the TTPs employed by cyber threat actors (CTAs).

### Tactics, Techniques, and Procedures (TTPs):
TTPs are the building blocks of threat intelligence. Here's what you need to know about them:

- Tactics: These represent the high-level objectives that threat actors aim to achieve during an attack. Examples include initial access, execution, persistence, and exfiltration.
- Techniques: Techniques are the specific methods or mechanisms used by threat actors to accomplish tactical goals. For instance, a technique under the "Initial Access" tactic might be "Phishing."
- Procedures: Procedures are the detailed steps or sequences of actions that threat actors follow when executing a technique. They offer a granular view of how an attack is carried out.

### The Role of TTPs:
TTPs are like the DNA of cyber threats. By identifying and understanding them, you gain insight into the methods employed by threat actors. This knowledge is invaluable for enhancing your security posture.

- Linking TTPs to security controls: TTPs are not abstract concepts; they have real-world implications for your security infrastructure. MITRE ATT&CK empowers you to link TTPs to specific security controls. These controls are measures, safeguards, or countermeasures designed to mitigate or counteract the associated threats.
- Connecting TTPs to Event IDs in logs: In the world of security operations, event logs are the treasure trove of information. MITRE ATT&CK assists you in linking TTPs to event IDs within these logs. This connection is vital for Security Information and Event Management (SIEM) or Security Orchestration, Automation, and Response (SOAR) solutions. It allows you to create rules and detections based on specific TTPs.
- Harnessing TTPs for targeted protection: Ultimately, MITRE ATT&CK empowers you to tailor your cybersecurity defences to your unique circumstances. If you know which threat groups are targeting your industry in your part of the world, you can align TTPs with the most relevant security controls and event IDs in your logs. This precision enhances your ability to detect and respond to threats effectively.

To give you a primer in these concepts, or if videos are just more your thing, check out [Putting MITRE ATT&CK™ into Action with What You Have, Where You Are](https://www.youtube.com/watch?v=bkfwMADar0M), an amazing presentation by Katie Nickels.

## Notice
Copyright 2021 Arachne Digital

Licensed under the Apache License, Version 2.0.

Please see our [NOTICE](NOTICE.txt) and [LICENSE](LICENSE.txt) files for further information. 
