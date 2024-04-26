# Design

## Overview of Components

Most of Thread's components have been extended from components from the original repo Thread is forked from. These are as follows:

- Config:
  - App-config
  - Database schema
  - List-values (Countries, Regions, and Industries)
- Database:
  - DAO (Data Access Object)
    - Interacts with the database to return or update data
- Handlers:
  - Web-API
    - The landing-point for any request
    - Handles the requests to pages (homepage, about, edit-report, etc.)
    - Receives the requests for actions - e.g. clicking on a report-sentence - and forwards this on to the appropriate component
- Models:
  - Contains the initially-released ML (Machine-Learning) models with the accompanying training data used
- Service:
  - Data-Service
    - For report-data or attack-data tasks
    - e.g. Fetching the latest Mitre Att&ck® data
    - e.g. Retrieval of report-sentence data
  - ML-Service
    - For tasks related to the ML-analysis of Thread reports
    - e.g. Analysing report sentences with Thread's ML models
    - e.g. Building/Saving the ML models
  - RegEx-Service
    - For tasks related to the regex-analysis of Thread reports
    - (Not currently used but will remain if used in the future)
  - Rest-Service
    - For tasks related to creating/updating reports from REST requests
    - e.g. Report-queue management
    - e.g. Report-sentence add/reject attack mappings
    - e.g. Report-sentence IoC (Indicators of Compromise) updates
    - (Currently becoming a large file, we could look into breaking this one up)
  - Web-Service
    - For website-related tasks
    - e.g. Website-routes definition
    - e.g. HTML-building for report-sentences
    - e.g. Permissions-check for certain website-actions
- Webapp:
  - The client-side code for Thread (HTML, JS)

New components added are as follows:

- Reports:
  - Report-exporter
    - Handles the export of report-data in JSON or a PDF(-library) compatible format
    - Extended from initial code in Web-API (handling export-requests)

Furthermore, Thread uses an external submodule - Spindle - (also by Arachne Digital) to hold data on cyber threat actors.

## Components Working Together

These components work together to fulfil different tasks related to reports. For example, submitting a report (URL) to Thread consists of:

- Web-API receives request; forwards to Rest-Service to handle an insert-report task
- Rest-Service adds this report to the queue
- Before the Rest-Service picks up this report from the queue, some tasks include:
  - Web-Service called to verify the URL
  - Data-Service called to confirm the provided title is unique
  - DAO called to create a database entry for this report
- When the Rest-Service picks up this report from the queue, its tasks during report-anaysis include:
  - Web-Service called to further call Newspaper for web-scraping the contents of the report-URL and return sentences as text and HTML
  - DAO is called to update the report-entry and create report-sentence entries as the report is analysed
  - ML-Service is called to use the ML models to analyse the report-URL web-scraped content
