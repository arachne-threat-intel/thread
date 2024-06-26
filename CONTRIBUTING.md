<!-- NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital -->

# Contribute to Arachne Digital Projects

Thank you for wanting to contribute to one (or more!) of the Arachne Digital projects! 

* [Project Mission and Summary](#project-mission-and-summary)
* [Code of Conduct](#code-of-conduct)
* [Resources](#resources)
* [Communication Channels](#communication-channels)
* [Types of Contributions](#types-of-contributions)
* [Coding Standards](#coding-standards)
* [Issue Tracking](#issue-tracking)
* [Bug Handling Process](#bug-handling-process)
* [Feature Request Process](#feature-request-process)
* [Code Contribution Workflow](#code-contribution-workflow)
* [Licence](#licence)
* [Recognition and Attribution](#recognition-and-attribution)
* [Contact Information](#contact-information)
* [Developer's Certificate of Origin v1.1](#developers-certificate-of-origin-v11)

## Project Mission and Summary

Arachne Digital is committed to revolutionising the world of cybersecurity through our innovative open-source projects. Our mission is to empower cybersecurity professionals, organisations, and analysts globally by providing them with tools that streamline threat intelligence processes, lead to enhanced threat detection, and fortify security postures. We believe in the power of collaboration, community-driven development, and giving back to the open-source community.

## Code of Conduct

The Arachne Digital community has adopted the Contributor Covenant. Before contributing, please read the [CODE OF CONDUCT](CODE_OF_CONDUCT.md). By contributing to the Arachne Digital community, you agree to the code of conduct.

## Resources

Please see the READMEs for high level information about the various Arachne Digital projects, and the [ROADMAP](ROADMAP.md) to get an understanding of where the project is going.

* [Thread README](https://github.com/arachne-threat-intel/thread/blob/main/README.md)
* [Tracery README](https://github.com/arachne-threat-intel/tracery/blob/main/README.rst)
* [Spindle README](https://github.com/arachne-threat-intel/spindle/blob/main/README.md)

## Communication Channels

Arachne Digital uses Slack to discuss everything to do with our open source projects. To get access, please email contact[at]arachne[dot]digital with a bit about who you are and how you would like to contribute.

## Types of Contributions

Arachne Digital welcomes contributions from individuals with diverse skills and backgrounds. You can contribute to Arachne Digital projects in various ways, depending on your interests. Below is a non-exhaustive list of some of the different types of contributions you can make:

**Technical Contributions**

* Code Contributions: If you want to code, you can contribute to the development of Arachne Digital by submitting pull requests to software to add new features, fix bugs, or enhance existing functionalities.
* Documentation: Help improve our documentation by fixing typos, clarifying instructions, or adding new content to make it more accessible and informative.
* Testing: Assist in testing our software by running test cases, identifying issues, and providing feedback to ensure the software's reliability.
* UI/UX Design: If you are a UI/UX designer, you can contribute by enhancing the user interface and user experience of our software.
* Review: Review code changes submitted by other contributors, provide constructive feedback, and help maintain code quality.
* Config Changes: Propose and implement changes to configuration settings that can enhance our software's performance and usability.
* Dependencies: Contribute by updating and managing the project's dependencies to keep it up-to-date and secure.

**Community Contributions**

* Community Building: Engage with our community on platforms like Slack, participate in discussions, and help newcomers navigate our projects.
* Event Organisation: Organise or participate in events related to Arachne Digital, such as webinars, workshops, or meetups, to foster collaboration and knowledge sharing.
* Content Creation: Contribute to our blog, write articles, or create tutorials that can benefit the community.
* Bug Reporting: If you encounter issues while using our software, report them on our GitHub repository with detailed information to help us improve.
* Feature Requests: Share your ideas for new features or enhancements on the GitHub repository for the specific software by opening feature request issues.
* Community Support: Provide support to fellow community members by answering questions, offering guidance, and sharing your expertise.

Remember that every contribution, regardless of its size or nature, is valuable to us and helps strengthen the Arachne Digital community. We appreciate your willingness to contribute in any way you would like!

## Coding Standards

- Please fork to create Pull Requests (PRs) to contribute to the codebase of our various projects. See [Code Contribution Workflow](#code-contribution-workflow) for more details.
- For Python code, we aim to follow recommended guides (https://peps.python.org/pep-0008/). Your IDE may already enforce these for you.
- If complex code is required, please comment.
- When making a commit, please begin your commit message with - if applicable - the tagged Issue number of what you are working on, `#<Issue number>: Added a unicorn to the homepage`.
- Small & few unrelated changes are fine; numerous or larger ones should be a separate branch and/or Issue, e.g.
   - whilst working on branch x, I spotted a typo in an unrelated file > commit in branch x.
      - If I spot a PR where the file or lines-changed includes the small typo, I will consider flagging this in the PR so the PR-owner can do the typo-fix themselves (reducing potential merge conflicts).
   - whilst working on branch y, I spotted numerous typos in an unrelated file > I'll leave branch y as is and consider raising an Issue for this typo or - if I am ok with branch maintenance - create a new branch to fix this.
- If you are introducing a new concept - e.g. a new field on a report - please consider updating tests and/or adding a new test case.
   - Regarding Thread, our test-suite currently only covers back-end functionality.

## Issue Tracking

We use GitHub issue tags to categorise our issues and pull requests. Please use these tags when creating or working on issues to help streamline the work that goes into building our software and the community.

Below are the tags we use:

* bug: If something isn't working as expected or there's a malfunction, tag the issue as a bug. Be sure to provide detailed information about the problem.
* community: These tags are used for community building efforts, such as organising events, discussions, or initiatives aimed at fostering our community.
* config change: Use this tag for requests to change configuration settings. Clearly describe the requested changes in the issue.
* dependencies: Tag for pull requests that update a dependency file, such as libraries or external resources. Provide information on the dependency and the reason for the update.
* documentation: Issues related to improvements or additions to documentation. Use this tag for discussions and tasks related to enhancing our documentation.
* duplicate: If you find that an issue or pull request already exists for the same problem or request, tag it as a duplicate.
* enhancement: Tag for issues related to performance improvements, code refactoring, or enhancing usability without introducing new features.
* feature request: Tag for new feature requests to our software or services. Please provide clear details about the proposed feature.
* good first issue: This tag identifies issues suitable for newcomers to the project. If you are new to our community, consider starting with these issues to get acquainted with contributing.
* help wanted: Tag for issues that require extra attention or assistance from the community. If you are looking for a way to contribute, check out these issues.
* invalid: If an issue doesn't seem valid or relevant, tag it as invalid. Provide a brief explanation of why the issue is considered invalid.
* question: If you have questions or need further information about an issue or topic, tag it as a question. Feel free to ask and engage in discussions.
* review: Issues or pull requests that are pending review. Use this tag when you have submitted your work, and it is awaiting feedback or approval from maintainers. Alternatively feel free to add the tag at any time you would like a maintainer to look over the issue.
* testing: Issues related to software testing, test cases, or compatibility checks. Use this tag when discussing testing procedures or reporting test-related problems.
* ui/ux: Issues related to user interface (UI) and user experience (UX) design. Use this tag when discussing design improvements or reporting UI/UX issues.
* wontfix: Tag for issues that will not be addressed or worked on. Use this tag when a proposed change or feature does not align with project goals or priorities.

If you are unsure which tag to use, feel free to ask for guidance in the comments.

## Bug Handling Process

Bugs are inevitable in any software project, and we appreciate your help in identifying and resolving them. To streamline bug reporting and resolution, we follow a structured process:

### 1. Check for Existing Issues

Before reporting a new bug, please search the issue tracker for the particular software on GitHub to see if someone has already reported the same issue. If you find a similar issue, you can add a comment with additional information if necessary.

### 2. Create a New Issue

If you could not find an existing report for your bug:

* Go to our GitHub repository and click on the "Issues" tab.
* Click "New Issue" to create a new bug report.
* Use the Bug Report Template: We have provided a bug report template to ensure you include essential information for our team to understand and reproduce the issue.

### 3. Provide Detailed Information

When creating a bug report, please provide as much detail as possible:

* Title: A concise, descriptive title.
* Description: A detailed description of the bug, including what you expected to happen and what actually happened.
* Reproduction Steps: Clear steps to reproduce the bug. This helps us isolate the issue.
* Environment Information: Include details about your environment, such as software-config settings, software version, operating system, browser version, or versions of related-software (e.g. Python packages).
* Screenshots or Error Logs: If applicable, include screenshots or error logs to illustrate the problem.

### 4. Label the Issue

Our team will review your bug report and apply appropriate labels, such as "bug" and any relevant tags (e.g., "ui/ux," "dependencies").

### 5. Discussion and Resolution

Once the bug report is submitted, our team will review it and engage in discussion if additional information or clarification is needed. 

### 6. Fix and Testing

If the bug is confirmed, a contributor or maintainer will work on a fix. After implementing the fix, it will undergo testing to ensure the issue is resolved without introducing new problems.

### 7. Closed and Verified

Once the fix is confirmed and tested, the issue will be marked as "closed." You will be notified of the resolution, and you can verify the fix on your end.

### 8. Contributor Recognition

As a token of our appreciation, contributors who actively help identify and resolve bugs may be recognised and credited in our project.

Thank you for helping us improve our software. Your diligence in reporting and verifying bugs contributes to the stability and reliability of our projects.

## Feature Request Process

Feature requests are a valuable way to improve our software's functionality and meet the needs of our users. We follow a similar structured process for features:

### 1. Check for Existing Requests

Before submitting a new feature request, please search our GitHub issue tracker to see if someone has already proposed a similar feature. If you find a similar request, you can add a comment with additional thoughts or use cases.

### 2. Create a New Feature Request

If you could not find an existing feature request for your idea:

* Go to our GitHub repository and click on the "Issues" tab.
* Click "New Issue" to create a new feature request.
* Use the Feature Request Template: We have provided a feature request template to help you include essential details about your proposal.

### 3. Provide Detailed Information

When creating a feature request, please provide as much detail as possible:

* Title: A concise, descriptive title that summarises the proposed feature.
* Description: A detailed description of the feature, including its purpose, benefits, and use cases.
* Use Cases: Explain scenarios where this feature would be valuable or necessary.
* Implementation Ideas: If you have suggestions on how to implement the feature, please share them.
* Alternatives: Mention any alternative solutions or workarounds you have considered.
* Visual Aids: If applicable, include diagrams, mock-ups, or screenshots to visualise the feature.

### 4. Label the Issue

Our team will review your feature request and apply appropriate labels, such as "feature request" and any relevant tags (e.g., "ui/ux," "enhancement").

### 5. Discussion and Feedback

Once your feature request is submitted, our team and the community may engage in discussions to better understand the proposal, refine the idea, or explore alternative approaches. Feedback from the community is invaluable in this process.

### 6. Evaluation

Feature requests will be evaluated based on their alignment with project goals, technical feasibility, and potential impact on users. Not all feature requests may be implemented, but each one will be carefully considered.

### 7. Implementation and Testing

If a feature request is approved for implementation, it will be added to the project's development roadmap. A contributor or maintainer will work on implementing the feature, followed by testing to ensure it functions as intended.

### 8. Notification

You will be notified about the progress of your feature request, including when it is assigned, in development, and tested. You can follow the discussion and implementation process on GitHub.

### 9. Contributor Recognition

We value your contributions, including feature requests. Contributors who actively participate in discussions and provide valuable input may be recognised and credited in our project.

Thank you for helping us enhance our project. Your feature requests play a vital role in shaping the future of the Arachne Digital community.

## Code Contribution Workflow

Arachne Digital follows a structured workflow to ensure that code contributions are thoroughly reviewed, tested, and integrated effectively. This process is designed to maintain code quality, reliability, and alignment with the project's goals. Here are the key steps in the contribution workflow:

### 1. Submission

Begin by creating a fork of our repository on GitHub. Next, clone your forked repository to your local development environment using Git. Once you have your local copy, create a new branch within your fork, giving it a descriptive name that relates to your contribution. This branch will serve as the container for the changes you make.

### 2. Development

To work on your contribution, make your code changes, enhancements, or bug fixes within your dedicated branch. As you make progress, remember to commit your changes regularly, accompanied by meaningful commit messages that describe the purpose and functionality of each commit. This practice helps maintain clarity and transparency throughout the development process.

### 3. Testing and Documentation

After implementing your code changes, it is crucial to conduct testing to ensure they function as intended and do not introduce new issues. Additionally, if your contribution impacts documentation in any way, please update the relevant documentation to ensure it remains accurate and aligned with the changes you have made. This ensures that users and contributors have access to up-to-date and reliable information.

### 4. Pull Request (PR)

Once your contribution is ready, it is time to create a PR from your branch to the original project's repository. When doing so, make sure to provide a clear and informative description of your changes within the PR. Explain why these changes are necessary and offer any pertinent details. If your contribution addresses specific issues, be sure to reference those issues in the PR description to facilitate a more efficient review process.

### 5. Review

After you have submitted your PR, our project maintainers and fellow contributors will review your changes. They will assess your code, offer feedback, and suggest potential improvements. You can engage in discussions with the reviewers. This collaborative process ensures that your work aligns with project standards and objectives.

### 6. Continuous Integration (CI)

Once you have submitted your PR, our CI system will automatically run tests to evaluate its adherence to our quality standards. Please review the CI results and address any issues or necessary fixes. This step helps maintain the project's overall integrity.

### 7. Approval

After your PR aligns with the project's criteria and requirements, it will undergo review and receive approvals from project maintainers or designated reviewers. This step signifies that your contribution has been accepted and is on track for inclusion in our software.

### 8. Merge

Once the PR is approved, a project maintainer will merge your changes into the main repository, incorporating your contribution into the software.

### 9. Closure

Upon merging your Pull Request (PR), any related issues that were addressed by your contribution will be automatically closed. We genuinely appreciate your valuable contribution, and our team extends heartfelt thanks for your effort and commitment to the project!

### 10. Contributor Recognition

Contributors who actively participate and make significant contributions may be recognised and credited in our project.

By following this structured workflow, you can contribute effectively to our projects, collaborate with the community, and ensure that your contributions align with our quality and coding standards. Thank you for your contributions to our projects!

## Licence 

Please refer to the project repositiory for the license the project is issued under. Please note that all contributions fall under the respective licence.

* [Thread licence](https://github.com/arachne-threat-intel/thread/blob/main/LICENSE.txt)
* [Tracery licence](https://github.com/arachne-threat-intel/tracery/blob/main/LICENSE)
* [Spindle licence](https://github.com/arachne-threat-intel/spindle/blob/main/LICENSE.md)

## Recognition and Attribution

At Arachne Digital, we greatly value the contributions of our community members. Your dedication and hard work drive the success of our projects. To show our appreciation, we have established several ways to recognise and attribute your contributions.

* Contributor Hall of Fame: Our Contributor Hall of Fame is a dedicated page on our website where we highlight the exceptional contributions made by community members. This is where your name and profile can shine, alongside a description of your significant contributions.
* Commit Messages and Changelogs: Our detailed changelog includes the names of contributors next to the changes or features they have introduced. This makes it easy for users and fellow contributors to see who contributed what in each release.
* Project Credits: In our README file, you will find an "[Acknowledgements](README.md#acknowledgements)" section that lists the names of individuals who have made substantial contributions.
* Social Media Shoutouts: We use our project's social media channels to publicly acknowledge and thank contributors. We share their profiles, contributions, and achievements with our followers.
* Personal Thank-You Notes: As a token of our appreciation, we may send personalised thank-you notes or emails to contributors. These messages will express our gratitude for your efforts and acknowledge your unique contributions.

By contributing to Arachne Digital projects, you are not only helping us advance that specific project but also becoming an integral part of our open-source community. Your contributions are essential, and we want to ensure that you receive the recognition and attribution you deserve.

Thank you for being a valued member of the Arachne Digital community!

## Contact Information

If you have questions or need clarifications about contributing to Arachne Digital, we encourage you to reach out and ask. Our community is here to support you on your journey to become a contributor. Here is how you can get help:

* Slack Community: Join our Slack community and visit the #questions-about-contributing channel. This channel is dedicated to answering your questions and providing guidance on the contribution process. To get access, please email contact[at]arachne[dot]digital with a bit about who you are and how you would like to contribute.
* GitHub Issues: If you have a specific question related to an ongoing issue or pull request on GitHub, feel free to comment directly on the relevant thread. Our maintainers and contributors will do their best to assist you.
* Documentation: Check our documentation for answers to common questions. We strive to maintain comprehensive and up-to-date documentation to help you get started.
* Contributor Guidelines: Review these Contributor Guidelines for detailed information on the contribution process, coding standards, and more.
* Contact Us: If you have a question that is not covered by the above options, you can contact us directly via contact[at]arachne[dot]digital. We are here to assist you in any way we can.

Remember, there are no silly questions, and we value your curiosity and engagement. Do not hesitate to ask if you are unsure about anything. We appreciate your interest in contributing to our projects!

## Developer's Certificate of Origin v1.1

If you contribute any source code, we need you to agree to the following Developer's Certificate of Origin (DCO) below.

The DCO was originally adopted from the TRAM project. It is a standard declaration ensuring that contributors have the right to submit their work, protecting both the project and our contributors. When making contributions to any Arachne Digital project, please keep in mind that agreeing to the DCO is part of the submission process.

```
By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
 have the right to submit it under the open source license
 indicated in the file; or

(b) The contribution is based upon previous work that, to the best
 of my knowledge, is covered under an appropriate open source
 license and I have the right under that license to submit that
 work with modifications, whether created in whole or in part
 by me, under the same open source license (unless I am
 permitted to submit under a different license), as indicated
 in the file; or

(c) The contribution was provided directly to me by some other
 person who certified (a), (b) or (c) and I have not modified
 it.

(d) I understand and agree that this project and the contribution
 are public and that a record of the contribution (including all
 personal information I submit with it, including my sign-off) is
 maintained indefinitely and may be redistributed consistent with
 this project or the open source license(s) involved.
```
