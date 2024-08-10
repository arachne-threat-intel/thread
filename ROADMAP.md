# Thread Roadmap

## Project Mission and Summary
Thread is an open-source, community-driven tool that automates the mapping of cybersecurity reports to the MITRE ATT&CK® framework and other threat analysis frameworks. Developed by Arachne Digital, Thread empowers security professionals and organisations to quickly and accurately map TTPs from free text, enhancing threat detection and analysis. With continuous updates and a focus on efficiency and accuracy, Thread aims to become the leading platform for CTI mapping, contributing to a safer digital world.

## Milestones

### Milestone 1: Enhancing Core Capabilities
* Performance Optimisation: Focus on improving the efficiency of TTP processing by implementing hierarchical search based on the ATT&CK structure and a prescan sampling method. These optimisations will enhance the speed and accuracy of mapping processes.
* Machine Learning Model Improvements: Update the machine learning models with Arachne Digital’s flagged data and evaluate their performance using different negative handling methods. Implement feedback loops to enhance model accuracy based on user interactions from Arachne Digital’s hosted Thread instances.
* Advanced TTP Breakdown: Implement the capability to break down TTPs in reports by operating systems (Windows, MAC, Linux), providing more granular insights for analysts.
Scalability Improvements: Optimise Thread’s infrastructure to handle increased traffic and usage, particularly as community engagement and the number of processed reports grow.
* Community Engagement: Launch initiatives to attract new contributors and maintain community engagement, including webinars, tutorials, and community challenges focused on specific development tasks.

### Milestone 2: Security Testing and Remediation
* Conduct Penetration Testing: Identify security vulnerabilities in the application through comprehensive penetration testing. Collaborate with the assigned penetration tester to perform a detailed security assessment, covering all aspects of the application infrastructure, codebase, and integrations.
* Review and Prioritise Findings: Understand and categorize the security risks identified during the penetration testing. Analyse the findings provided by the penetration tester, categorise them based on severity, and prioritise them for remediation based on potential impact and ease of exploitation.
* Implement Remediation Measures: Address all identified security vulnerabilities to ensure the safety and integrity of the application. Develop and deploy fixes for the identified vulnerabilities, ensuring that each issue is resolved in line with best security practices. 
* Update Security Documentation: Maintain accurate records of the security posture and mitigation steps taken for Thread. Document all findings, remediation steps, and testing results, and update the security policy and procedures to reflect any new security practices or lessons learned from the testing process.

### Milestone 3: User Experience and Documentation
* Automation of Maintenance Tasks: Develop and deploy automated systems for monthly updates of MITRE ATT&CK data, ensuring that Thread remains current without manual intervention.
* User Experience Enhancements: Streamline the setup and development environment for new contributors, making it easier to get started with Thread development. Improve the user interface to simplify the report analysis and export process.
* Review and Assess Existing Documentation: Ensure that Thread users have access to accurate and up-to-date resources. Conduct a thorough review of the current documentation to identify gaps, outdated information, and areas that require clarification or expansion.
* Revise and Expand Documentation: Provide comprehensive guidance on Thread's enhanced capabilities. Update existing documentation to reflect recent functionality changes, ensuring all new features are well-documented and easy to understand for users.
* Create New Tutorials and Guides: Empower users to leverage Thread effectively for their threat intelligence needs. Based on the documentation review, develop new tutorials and guides, if necessary, to help users maximise the potential of Thread and navigate its features with ease.

### Milestone 4: Additional Frameworks 
* Integration with New Frameworks: Begin implementing support for additional frameworks past MITRE ATT&CK Enterprise, including MITRE ATT&CK ICS, MITRE ATT&CK Mobile, MITRE ATLAS, and DISARM Red Framework. The order listed here is the planned order of implementation. This will expand Thread’s utility and make it more versatile for various cybersecurity and disinformation analysis use cases.

### Milestone 5: Integrations and Stakeholders
* Support for MISP and Sigma Rules: Add support for exporting mapped TTPs to MISP and Sigma rules, enhancing Thread’s utility in threat intelligence sharing and SIEM rule creation.
* Stakeholder Collaboration: Engage with DISARM Foundation and initiate collaboration with MITRE to align Thread’s development with broader industry standards and needs. Gather input from these stakeholders to prioritise upcoming features.

### Milestone 6: UX Design Optimisation
* Conduct a UX Audit: Identify pain points and areas for improvement in the current Thread user experience. Review user feedback, analyse usage data, and assess the interface's overall flow to pinpoint areas that may hinder user efficiency or satisfaction.
* Collaborate with UI/UX Designers: Revamp the Thread interface for enhanced usability. Work closely with UI/UX designers to redesign the interface, focusing on simplifying navigation, improving accessibility, and optimising user interactions.
* Implement User Testing: Validate the effectiveness of the UX improvements through user feedback. Conduct user testing sessions with a diverse group of Thread users to gather insights on the redesigned interface, ensuring that changes align with user expectations and needs.

### Milestone 7: Scaling and Sustainability
* Scaling Infrastructure: Optimise the infrastructure to handle increased traffic and usage, ensuring that the public instance of Thread remains performant and reliable as its user base grows.
* Long-term Sustainability Planning: Develop a sustainability plan for Thread, including potential funding sources, partnerships, and governance structures to ensure its continued development and maintenance.
* Global Outreach and Localisation: Begin efforts to localise Thread, translating the interface and documentation into multiple languages to support a global user base. Engage with international privacy and open-source communities to broaden Thread’s reach.

### Milestone 8: Global Impact and Continuous Innovation
* Global Outreach: Expand Thread’s reach by promoting its capabilities at cybersecurity conferences, publishing case studies, and engaging with global CTI communities. Work towards making Thread the standard tool for CTI mapping worldwide.
* Establishing Industry Leadership: Position Thread as the leading tool for mapping free text to various security and disinformation frameworks. Continue to build partnerships with key industry players and integrate Thread into broader CTI workflows.
