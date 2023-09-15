<!-- NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital -->

# Contribute to Thread

Thank you for wanting to contribute to Thread! 

## Project Mission & Summary:

Thread is an open-source initiative dedicated to enhancing cyber threat intelligence (CTI) mapping by automating the process of linking cybersecurity reports and articles to MITRE ATT&CK®. Our mission is to empower security professionals, organisations, and analysts by providing efficient, empowering, and community driven CTI capabilities.

## Code of Conduct

The Thread community has adopted the Contributor Covenant. Before contributing, please read the [CODE OF CONDUCT](CODE_OF_CONDUCT.md). By contributing to the Thread community you agree to the code of conduct.

## Resources

Please see the [README](README.md) for high level information about Thread, and the [ROADMAP](ROADMAP.md) to get an understanding of where the project is going.

## Communication channels

Arachne Digital uses Slack to discuss everything to do with our open source projects. To get access, please email contact[at]arachne[dot]digital with a bit about who you are and how you would like to contribute.

## Getting started

* Is there anything we've not already said that someone needs to know to help them get started?

## Types of contributions

* The types of contributions we would like, such as code, documentation, bug reports, feature requests. Anything else?
* We will need guidelines for each type of contribution.

## Coding standards

Anything to add here?

## Issue tracking

We use GitHub issue tags to categorise our issues and pull requests. Please use these tags when creating or working on issues to help streamline the work that goes into building Thread and the community.

Below are the tags we use:

* bug: If something isn't working as expected or there's a malfunction, tag the issue as a bug. Be sure to provide detailed information about the problem.
* community: These tags are used for community building efforts, such as organising events, discussions, or initiatives aimed at fostering our community.
* config change: Use this tag for requests to change configuration settings. Clearly describe the requested changes in the issue.
* dependencies: Tag for pull requests that update a dependency file, such as libraries or external resources. Provide information on the dependency and the reason for the update.
* documentation: Issues related to improvements or additions to documentation. Use this tag for discussions and tasks related to enhancing our documentation.
* duplicate: If you find that an issue or pull request already exists for the same problem or request, tag it as a duplicate.
* enhancement: Tag for issues related to performance improvements, code refactoring, or enhancing usability without introducing new features.
* feature request: Tag for new feature requests to our software or services. Please provide clear details about the proposed feature.
* good first issue: This tag identifies issues suitable for newcomers to the project. If you're new to our community, consider starting with these issues to get acquainted with contributing.
* help wanted: Tag for issues that require extra attention or assistance from the community. If you're looking for a way to contribute, check out these issues.
* invalid: If an issue doesn't seem valid or relevant, tag it as invalid. Provide a brief explanation of why the issue is considered invalid.
* question: If you have questions or need further information about an issue or topic, tag it as a question. Feel free to ask and engage in discussions.
* review: Issues or pull requests that are pending review. Use this tag when you've submitted your work, and it's awaiting feedback or approval from maintainers. Alternatively feel free to add the tag at any time you would like a maintainer to look over the issue.
* testing: Issues related to software testing, test cases, or compatibility checks. Use this tag when discussing testing procedures or reporting test-related problems.
* ui/ux: Issues related to user interface (UI) and user experience (UX) design. Use this tag when discussing design improvements or reporting UI/UX issues.
* wontfix: Tag for issues that will not be addressed or worked on. Use this tag when a proposed change or feature doesn't align with project goals or priorities.

If you're unsure which tag to use, feel free to ask for guidance in the comments.

## Bug Handling Process

Bugs are inevitable in any software project, and we appreciate your help in identifying and resolving them. To streamline bug reporting and resolution, we follow a structured process:

1. Check for Existing Issues. 

Before reporting a new bug, please search our issue tracker on GitHub to see if someone has already reported the same issue. If you find a similar issue, you can add a comment with additional information if necessary.

2. Create a New Issue.

If you couldn't find an existing report for your bug:

* Go to our GitHub repository and click on the "Issues" tab.
* Click "New Issue" to create a new bug report.
* Use the Bug Report Template: We have provided a bug report template to ensure you include essential information for our team to understand and reproduce the issue.

3. Provide Detailed Information

When creating a bug report, please provide as much detail as possible:

* Title: A concise, descriptive title.
* Description: A detailed description of the bug, including what you expected to happen and what actually happened.
* Reproduction Steps: Clear steps to reproduce the bug. This helps us isolate the issue.
* Environment Information: Include details about your environment, such as operating system, browser version, or software version.
* Screenshots or Error Logs: If applicable, include screenshots or error logs to illustrate the problem.

4. Label the Issue

Our team will review your bug report and apply appropriate labels, such as "bug" and any relevant tags (e.g., "ui/ux," "dependencies").

5. Discussion and Resolution

Once the bug report is submitted, our team will review it and engage in discussion if additional information or clarification is needed. 

6. Fix and Testing

If the bug is confirmed, a contributor or maintainer will work on a fix. After implementing the fix, it will undergo testing to ensure the issue is resolved without introducing new problems.

7. Closed and Verified

Once the fix is confirmed and tested, the issue will be marked as "closed." You will be notified of the resolution, and you can verify the fix on your end.

8. Participate in Discussions

Feel free to participate in discussions related to the bug. Your insights and suggestions are valuable in making the project better.

9. Contributor Recognition

As a token of our appreciation, contributors who actively help identify and resolve bugs may be recognised and credited in our project.

Thank you for helping us improve our software. Your diligence in reporting and verifying bugs contributes to the stability and reliability of our project.




* How feature requests are handled? I'm happy for there to be a process where both of us discuss features and build them into our roadmap. We may need something like "Features will be discussed at our fortnightly maintainers catchup and we will reply to the request to let you know if it is something that will be incorporated into Thread, and if so where it fits into the roadmap." This gives people a cadence they can expect, and it means we will also need to formalise calls and put regular review calls in place.
* What will the workflow be for submitting, reviewing, and merging contributions?

For the tagging system, here are some suggested tags as a first pass:
* Good first issue
* Bug
* Feature Request
* Documentation: Issues related to improving or updating documentation, such as README files, user guides, or API documentation
* UI/UX: This tag is for issues related to user interface (UI) or user experience (UX) improvements. It can cover design changes, layout enhancements, and usability suggestions.
* Enhancement: We can use this tag for general enhancements or improvements that don't fit strictly into the "feature request" category. It can include performance optimisations, code refactoring, or usability improvements.
* Help Wanted: Indicate issues where help from the community is needed. This tag can be applied to issues that may require additional expertise or effort. We should have a process for monitoring for these if we use this, and state that people should reach out in whatever channel we go with as well.
* Testing: Tag issues that involve testing the software, creating test cases, or ensuring compatibility with different environments or configurations.
* Community: This tag can be used for issues related to community building, collaboration, or discussions. It may include proposals for events, community guidelines, or discussions about project direction. Might seem strange but this is a contribution to the community, not all contributions take the form of code. We should decide if we want this discussion to occur on GitHub, or in anothe channel such as Slack/Discord. Either way it should be called out in these guidelines so people who want to make non-code contributions know what to do.
* Priority
* Security: We have said we want things disclosed to us privately, do we reiterate that here? Do we formalise what that process is?
* Question
* Review Needed
* Duplicate: If an issue is a duplicate of another, we can mark it with this tag to avoid redundancy and track the original issue.
* Invalid: We can use this tag for issues that are deemed invalid or not relevant to Thread.
* Wontfix

## Testing and quality assurance
* How do you want testing handled?
* We will need to talk about what our QA process will be, as in you reviewing code, and how often that will occur so people know when their pull request will be merged in.

## Licence 
Thread is offered under the original TRAM licence, the [Apache License 2.0](LICENSE.txt). Please note that all contributions to Thread fall under the Apache License 2.0.

## Recognition and Attribution
* How will contributors be recognised and attributed for their work?
* What contributor acknowledgement or rewards system will we put in place?

## Contact information
How do we want to manage questions people want to ask before contributing? Do we want to have a shared mailbox that we both have access to, and can add others to if they become maintainers over time? Or do we want to handle this in a dedicated channel in our Slack or Discord (if we go with either of those)?

## Submission guidelines

You are welcome to comment on issues, open new issues, and open pull requests.

Also, if you contribute any source code, we need you to agree to the following Developer's Certificate of Origin below.

Below are the contribution guidelines for the original repo Thread is forked from, TRAM. We have no major differences for these guidelines, so they have remained the same:
### Developer's Certificate of Origin v1.1

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
